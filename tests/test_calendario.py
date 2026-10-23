"""Calendário editorial (Incremento 3C). Calendários, papéis e clientes fictícios."""
import contextlib
import dataclasses
import io
import json
import os
import re
import tempfile
import tomllib
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from apoio import cliente

from shiba.calendario import interpretar_calendario, verificar_calendario
from shiba.cli import main
from shiba.config import RAIZ, ErroConfig
from shiba.regras import AVISO, BLOQUEANTE, INFO, NORMATIVA

FIXTURES = Path(__file__).parent / "fixtures" / "sinteticos"
HOJE = date(2026, 10, 30)
PLATAFORMAS = {"instagram", "tiktok", "youtube-shorts"}
SECOES = {
    "calendario": {"status_exigem_arquivo": ["pronto", "aprovado", "agendado", "publicado"]},
    "equipe": {"papeis": ["resp-01", "resp-02", "resp-03"], "aprovadores": ["resp-02"],
               "validadores_normativos": ["resp-03"]},
    "revisao": {"exige_validacao_normativa": False},
}


def cli(**mudancas):
    secoes = {k: dict(v) for k, v in SECOES.items()}
    for chave, valor in mudancas.items():
        secao, campo = chave.split("__")
        secoes[secao][campo] = valor
    return dataclasses.replace(cliente(), secoes=secoes)


def peca(**extra):
    p = {"id": "p1", "data": date(2026, 11, 3), "plataforma": "instagram",
         "responsavel": "resp-01", "status": "planejado"}
    p.update(extra)
    return p


def laudo(*pecas, c=None, base=None):
    cal = interpretar_calendario({"inicio": date(2026, 11, 2), "fim": date(2026, 11, 8),
                                  "peca": list(pecas)})
    return verificar_calendario(cal, c or cli(), PLATAFORMAS, HOJE, base)


def achados(*pecas, **kw):
    return [(a["regra"], a["severidade"]) for a in laudo(*pecas, **kw)["achados"]]


class TestEstrutura(unittest.TestCase):
    def test_erros(self):
        casos = [
            ({"inicio": date(2026, 1, 1), "fim": date(2026, 1, 2), "pecas": []}, "desconhecida"),
            ({"fim": date(2026, 1, 2)}, "inicio"),
            ({"inicio": date(2026, 1, 5), "fim": date(2026, 1, 2)}, "anterior"),
            ({"inicio": "05/01/2026", "fim": date(2026, 1, 2)}, "AAAA-MM-DD"),
            ({"inicio": date(2026, 1, 1), "fim": date(2026, 1, 2), "peca": [{"id": "p", "dia": 1}]},
             "desconhecida"),
            ({"inicio": date(2026, 1, 1), "fim": date(2026, 1, 2), "peca": [{"id": "p"}]}, "data"),
            ({"inicio": date(2026, 1, 1), "fim": date(2026, 1, 2),
              "peca": [peca(exige_validacao_normativa="sim")]}, "true ou false"),
        ]
        for dados, msg in casos:
            with self.subTest(msg=msg), self.assertRaisesRegex(ErroConfig, msg):
                interpretar_calendario(dados)

    def test_data_e_hora_toml_nao_e_data(self):
        dados = tomllib.loads("inicio = 2026-11-02T10:00:00\nfim = 2026-11-08\n")
        with self.assertRaisesRegex(ErroConfig, "AAAA-MM-DD"):
            interpretar_calendario(dados)


