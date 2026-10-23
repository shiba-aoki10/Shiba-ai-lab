"""Fluxo completo de aprovação e liberação (Incremento 4C).

Tudo FICTÍCIO, em pastas temporárias fora do Git. Decisões rodam em modo
simulação (como deve ser quando executadas por IA) ou com o ambiente
explicitamente limpo, para testar a regra do não-simulado.
"""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from shiba import fluxo
from shiba.aprovacao import APROVACAO_EDITORIAL as AP, VALIDACAO_NORMATIVA as VN, ErroAprovacao
from shiba.auditoria import ErroIntegridade, Registro
from shiba.cli import main
from shiba.config import DIR_CLIENTES, RAIZ, ErroConfig
from shiba.dados import repositorio_que_contem

HOJE = date(2026, 10, 23)
CLIENTE = "exemplo-clinica"
SEM_AGENTE = {}                       # ambiente sem marcadores de agente
COM_AGENTE = {"CLAUDECODE": "1"}


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name).resolve()
        if repositorio_que_contem(self.tmp):
            self.skipTest("pasta temporária dentro de repositório Git")
        self.estado = self.tmp / "estado"
        self.estado.mkdir()
        # Cópia dos clientes fictícios: permite alterar configuração sem tocar no repositório.
        self.clientes = self.tmp / "clientes"
        shutil.copytree(DIR_CLIENTES, self.clientes)
        self.amb = fluxo.abrir(self.estado, dir_clientes=self.clientes)
        self.peca = self.tmp / "legenda.md"
        self.peca.write_text("Conheça nosso tratamento.\n\n#saude", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def cadastrar_equipe(self):
        f, c = fluxo.cadastrar_identidade, CLIENTE
        f(self.amb, c, "id-adm", ["resp-04"], "FICTÍCIO: termo T-0", "bootstrap", simulacao=True)
        for ident, papel in (("id-autor", "resp-01"), ("id-rev1", "resp-02"), ("id-rev2", "resp-02"),
                             ("id-val", "resp-03")):
            f(self.amb, c, ident, [papel], f"FICTÍCIO: termo de {ident}", "id-adm", simulacao=True)

    def hashes(self, peca="p1"):
        e = fluxo.status(self.amb, CLIENTE, peca, HOJE)
        return {k: e[k] for k in ("hash_conteudo", "hash_config", "hash_laudo")}

    def ate_aprovado(self, peca="p1", arquivo=None):
        if not Registro(self.estado, CLIENTE).ler():
            self.cadastrar_equipe()
        fluxo.registrar_versao(self.amb, CLIENTE, peca, arquivo or self.peca, "legenda", "id-autor",
                               "instagram", hoje=HOJE)
        fluxo.verificar_versao(self.amb, CLIENTE, peca, HOJE)
        fluxo.enviar_para_revisao(self.amb, CLIENTE, peca, "id-autor", HOJE)
        for aviso in fluxo.status(self.amb, CLIENTE, peca, HOJE)["avisos"]:
            fluxo.reconhecer_aviso(self.amb, CLIENTE, peca, aviso, "id-rev1", "resp-02",
                                   "FICTÍCIO: ciente", self.hashes(peca), simulacao=True, hoje=HOJE)
        for rev in ("id-rev1", "id-rev2"):
            fluxo.decidir(self.amb, CLIENTE, peca, AP, rev, "resp-02", "", self.hashes(peca),
                          simulacao=True, hoje=HOJE)
        return fluxo.decidir(self.amb, CLIENTE, peca, VN, "id-val", "resp-03", "", self.hashes(peca),
                             simulacao=True, hoje=HOJE)


class TestFluxoCompleto(Base):
    def test_saude_ate_liberacao(self):
        self.cadastrar_equipe()
        fluxo.registrar_versao(self.amb, CLIENTE, "p1", self.peca, "legenda", "id-autor", "instagram",
                               hoje=HOJE)
        estados = [fluxo.status(self.amb, CLIENTE, "p1", HOJE)["estado"]]
        estados.append(fluxo.verificar_versao(self.amb, CLIENTE, "p1", HOJE)["estado"]["estado"])
        estados.append(fluxo.enviar_para_revisao(self.amb, CLIENTE, "p1", "id-autor", HOJE)["estado"])
        self.assertEqual(estados, ["rascunho", "verificado", "aguardando_revisao"])
        for aviso in fluxo.status(self.amb, CLIENTE, "p1", HOJE)["avisos"]:
            fluxo.reconhecer_aviso(self.amb, CLIENTE, "p1", aviso, "id-rev1", "resp-02", "ciente",
                                   self.hashes(), simulacao=True, hoje=HOJE)
        e = fluxo.decidir(self.amb, CLIENTE, "p1", AP, "id-rev1", "resp-02", "", self.hashes(),
                          simulacao=True, hoje=HOJE)
        self.assertEqual(e["estado"], "aguardando_revisao")          # quórum 2 da saúde
        e = fluxo.decidir(self.amb, CLIENTE, "p1", AP, "id-rev2", "resp-02", "", self.hashes(),
                          simulacao=True, hoje=HOJE)
        self.assertEqual(e["estado"], "aguardando_validacao_normativa")
        e = fluxo.decidir(self.amb, CLIENTE, "p1", VN, "id-val", "resp-03", "", self.hashes(),
                          simulacao=True, hoje=HOJE)
        self.assertEqual((e["estado"], e["simulacao"], e["nivel_garantia"]), ("aprovado", True, "declarativa"))
        r = fluxo.liberar(self.amb, CLIENTE, "p1", "id-rev1", simulacao=True, hoje=HOJE)
        pacote = Path(r["pacote"])
        self.assertEqual(sorted(p.name for p in pacote.iterdir()),
                         ["LEIA-ANTES.md", "conteudo.md", "fontes.md", "laudo.json", "manifesto.json"])
        m = json.loads((pacote / "manifesto.json").read_text(encoding="utf-8"))
        self.assertEqual((m["escopo"], m["publicacao_audiovisual_autorizada"], m["publicacao_automatica"],
                          m["simulacao"]), ("conteudo_textual", False, False, True))
        self.assertEqual(len(m["aprovacao_editorial"]), 2)
        self.assertEqual(m["validacao_normativa"][0]["identidade"], "id-val")
        self.assertEqual(m["liberacao_manual"]["identidade"], "id-rev1")
        leia = (pacote / "LEIA-ANTES.md").read_text(encoding="utf-8")
        for trecho in ("NÃO É AUTORIZAÇÃO PARA PUBLICAR A PEÇA AUDIOVISUAL", "SIMULAÇÃO: NÃO PUBLICAR",
                       "Aprovação editorial", "Validação normativa", "Liberação manual",
                       "não prova identidade", "Não é assinatura digital"):
            self.assertIn(trecho, leia)
        self.assertEqual((pacote / "conteudo.md").read_bytes(), self.peca.read_bytes())
        eventos = [e["evento"] for e in Registro(self.estado, CLIENTE).ler()]
        self.assertEqual(eventos[-1], "liberacao_manual")
        self.assertFalse(any(p.name.startswith(".tmp-") for p in pacote.parent.iterdir()))

    def test_liberar_exige_aprovado(self):
        self.cadastrar_equipe()
        fluxo.registrar_versao(self.amb, CLIENTE, "p1", self.peca, "legenda", "id-autor", "instagram", hoje=HOJE)
        with self.assertRaisesRegex(ErroAprovacao, "aprovada"):
            fluxo.liberar(self.amb, CLIENTE, "p1", "id-rev1", simulacao=True, hoje=HOJE)

    def test_liberacao_e_unica_por_versao(self):
        self.ate_aprovado()
        fluxo.liberar(self.amb, CLIENTE, "p1", "id-rev1", simulacao=True, hoje=HOJE)
        with self.assertRaisesRegex(ErroAprovacao, "já foi liberada"):
            fluxo.liberar(self.amb, CLIENTE, "p1", "id-rev1", simulacao=True, hoje=HOJE)

    def test_tentativa_recusada_fica_no_historico(self):
        self.ate_aprovado()
        fluxo.registrar_versao(self.amb, CLIENTE, "p1", self.peca, "legenda", "id-autor", "instagram", hoje=HOJE)
        with self.assertRaises(ErroAprovacao):
            fluxo.decidir(self.amb, CLIENTE, "p1", AP, "id-autor", "resp-01", "", self.hashes(),
                          simulacao=True, hoje=HOJE)
        self.assertEqual(Registro(self.estado, CLIENTE).ler()[-1]["evento"], "tentativa_recusada")


class TestAgenteESimulacao(Base):
    def test_agente_nao_decide_sem_simulacao(self):
        for chamada in (
            lambda: fluxo.cadastrar_identidade(self.amb, CLIENTE, "id-x", ["resp-04"], "x", "bootstrap",
                                               ambiente=COM_AGENTE),
            lambda: fluxo.decidir(self.amb, CLIENTE, "p1", AP, "id-rev1", "resp-02", "", {},
                                  ambiente=COM_AGENTE),
            lambda: fluxo.liberar(self.amb, CLIENTE, "p1", "id-rev1", ambiente=COM_AGENTE),
            lambda: fluxo.reconhecer_aviso(self.amb, CLIENTE, "p1", "a", "id-rev1", "resp-02", "x", {},
                                           ambiente=COM_AGENTE),
        ):
            with self.assertRaisesRegex(ErroAprovacao, "agente de IA"):
                chamada()

    def test_sem_marcadores_decisao_real_em_cliente_ficticio_e_aceita(self):
        """Prova de que a barreira é de PROCESSO: sem os marcadores, ela não age."""
        e = fluxo.cadastrar_identidade(self.amb, CLIENTE, "id-adm", ["resp-04"], "FICTÍCIO", "bootstrap",
                                       ambiente=SEM_AGENTE)
        self.assertFalse(e["dados"]["simulacao"])

    def test_simulacao_recusada_para_cliente_real(self):
        dados = self.tmp / "dados"
        (dados / "clientes").mkdir(parents=True)
        shutil.copytree(self.clientes / CLIENTE, dados / "clientes" / "real1")
        perfil = dados / "clientes" / "real1" / "perfil.toml"
        perfil.write_text(perfil.read_text(encoding="utf-8").replace('id = "exemplo-clinica"', 'id = "real1"')
                          .replace("ficticio = true", "ficticio = false"), encoding="utf-8")
        amb = fluxo.abrir(dados=str(dados))
        self.assertEqual(amb.estado, dados.resolve())
        with self.assertRaisesRegex(ErroAprovacao, "fictício"):
            fluxo.cadastrar_identidade(amb, "real1", "id-adm", ["resp-04"], "x", "bootstrap", simulacao=True)


class TestSeguranca(Base):
    def test_edicao_da_copia_depois_da_aprovacao(self):
        self.ate_aprovado()
        copia = self.estado / "pecas" / CLIENTE / "p1" / "v1" / "peca.md"
        copia.write_text("Conheça nosso tratamento!\n\n#saude", encoding="utf-8")
        e = fluxo.status(self.amb, CLIENTE, "p1", HOJE)
        self.assertEqual(e["estado"], "integridade_nao_confirmada")
        with self.assertRaises(ErroIntegridade):
            fluxo.liberar(self.amb, CLIENTE, "p1", "id-rev1", simulacao=True, hoje=HOJE)

    def test_arquivo_de_trabalho_editado(self):
        self.ate_aprovado()
        self.peca.write_text("Conheça nosso tratamento!!\n\n#saude", encoding="utf-8")
        e = fluxo.status(self.amb, CLIENTE, "p1", HOJE, arquivo=self.peca)
        self.assertEqual(e["estado"], "aprovado")                    # a versão registrada
        self.assertIn("DIFERENTE", e["arquivo_de_trabalho"])          # mas não o arquivo editado

    def test_historico_adulterado_bloqueia_tudo(self):
        self.ate_aprovado()
        reg = Registro(self.estado, CLIENTE)
        linhas = reg.log.read_text(encoding="utf-8").splitlines()
        reg.log.write_text("\n".join(linhas[:-1]) + "\n", encoding="utf-8")   # apaga a validação
        self.assertEqual(fluxo.status(self.amb, CLIENTE, "p1", HOJE)["estado"], "integridade_nao_confirmada")
        with self.assertRaises(ErroIntegridade):
            fluxo.decidir(self.amb, CLIENTE, "p1", VN, "id-val", "resp-03", "", {}, simulacao=True, hoje=HOJE)
        with self.assertRaises(ErroIntegridade):
            fluxo.liberar(self.amb, CLIENTE, "p1", "id-rev1", simulacao=True, hoje=HOJE)

    def test_configuracao_modificada_depois_da_aprovacao(self):
        self.ate_aprovado()
        perfil = self.clientes / CLIENTE / "perfil.toml"
        perfil.write_text(perfil.read_text(encoding="utf-8").replace("maximo = 3", "maximo = 4"),
                          encoding="utf-8")
        e = fluxo.status(self.amb, CLIENTE, "p1", HOJE)
        self.assertEqual(e["estado"], "rascunho")
        with self.assertRaisesRegex(ErroAprovacao, "rascunho"):
            fluxo.liberar(self.amb, CLIENTE, "p1", "id-rev1", simulacao=True, hoje=HOJE)

    def test_aprovacao_de_outra_peca_nao_libera(self):
        self.ate_aprovado("p1")
        outra = self.tmp / "outra.md"
        outra.write_text("Agende uma consulta.\n\n#saude", encoding="utf-8")
        fluxo.registrar_versao(self.amb, CLIENTE, "p2", outra, "legenda", "id-autor", "instagram", hoje=HOJE)
        reg = Registro(self.estado, CLIENTE)
        for e in [e for e in reg.ler() if e["evento"] == "decisao" and e["dados"]["peca"] == "p1"]:
            copia = {k: v for k, v in e["dados"].items() if k != "registrado_em"}
            reg.anexar("decisao", dict(copia, peca="p2"))
        self.assertNotEqual(fluxo.status(self.amb, CLIENTE, "p2", HOJE)["estado"], "aprovado")
        with self.assertRaises(ErroAprovacao):
            fluxo.liberar(self.amb, CLIENTE, "p2", "id-rev1", simulacao=True, hoje=HOJE)

    def test_mudanca_durante_a_liberacao_aborta_sem_pacote(self):
        self.ate_aprovado()
        original = fluxo._avaliar_atual
        chamadas = []

        def avaliar_e_alterar(*args, **kw):
            r = original(*args, **kw)
            chamadas.append(1)
            if len(chamadas) == 1:   # depois da 1ª leitura, alguém muda a configuração
                perfil = self.clientes / CLIENTE / "perfil.toml"
                perfil.write_text(perfil.read_text(encoding="utf-8").replace("maximo = 3", "maximo = 4"),
                                  encoding="utf-8")
            return r

        with mock.patch.object(fluxo, "_avaliar_atual", avaliar_e_alterar):
            with self.assertRaisesRegex(ErroIntegridade, "durante a liberação"):
                fluxo.liberar(self.amb, CLIENTE, "p1", "id-rev1", simulacao=True, hoje=HOJE)
        base = self.estado / "liberadas" / CLIENTE
        self.assertEqual(list(base.iterdir()), [])                  # nem pacote nem temporário
        self.assertNotEqual(Registro(self.estado, CLIENTE).ler()[-1]["evento"], "liberacao_manual")

    def test_hashes_vistos_desatualizados_recusam(self):
        self.ate_aprovado()
        fluxo.registrar_versao(self.amb, CLIENTE, "p1", self.peca, "legenda", "id-autor", "instagram", hoje=HOJE)
        fluxo.verificar_versao(self.amb, CLIENTE, "p1", HOJE)
        fluxo.enviar_para_revisao(self.amb, CLIENTE, "p1", "id-autor", HOJE)
        antigos = dict(self.hashes(), hash_laudo="0" * 64)
        with self.assertRaisesRegex(ErroAprovacao, "mudaram"):
            fluxo.decidir(self.amb, CLIENTE, "p1", AP, "id-rev1", "resp-02", "", antigos, simulacao=True,
                          hoje=HOJE)

    def test_versao_nova_com_os_mesmos_bytes_zera(self):
        self.ate_aprovado()
        fluxo.registrar_versao(self.amb, CLIENTE, "p1", self.peca, "legenda", "id-autor", "instagram", hoje=HOJE)
        e = fluxo.status(self.amb, CLIENTE, "p1", HOJE)
        self.assertEqual((e["versao"], e["estado"]), (2, "rascunho"))


class TestIsolamentoDoEstado(Base):
    def test_estado_dentro_de_repositorio_e_recusado_mesmo_ficticio(self):
        repo = self.tmp / "repo"
        (repo / ".git").mkdir(parents=True)
        (repo / "estado").mkdir()
        with self.assertRaisesRegex(ErroConfig, "repositório Git"):
            fluxo.abrir(repo / "estado")
        with self.assertRaises(ErroConfig):
            fluxo.abrir(RAIZ)

    def test_estado_obrigatorio_e_exclusivo(self):
        with self.assertRaisesRegex(ErroConfig, "--estado"):
            fluxo.abrir()
        with self.assertRaisesRegex(ErroConfig, "não existe"):
            fluxo.abrir(self.tmp / "nao-existe")

    def test_topo_exportado_fora_do_git(self):
        self.cadastrar_equipe()
        repo = self.tmp / "repo"
        (repo / ".git").mkdir(parents=True)
        with self.assertRaises(ErroConfig):
            fluxo.exportar_topo_auditoria(self.amb, CLIENTE, repo / "topo.json")
        topo = fluxo.exportar_topo_auditoria(self.amb, CLIENTE, self.tmp / "topo.json")
        self.assertEqual(fluxo.verificar_auditoria(self.amb, CLIENTE, self.tmp / "topo.json")["topo"]["seq"],
                         topo["seq"])

    def test_nada_do_fluxo_vai_para_o_repositorio(self):
        self.ate_aprovado()
        fluxo.liberar(self.amb, CLIENTE, "p1", "id-rev1", simulacao=True, hoje=HOJE)
        for nome in ("pecas", "auditoria", "liberadas"):
            self.assertFalse((RAIZ / nome).exists())
            self.assertTrue((self.estado / nome).is_dir())


class TestPassouNaoEAprovado(unittest.TestCase):
    def test_so_o_calculo_de_estado_produz_aprovado(self):
        ocorrencias = []
        for arq in (RAIZ / "shiba").glob("*.py"):
            texto = arq.read_text(encoding="utf-8")
            if 'fim("aprovado")' in texto or '"estado": "aprovado"' in texto:
                ocorrencias.append(arq.name)
        self.assertEqual(ocorrencias, ["aprovacao.py"])


def rodar(*args, ambiente=None):
    saida, erro = io.StringIO(), io.StringIO()
    env = {"SHIBA_DADOS": "", "GIT_DIR": "", "GIT_WORK_TREE": ""}
    with mock.patch.dict(os.environ, ambiente or env), contextlib.redirect_stdout(saida), \
            contextlib.redirect_stderr(erro):
        codigo = main(list(args))
    return codigo, saida.getvalue(), erro.getvalue()


class TestCli(Base):
    def base(self, *args):
        return rodar(*args, "--cliente", CLIENTE, "--estado", str(self.estado),
                     "--dir-clientes", str(self.clientes), "--data-referencia", "2026-10-23")

    def test_fluxo_pela_cli_em_simulacao(self):
        self.assertEqual(self.base("identidade", "cadastrar", "--id", "id-adm", "--papel", "resp-04",
                                   "--processo", "FICTÍCIO", "--por", "bootstrap", "--simulacao")[0], 0)
        for ident, papel in (("id-autor", "resp-01"), ("id-rev1", "resp-02"), ("id-rev2", "resp-02"),
                             ("id-val", "resp-03")):
            self.base("identidade", "cadastrar", "--id", ident, "--papel", papel, "--processo", "FICTÍCIO",
                      "--por", "id-adm", "--simulacao")
        self.base("peca", "registrar", str(self.peca), "--peca", "p1", "--tipo", "legenda",
                  "--plataforma", "instagram", "--autor", "id-autor")
        codigo, saida, _ = self.base("peca", "verificar", "--peca", "p1")
        self.assertIn("VERIFICADO", saida)
        self.assertNotIn("APROVADO", saida)
        self.base("peca", "enviar", "--peca", "p1", "--por", "id-autor")
        _, saida, _ = self.base("peca", "status", "--peca", "p1", "--formato", "json")
        for aviso in json.loads(saida)["avisos"]:
            self.base("peca", "reconhecer", "--peca", "p1", "--aviso", aviso, "--identidade", "id-rev1",
                      "--papel", "resp-02", "--justificativa", "ciente", "--simulacao")
        for rev in ("id-rev1", "id-rev2"):
            self.base("peca", "aprovar", "--peca", "p1", "--identidade", rev, "--papel", "resp-02", "--simulacao")
        _, saida, _ = self.base("peca", "validar-normativo", "--peca", "p1", "--identidade", "id-val",
                                "--papel", "resp-03", "--simulacao")
        self.assertIn("APROVADO", saida)
        self.assertIn("SIMULAÇÃO", saida)
        self.assertIn("não prova identidade", saida)
        codigo, saida, _ = self.base("peca", "liberar", "--peca", "p1", "--identidade", "id-rev1", "--simulacao")
        self.assertEqual(codigo, 0)
        self.assertIn("não autoriza publicar a peça audiovisual", saida)
        self.assertEqual(self.base("auditoria", "verificar")[0], 0)

    def test_decisao_real_sem_terminal_e_recusada(self):
        codigo, _, erro = self.base("identidade", "cadastrar", "--id", "id-adm", "--papel", "resp-04",
                                    "--processo", "x", "--por", "bootstrap")
        self.assertEqual(codigo, 2)
        self.assertIn("terminal interativo", erro)

    def test_status_com_historico_adulterado_sai_com_2(self):
        self.ate_aprovado()
        Registro(self.estado, CLIENTE).ancora.unlink()
        codigo, saida, _ = self.base("peca", "status", "--peca", "p1")
        self.assertEqual(codigo, 2)
        self.assertIn("INTEGRIDADE_NAO_CONFIRMADA", saida)


if __name__ == "__main__":
    unittest.main()
