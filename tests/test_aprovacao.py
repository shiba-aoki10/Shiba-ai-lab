"""Aprovação por papéis, independência e estado derivado (Incremento 4B).

Identidades, peças e clientes FICTÍCIOS, em pastas temporárias fora do Git.
Os eventos são gravados direto no registro, como a API (4C) fará.
"""
import dataclasses
import tempfile
import unittest
from datetime import date
from pathlib import Path

from apoio import FONTE, VERIFICACAO, cliente, fato_completo, plataforma

from shiba.aprovacao import (
    APROVACAO_EDITORIAL as AP,
    RECUSA_NORMATIVA as RN,
    REJEICAO_EDITORIAL as RE,
    VALIDACAO_NORMATIVA as VN,
    ErroAprovacao,
    calcular_estado,
    politica_de,
    validar_pedido,
)
from shiba.auditoria import ErroIntegridade, Registro
from shiba.config import Fato
from shiba.dependencias import avaliar, fatos_influentes
from shiba.identidades import BOOTSTRAP, ErroIdentidade, identidades, validar_cadastro

HOJE = date(2026, 10, 23)
EQUIPE = {"papeis": ["autor", "rev", "val", "adm"], "autores": ["autor"], "aprovadores": ["rev"],
          "validadores_normativos": ["val"], "cadastradores": ["adm"]}
REVISAO = {"aprovacoes_minimas": 1, "revisao_independente": True,
           "validacao_normativa_independente": True, "nivel_minimo": "declarativa",
           "exige_validacao_normativa": False, "categorias_validacao_normativa": [], "listas_validacao": []}


def cli(**revisao):
    return dataclasses.replace(cliente(minimo=0, palavras=()),
                               secoes={"equipe": dict(EQUIPE), "revisao": dict(REVISAO, **revisao),
                                       "editorial": {}})


class Fluxo:
    """Simula o que a API fará: registra eventos e calcula o estado."""

    def __init__(self, estado: Path, c=None, fatos=(), peca="p1"):
        self.reg = Registro(estado, "teste")
        self.c, self.fatos, self.peca, self.hoje = c or cli(), tuple(fatos), peca, HOJE
        self.bytes = b""
        self.versao = 0
        for ident, papeis in (("id-adm", ["adm"]), ("id-autor", ["autor"]), ("id-rev1", ["rev"]),
                              ("id-rev2", ["rev"]), ("id-val", ["val"]), ("id-revval", ["rev", "val"])):
            por = BOOTSTRAP if ident == "id-adm" else "id-adm"
            self.reg.anexar("identidade_cadastrada", {"identidade": ident, "papeis": papeis,
                                                      "processo": "FICTÍCIO: termo de teste",
                                                      "cadastrada_por": por, "simulacao": False})

    def aval(self, conteudo=None):
        return avaliar("legenda", self.bytes if conteudo is None else conteudo, None, self.c,
                       self.fatos, plataforma(), self.hoje)

    def registrar(self, conteudo: bytes, autor="id-autor"):
        self.bytes, self.versao = conteudo, self.versao + 1
        self.reg.anexar("versao_registrada", {"peca": self.peca, "versao": self.versao, "tipo": "legenda",
                                              "plataforma": "teste", "autor": autor,
                                              "hash_conteudo": self.aval().hash_conteudo, "simulacao": False})

    def _evento(self, evento, **extra):
        self.reg.anexar(evento, {"peca": self.peca, "versao": self.versao, **self.aval().hashes,
                                 "simulacao": False, **extra})

    def verificar(self):
        self._evento("verificacao", resultado=self.aval().laudo["resultado"])

    def enviar(self, por="id-autor"):
        self._evento("enviada", identidade=por)

    def decidir(self, ato, identidade, papel, validar=True):
        if validar:
            validar_pedido(self.reg.ler(), self.peca, ato, identidade, papel, self.aval().hashes,
                           self.aval(), politica_de(self.c), False)
        self._evento("decisao", ato=ato, identidade=identidade, papel=papel, nivel="declarativa")

    def reconhecer(self, aviso, identidade="id-rev1", papel="rev"):
        self._evento("aviso_reconhecido", aviso=aviso, identidade=identidade, papel=papel,
                     nivel="declarativa", justificativa="FICTÍCIO")

    def estado(self, conteudo=None):
        return calcular_estado(self.reg.ler(), self.peca, self.aval(conteudo), politica_de(self.c), False)

    def ate_revisao(self, conteudo=b"Pao quente."):
        self.registrar(conteudo)
        self.verificar()
        self.enviar()


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def fluxo(self, **kw):
        return Fluxo(self.dir, **kw)