class TestArquivoPorStatus(unittest.TestCase):
    def test_planejamento_nao_exige_arquivo(self):
        for status in ("ideia", "planejado", "em_producao", "em_revisao"):
            with self.subTest(status=status):
                self.assertEqual(achados(peca(status=status)), [])

    def test_pronto_sem_arquivo_bloqueia(self):
        self.assertEqual(achados(peca(status="pronto")), [("calendario_peca_incompleta", BLOQUEANTE)])

    def test_exigencia_e_configuravel(self):
        self.assertEqual(achados(peca(status="pronto"), c=cli(calendario__status_exigem_arquivo=[])), [])

    def test_arquivo_citado_inexistente(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self.assertEqual(achados(peca(arquivo="x.md"), base=base), [("calendario_arquivo", AVISO)])
            self.assertIn(("calendario_arquivo", BLOQUEANTE),
                          achados(peca(status="pronto", arquivo="x.md"), base=base))
            (base / "x.md").write_text("peça fictícia", encoding="utf-8")
            self.assertEqual(achados(peca(status="pronto", arquivo="x.md"), base=base), [])


class TestAprovacao(unittest.TestCase):
    def test_status_de_aprovacao_exige_aprovador(self):
        for status in ("aprovado", "agendado", "publicado"):
            with self.subTest(status=status):
                r = achados(peca(status=status, arquivo="", data=date(2026, 10, 29)),
                            c=cli(calendario__status_exigem_arquivo=[]))
                self.assertIn(("calendario_aprovacao", BLOQUEANTE), r)

    def test_aprovador_precisa_ter_o_papel(self):
        c = cli(calendario__status_exigem_arquivo=[])
        self.assertIn(("calendario_aprovacao", BLOQUEANTE),
                      achados(peca(status="aprovado", aprovado_por="resp-01"), c=c))
        self.assertEqual(achados(peca(status="aprovado", aprovado_por="resp-02"), c=c), [])


class TestValidacaoNormativa(unittest.TestCase):
    def c(self, exige=True):
        return cli(calendario__status_exigem_arquivo=[], revisao__exige_validacao_normativa=exige)

    def test_aprovado_sem_validacao_normativa_bloqueia(self):
        r = laudo(peca(status="aprovado", aprovado_por="resp-02"), c=self.c())
        a = next(a for a in r["achados"] if a["regra"] == "calendario_validacao_normativa")
        self.assertEqual((a["severidade"], a["natureza"]), (BLOQUEANTE, NORMATIVA))
        self.assertIn("não basta", a["mensagem"])
        self.assertTrue(r["requer_validacao_normativa"])
        self.assertIn("validacao_normativa_pelo_responsavel_competente", r["exigencias_aprovacao"])

    def test_validador_precisa_ter_o_papel(self):
        self.assertIn(("calendario_validacao_normativa", BLOQUEANTE),
                      achados(peca(status="aprovado", aprovado_por="resp-02", validado_por="resp-02"),
                              c=self.c()))
        self.assertEqual(achados(peca(status="aprovado", aprovado_por="resp-02", validado_por="resp-03"),
                                 c=self.c()), [])

    def test_planejamento_so_informa(self):
        self.assertEqual(achados(peca(), c=self.c()), [("calendario_validacao_normativa", INFO)])

    def test_exigencia_por_peca(self):
        r = achados(peca(status="aprovado", aprovado_por="resp-02", exige_validacao_normativa=True),
                    c=self.c(False))
        self.assertIn(("calendario_validacao_normativa", BLOQUEANTE), r)


class TestResponsaveis(unittest.TestCase):
    def test_ausente_malformado_e_fora_da_equipe(self):
        self.assertIn(("calendario_responsavel", BLOQUEANTE), achados(peca(responsavel="")))
        self.assertIn(("calendario_responsavel", BLOQUEANTE), achados(peca(responsavel="RESP 01")))
        self.assertIn(("calendario_responsavel", BLOQUEANTE), achados(peca(responsavel="resp-99")))

    def test_equipe_nao_configurada_avisa_uma_vez(self):
        c = cli(equipe__papeis=[], equipe__aprovadores=[], equipe__validadores_normativos=[])
        self.assertEqual(achados(peca(), peca(id="p2"), c=c), [("calendario_equipe", AVISO)])


class TestDatasEConflitos(unittest.TestCase):
    def test_datas(self):
        self.assertIn(("calendario_data", AVISO), achados(peca(data=date(2026, 11, 20))))
        self.assertIn(("calendario_data", AVISO), achados(peca(data=date(2026, 10, 1))))      # passou
        self.assertIn(("calendario_data", AVISO),
                      achados(peca(status="publicado", aprovado_por="resp-02", arquivo="",
                                   data=date(2026, 11, 4)), c=cli(calendario__status_exigem_arquivo=[])))
        self.assertIn(("calendario_data", BLOQUEANTE), achados(peca(hora="25:00")))

    def test_cancelada_e_ignorada(self):
        self.assertEqual(achados(peca(status="cancelado", data=date(2026, 1, 1), plataforma="orkut")), [])

    def test_conflito_de_horario(self):
        a, b = peca(hora="09:00"), peca(id="p2", hora="09:00")
        self.assertIn(("calendario_conflito", AVISO), achados(a, b))
        self.assertNotIn(("calendario_conflito", AVISO), achados(a, peca(id="p2", hora="10:00")))
        self.assertNotIn(("calendario_conflito", AVISO), achados(a, peca(id="p2", hora="09:00", plataforma="tiktok")))
        self.assertNotIn(("calendario_conflito", AVISO), achados(peca(), peca(id="p2")))  # sem hora
        self.assertNotIn(("calendario_conflito", AVISO), achados(a, peca(id="p2", hora="09:00", status="cancelado")))

    def test_carga_por_responsavel(self):
        pecas = [peca(id=f"p{i}") for i in range(3)]
        self.assertEqual(achados(*pecas), [])
        self.assertIn(("calendario_carga", AVISO),
                      achados(*pecas, c=cli(calendario__max_pecas_por_responsavel_dia=2)))

    def test_ids_e_status(self):
        self.assertIn(("calendario_id_repetido", BLOQUEANTE), achados(peca(), peca()))
        r = achados(peca(status="rascunho", plataforma="orkut"))
        self.assertIn(("calendario_status", BLOQUEANTE), r)
        self.assertIn(("calendario_plataforma", BLOQUEANTE), r)  # continua checando


class TestEquilibrio(unittest.TestCase):
    def test_pilares(self):
        c = cli(calendario__pilares=["produto", "bastidores"])
        r = achados(peca(pilar="produto"), peca(id="p2", pilar="receitas"), c=c)
        self.assertIn(("calendario_pilar", AVISO), r)   # pilar fora da lista
        self.assertIn(("calendario_pilar", INFO), r)    # bastidores sem peça

    def test_mesma_formula_em_dias_seguidos(self):
        r = achados(peca(gancho_formula="IG1"), peca(id="p2", data=date(2026, 11, 4), gancho_formula="IG1"))
        self.assertIn(("calendario_variedade", INFO), r)


class TestSemNomesDePessoas(unittest.TestCase):
    PAPEL = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")

    def test_modelos_e_fixtures_so_tem_papeis(self):
        arquivos = list((RAIZ / "modelos").rglob("*.toml")) + list(FIXTURES.glob("*.toml"))
        invalidos_de_proposito = {("calendario_problemas.toml", "RESP 01")}
        for arq in arquivos:
            dados = tomllib.loads(arq.read_text(encoding="utf-8"))
            valores = list(dados.get("equipe", {}).get("papeis", []))
            for p in dados.get("peca", []):
                valores += [p.get(c, "") for c in ("responsavel", "aprovado_por", "validado_por")]
            for v in filter(None, valores):
                with self.subTest(arquivo=arq.name, valor=v):
                    if (arq.name, v) not in invalidos_de_proposito:
                        self.assertTrue(self.PAPEL.fullmatch(v))


def rodar(*args):
    saida, erro = io.StringIO(), io.StringIO()
    with mock.patch.dict(os.environ, {"SHIBA_DADOS": "", "GIT_DIR": "", "GIT_WORK_TREE": ""}), \
            contextlib.redirect_stdout(saida), contextlib.redirect_stderr(erro):
        codigo = main(list(args))
    return codigo, saida.getvalue(), erro.getvalue()


class TestCli(unittest.TestCase):
    def test_fixtures(self):
        codigo, saida, _ = rodar("calendario", "verificar", str(FIXTURES / "calendario_ok.toml"),
                                 "--cliente", "exemplo-cafe", "--data-referencia", "2026-10-30",
                                 "--formato", "json")
        r = json.loads(saida)
        self.assertEqual((codigo, r["resumo"]["bloqueante"], r["metricas"]["pecas"]), (0, 0, 3))
        codigo, saida, _ = rodar("calendario", "verificar", str(FIXTURES / "calendario_problemas.toml"),
                                 "--cliente", "exemplo-cafe", "--data-referencia", "2026-10-30")
        self.assertEqual(codigo, 1)
        self.assertIn("[peça p3]", saida)


class TestIsolamento(unittest.TestCase):
    SEGREDO = "MARCADOR-SIGILOSO-CAL5"

    def setUp(self):
        from shiba.dados import repositorio_que_contem
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name).resolve()
        if repositorio_que_contem(self.tmp):
            self.skipTest("pasta temporária dentro de repositório Git")
        pasta = self.tmp / "dados" / "clientes" / "real1"
        pasta.mkdir(parents=True)
        (pasta / "perfil.toml").write_text(
            'id = "real1"\nnome = "x"\nficticio = false\nsegmento = "gastronomia"\n'
            '[equipe]\npapeis = ["resp-01"]\n', encoding="utf-8")
        (pasta / "fatos.toml").write_text("", encoding="utf-8")
        self.repo = self.tmp / "repo"
        (self.repo / ".git").mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def rodar_real(self, calendario):
        return rodar("calendario", "verificar", str(calendario), "--cliente", "real1",
                     "--dados", str(self.tmp / "dados"), "--data-referencia", "2026-10-30")

    def test_calendario_dentro_de_repositorio(self):
        cal = self.repo / "cal.toml"
        cal.write_text("inicio = 2026-11-02\nfim = 2026-11-08\n", encoding="utf-8")
        codigo, saida, erro = self.rodar_real(cal)
        self.assertEqual((codigo, saida), (2, ""))
        self.assertIn("calendário", erro)

    def test_arquivo_citado_dentro_de_repositorio(self):
        cal = self.tmp / "cal.toml"
        cal.write_text(f'inicio = 2026-11-02\nfim = 2026-11-08\n[[peca]]\nid = "p1"\n'
                       f'data = 2026-11-03\nplataforma = "instagram"\nresponsavel = "resp-01"\n'
                       f'status = "planejado"\narquivo = "{self.repo / "peca.md"}"\n', encoding="utf-8")
        codigo, _, erro = self.rodar_real(cal)
        self.assertEqual(codigo, 2)
        self.assertIn("citado", erro)

    def test_fora_do_git_funciona(self):
        cal = self.tmp / "cal.toml"
        cal.write_text('inicio = 2026-11-02\nfim = 2026-11-08\n[[peca]]\nid = "p1"\ndata = 2026-11-03\n'
                       'plataforma = "instagram"\nresponsavel = "resp-01"\nstatus = "planejado"\n',
                       encoding="utf-8")
        self.assertEqual(self.rodar_real(cal)[0], 0)

    def test_erro_nao_vaza_conteudo(self):
        cal = self.tmp / "cal.toml"
        cal.write_text(f'inicio = "{self.SEGREDO}"\nfim = 2026-11-08\n', encoding="utf-8")
        codigo, saida, erro = self.rodar_real(cal)
        self.assertEqual(codigo, 2)
        self.assertNotIn(self.SEGREDO, erro + saida)
        self.assertNotIn(str(self.tmp), erro)


if __name__ == "__main__":
    unittest.main()