class TestFluxoBasico(Base):
    def test_estados_em_ordem(self):
        f = self.fluxo()
        f.registrar(b"Pao quente.")
        self.assertEqual(f.estado()["estado"], "rascunho")
        f.verificar()
        self.assertEqual(f.estado()["estado"], "verificado")
        f.enviar()
        self.assertEqual(f.estado()["estado"], "aguardando_revisao")
        f.decidir(AP, "id-rev1", "rev")
        e = f.estado()
        self.assertEqual(e["estado"], "aprovado")
        self.assertEqual(e["nivel_garantia"], "declarativa")
        self.assertIn("não prova identidade", e["aviso_nivel"])

    def test_passou_nos_testes_nao_e_aprovado(self):
        f = self.fluxo()
        f.registrar(b"Pao quente.")
        f.verificar()
        self.assertEqual(f.aval().laudo["resultado"], "passou")
        self.assertNotEqual(f.estado()["estado"], "aprovado")

    def test_bloqueante_fica_em_rascunho(self):
        f = self.fluxo()
        f.ate_revisao(b"Vendemos 500 paes.")
        self.assertEqual(f.estado()["estado"], "rascunho")


class TestEdicaoPosterior(Base):
    def test_copia_da_versao_alterada_falha_fechado(self):
        f = self.fluxo()
        f.ate_revisao()
        f.decidir(AP, "id-rev1", "rev")
        with self.assertRaises(ErroIntegridade):
            f.estado(b"Pao quente!")

    def test_nova_versao_zera_aprovacoes(self):
        f = self.fluxo()
        f.ate_revisao()
        f.decidir(AP, "id-rev1", "rev")
        f.registrar(b"Pao quente!")
        e = f.estado()
        self.assertEqual((e["estado"], e["aprovacoes_editoriais"]), ("rascunho", []))

    def test_reverter_para_bytes_antigos_nao_recupera_aprovacao(self):
        f = self.fluxo()
        f.ate_revisao(b"Pao quente.")
        f.decidir(AP, "id-rev1", "rev")
        f.registrar(b"Outro texto.")
        f.ate_revisao(b"Pao quente.")      # versão 3 com os bytes da versão 1
        e = f.estado()
        self.assertEqual((e["versao"], e["estado"]), (3, "aguardando_revisao"))


class TestConfiguracaoModificada(Base):
    def test_config_alterada_invalida(self):
        f = self.fluxo()
        f.ate_revisao()
        f.decidir(AP, "id-rev1", "rev")
        f.c = dataclasses.replace(f.c, palavras_proibidas=("croissant",))
        e = f.estado()
        self.assertEqual(e["estado"], "rascunho")
        f.verificar()
        f.enviar()
        e = f.estado()
        self.assertEqual(e["estado"], "aguardando_revisao")
        self.assertTrue(any("mudaram" in d["motivo"] for d in e["descartadas"]))

    def test_politica_e_plataforma_tambem_entram_no_hash(self):
        f = self.fluxo()
        base = f.aval(b"x").hash_config
        f.c = cli(aprovacoes_minimas=2)
        self.assertNotEqual(f.aval(b"x").hash_config, base)

    def test_fato_que_influenciou_sem_alerta(self):
        """D2: fato com vínculo forte e verificado não gera achado, mas entra no hash."""
        fato = fato_completo(id="F-1", valores=("2015",), contexto=("desde",), categoria="institucional")
        f = self.fluxo(fatos=[fato])
        f.ate_revisao(b"Desde 2015, pao quente.")
        self.assertFalse(any(a["severidade"] != "info" for a in f.aval().laudo["achados"]))
        self.assertEqual(f.aval().fatos_influentes, ("F-1",))
        f.decidir(AP, "id-rev1", "rev")
        self.assertEqual(f.estado()["estado"], "aprovado")
        alterado = dataclasses.replace(fato, fonte=(("tipo", "cliente_declarou"), ("referencia", "OUTRA"),
                                                    ("informado_por", "x"), ("informado_em", "2026-10-23")))
        f.fatos = (alterado,)
        self.assertNotEqual(f.estado()["estado"], "aprovado")

    def test_fato_que_nao_influenciou_nao_entra_no_hash(self):
        usado = fato_completo(id="F-1", valores=("2015",), contexto=("desde",))
        outro = fato_completo(id="F-9", valores=("77",), contexto=("nada",))
        f = self.fluxo(fatos=[usado, outro])
        f.ate_revisao(b"Desde 2015, pao quente.")
        f.decidir(AP, "id-rev1", "rev")
        f.fatos = (usado, dataclasses.replace(outro, texto="mudou"))
        self.assertEqual(f.estado()["estado"], "aprovado")

    def test_fato_vencido_depois_da_aprovacao(self):
        fato = fato_completo(id="F-1", valores=("2015",), contexto=("desde",), status="fornecido",
                             valido_ate=date(2026, 10, 30))
        f = self.fluxo(fatos=[fato])
        f.ate_revisao(b"Desde 2015, pao quente.")
        avisos = [a for a in f.aval().laudo["achados"] if a["severidade"] == "aviso"]
        from shiba.hashes import id_do_achado
        for a in avisos:
            f.reconhecer(id_do_achado(a))
        f.decidir(AP, "id-rev1", "rev")
        self.assertEqual(f.estado()["estado"], "aprovado")
        f.hoje = date(2026, 11, 2)
        self.assertEqual(f.estado()["estado"], "rascunho")


class TestDuplicadaEConflitos(Base):
    def test_aprovacao_duplicada(self):
        f = self.fluxo(c=cli(aprovacoes_minimas=2))
        f.ate_revisao()
        f.decidir(AP, "id-rev1", "rev")
        with self.assertRaisesRegex(ErroAprovacao, "duplicada"):
            f.decidir(AP, "id-rev1", "rev")
        f.decidir(AP, "id-rev1", "rev", validar=False)   # forçada direto no registro
        e = f.estado()
        self.assertEqual((e["estado"], len(e["aprovacoes_editoriais"])), ("aguardando_revisao", 1))
        self.assertTrue(any("duplicada" in d["motivo"] for d in e["descartadas"]))
        f.decidir(AP, "id-rev2", "rev")
        self.assertEqual(f.estado()["estado"], "aprovado")

    def test_autor_nao_aprova_a_propria_peca(self):
        f = self.fluxo()
        f.registrar(b"Pao quente.", autor="id-revval")
        f.verificar()
        f.enviar("id-revval")
        with self.assertRaisesRegex(ErroAprovacao, "autor"):
            f.decidir(AP, "id-revval", "rev")
        f.decidir(AP, "id-revval", "rev", validar=False)
        self.assertEqual(f.estado()["estado"], "aguardando_revisao")

    def test_independencia_desligada_e_configuravel(self):
        f = self.fluxo(c=cli(revisao_independente=False))
        f.registrar(b"Pao quente.", autor="id-revval")
        f.verificar()
        f.enviar("id-revval")
        f.decidir(AP, "id-revval", "rev")
        self.assertEqual(f.estado()["estado"], "aprovado")

    def test_identidade_sem_o_papel(self):
        f = self.fluxo()
        f.ate_revisao()
        for identidade, papel in (("id-val", "rev"), ("id-val", "val"), ("id-rev1", "adm")):
            with self.subTest(identidade=identidade, papel=papel), self.assertRaises(ErroAprovacao):
                f.decidir(AP, identidade, papel)

    def test_identidade_revogada_perde_a_aprovacao(self):
        f = self.fluxo()
        f.ate_revisao()
        f.decidir(AP, "id-rev1", "rev")
        f.reg.anexar("identidade_revogada", {"identidade": "id-rev1", "motivo": "FICTÍCIO",
                                             "revogada_por": "id-adm"})
        self.assertEqual(f.estado()["estado"], "aguardando_revisao")

    def test_papel_retirado_da_equipe(self):
        f = self.fluxo()
        f.ate_revisao()
        f.decidir(AP, "id-rev1", "rev")
        eq = dict(EQUIPE, aprovadores=["val"])
        f.c = dataclasses.replace(f.c, secoes=dict(f.c.secoes, equipe=eq))
        self.assertNotEqual(f.estado()["estado"], "aprovado")


class TestValidacaoNormativa(Base):
    def test_exigida_pelo_cliente(self):
        f = self.fluxo(c=cli(exige_validacao_normativa=True))
        f.ate_revisao()
        f.decidir(AP, "id-rev1", "rev")
        self.assertEqual(f.estado()["estado"], "aguardando_validacao_normativa")
        f.decidir(AP, "id-revval", "rev", validar=False)   # id-revval também revisou
        with self.assertRaisesRegex(ErroAprovacao, "independente"):
            f.decidir(VN, "id-revval", "val")
        f.decidir(VN, "id-val", "val")
        e = f.estado()
        self.assertEqual(e["estado"], "aprovado")
        self.assertEqual([v["identidade"] for v in e["validacoes_normativas"]], ["id-val"])

    def test_validador_que_foi_revisor_nao_conta(self):
        f = self.fluxo(c=cli(exige_validacao_normativa=True))
        f.ate_revisao()
        f.decidir(AP, "id-revval", "rev")
        f.decidir(VN, "id-revval", "val", validar=False)
        e = f.estado()
        self.assertEqual(e["estado"], "aguardando_validacao_normativa")
        self.assertTrue(any("independente" in d["motivo"] for d in e["descartadas"]))

    def test_validador_sem_papel_e_estado_errado(self):
        f = self.fluxo(c=cli(exige_validacao_normativa=True))
        f.ate_revisao()
        with self.assertRaisesRegex(ErroAprovacao, "não aguardando"):
            f.decidir(VN, "id-val", "val")      # ainda em revisão
        f.decidir(AP, "id-rev1", "rev")
        with self.assertRaises(ErroAprovacao):
            f.decidir(VN, "id-rev2", "rev")

    def test_exigida_pelo_laudo_de_saude(self):
        c = cli(categorias_validacao_normativa=["saude"], listas_validacao=["saude"])
        f = self.fluxo(c=c)
        f.ate_revisao("Conheça o tratamento.".encode())
        self.assertTrue(f.aval().laudo["requer_validacao_normativa"])
        from shiba.hashes import id_do_achado
        for a in f.aval().laudo["achados"]:
            if a["severidade"] == "aviso":
                f.reconhecer(id_do_achado(a))
        f.decidir(AP, "id-rev1", "rev")
        self.assertEqual(f.estado()["estado"], "aguardando_validacao_normativa")

    def test_recusa_normativa_rejeita(self):
        f = self.fluxo(c=cli(exige_validacao_normativa=True))
        f.ate_revisao()
        f.decidir(AP, "id-rev1", "rev")
        f.decidir(RN, "id-val", "val")
        self.assertEqual(f.estado()["estado"], "rejeitado")


class TestOutrosCasos(Base):
    def test_rejeicao_editorial_e_nova_versao(self):
        f = self.fluxo()
        f.ate_revisao()
        f.decidir(RE, "id-rev1", "rev")
        self.assertEqual(f.estado()["estado"], "rejeitado")
        f.registrar(b"Pao quente, versao 2.")
        self.assertEqual(f.estado()["estado"], "rascunho")

    def test_avisos_precisam_ser_reconhecidos_por_revisor(self):
        f = self.fluxo()
        f.ate_revisao("No cenário atual, vale ressaltar o pão.".encode())
        f.c = dataclasses.replace(f.c, secoes=dict(f.c.secoes, editorial={"ia_por_paragrafo_aviso": 2}))
        f.verificar()
        f.enviar()
        f.decidir(AP, "id-rev1", "rev")
        e = f.estado()
        self.assertEqual(e["estado"], "aguardando_revisao")
        from shiba.hashes import id_do_achado
        avisos = [id_do_achado(a) for a in f.aval().laudo["achados"] if a["severidade"] == "aviso"]
        for a in avisos:
            f.reconhecer(a, identidade="id-autor", papel="autor")     # autor: não conta
        self.assertEqual(f.estado()["estado"], "aguardando_revisao")
        for a in avisos:
            f.reconhecer(a)
        self.assertEqual(f.estado()["estado"], "aprovado")

    def test_aprovacao_reutilizada_de_outra_peca(self):
        f = self.fluxo()
        f.ate_revisao(b"Pao quente.")
        f.decidir(AP, "id-rev1", "rev")
        aprovacao_a = [e for e in f.reg.ler() if e["evento"] == "decisao"][-1]["dados"]
        g = Fluxo.__new__(Fluxo)
        g.reg, g.c, g.fatos, g.peca, g.hoje, g.bytes, g.versao = f.reg, f.c, (), "p2", HOJE, b"", 0
        g.ate_revisao(b"Bolo de fuba.")
        copia = {k: v for k, v in aprovacao_a.items() if k != "registrado_em"}
        f.reg.anexar("decisao", dict(copia, peca="p2"))           # mesma decisão, outra peça
        e = g.estado()
        self.assertEqual(e["estado"], "aguardando_revisao")
        self.assertTrue(any("mudaram" in d["motivo"] for d in e["descartadas"]))

    def test_nivel_autenticado_exigido_falha_seguro(self):
        f = self.fluxo(c=cli(nivel_minimo="autenticada"))
        f.ate_revisao()
        with self.assertRaisesRegex(ErroAprovacao, "4D"):
            f.decidir(AP, "id-rev1", "rev")
        f.decidir(AP, "id-rev1", "rev", validar=False)
        self.assertEqual(f.estado()["estado"], "aguardando_revisao")

    def test_hashes_vistos_desatualizados(self):
        f = self.fluxo()
        f.ate_revisao()
        vistos = dict(f.aval().hashes, hash_conteudo="0" * 64)
        with self.assertRaisesRegex(ErroAprovacao, "mudaram"):
            validar_pedido(f.reg.ler(), "p1", AP, "id-rev1", "rev", vistos, f.aval(), politica_de(f.c), False)

    def test_simulacao_em_cliente_real(self):
        f = self.fluxo()
        f.ate_revisao()
        f._evento("decisao", ato=AP, identidade="id-rev1", papel="rev", nivel="declarativa")
        f.reg.anexar("decisao", {"peca": "p1", "versao": 1, **f.aval().hashes, "ato": AP,
                                 "identidade": "id-rev2", "papel": "rev", "nivel": "declarativa",
                                 "simulacao": True})
        e = f.estado()
        self.assertTrue(any("simulada" in d["motivo"] for d in e["descartadas"]))

    def test_peca_inexistente(self):
        f = self.fluxo()
        with self.assertRaises(ErroAprovacao):
            calcular_estado(f.reg.ler(), "nada", f.aval(b"x"), politica_de(f.c), False)


class TestCadastro(Base):
    PAPEIS, CAD = {"adm", "rev"}, {"adm"}

    def test_regras_de_cadastro(self):
        ids = {}
        casos = [
            ("Ana Silva", ["rev"], "x", BOOTSTRAP, "nunca um nome"),
            ("id-a", ["rev"], "x", BOOTSTRAP, "papel cadastrador"),
            ("id-a", ["inexistente"], "x", BOOTSTRAP, "papéis"),
            ("id-a", ["adm"], "  ", BOOTSTRAP, "processo"),
            ("id-a", ["adm"], "x", "id-outra", "cadastrada_por"),
            ("bootstrap", ["adm"], "x", BOOTSTRAP, "reservado"),
        ]
        for ident, papeis, proc, por, msg in casos:
            with self.subTest(ident=ident, msg=msg), self.assertRaisesRegex(ErroIdentidade, msg):
                validar_cadastro(ids, ident, papeis, proc, por, self.PAPEIS, self.CAD)
        validar_cadastro(ids, "id-a", ["adm"], "x", BOOTSTRAP, self.PAPEIS, self.CAD)

    def test_bootstrap_so_na_primeira_e_sem_autocadastro(self):
        f = self.fluxo()
        ids = identidades(f.reg.ler())
        with self.assertRaisesRegex(ErroIdentidade, "primeira"):
            validar_cadastro(ids, "id-novo", ["adm"], "x", BOOTSTRAP, self.PAPEIS, self.CAD)
        with self.assertRaisesRegex(ErroIdentidade, "já cadastrada"):
            validar_cadastro(ids, "id-rev1", ["rev"], "x", "id-adm", self.PAPEIS, self.CAD)
        with self.assertRaisesRegex(ErroIdentidade, "cadastrador"):
            validar_cadastro(ids, "id-novo", ["rev"], "x", "id-rev1", self.PAPEIS, self.CAD)
        validar_cadastro(ids, "id-novo", ["rev"], "x", "id-adm", self.PAPEIS, self.CAD)

    def test_sem_cadastradores_definidos(self):
        with self.assertRaisesRegex(ErroIdentidade, "cadastradores"):
            validar_cadastro({}, "id-a", ["adm"], "x", BOOTSTRAP, self.PAPEIS, set())


class TestDependencias(unittest.TestCase):
    def test_fatos_influentes_incluem_vinculo_sem_alerta_e_ambiguo(self):
        forte = fato_completo(id="F-1", valores=("2015",), contexto=("desde",))
        ambiguo = fato_completo(id="F-2", valores=("24",), contexto=("massa",))
        nada = fato_completo(id="F-3", valores=("99",))
        usados = fatos_influentes(["Desde 2015. Entregamos em 24 horas."], (forte, ambiguo, nada), cli(), HOJE)
        self.assertEqual([f.id for f in usados], ["F-1", "F-2"])

    def test_roteiro_com_plataforma_diferente(self):
        from shiba.config import ErroConfig
        roteiro = b'plataforma = "tiktok"\n[[cena]]\nid = "c1"\ninicio_s = 0\nfim_s = 3\nvisual = "x"\n'
        with self.assertRaisesRegex(ErroConfig, "plataforma"):
            avaliar("roteiro", roteiro, None, cli(), (), plataforma(), HOJE)


if __name__ == "__main__":
    unittest.main()
