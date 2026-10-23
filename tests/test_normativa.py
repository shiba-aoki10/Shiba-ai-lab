"""Perfis futuros e validação normativa (Incremento 3D). Só dados fictícios."""
import dataclasses
import json
import re
import tempfile
import textwrap
import unittest
from datetime import date
from pathlib import Path

from apoio import cliente, fato_completo, plataforma

from shiba.calendario import interpretar_calendario, verificar_calendario
from shiba.config import RAIZ, ErroConfig, carregar_cliente, carregar_fatos, carregar_plataforma
from shiba.normativa import carregar_lista, regra_validacao_normativa
from shiba.regras import AVISO, BLOQUEANTE, NORMATIVA
from shiba.roteiro import interpretar_roteiro
from shiba.verificar import formatar_texto, verificar
from shiba.verificar_roteiro import verificar_roteiro

HOJE = date(2026, 10, 23)
REVISAO_SAUDE = {"exige_validacao_normativa": True, "categorias_validacao_normativa": ["saude"],
                 "listas_validacao": ["saude"]}


def cli_saude(**revisao):
    return dataclasses.replace(cliente(minimo=0, palavras=()),
                               secoes={"revisao": dict(REVISAO_SAUDE, **revisao), "editorial": {}})


def normativos(texto, c=None, fatos=()):
    return regra_validacao_normativa(texto, tuple(fatos), c or cli_saude(), HOJE)


class TestSegmentos(unittest.TestCase):
    def test_tres_segmentos_carregam_sem_presumir_regras(self):
        for seg in ("saude", "social", "esportivo"):
            with self.subTest(segmento=seg):
                with tempfile.TemporaryDirectory() as tmp:
                    pasta = Path(tmp) / "c1"
                    pasta.mkdir()
                    (pasta / "perfil.toml").write_text(textwrap.dedent(f"""
                        id = "c1"
                        nome = "Cliente fictício"
                        ficticio = true
                        segmento = "{seg}"
                        [hashtags]
                        minimo = 0
                        maximo = 3
                    """), encoding="utf-8")
                    c = carregar_cliente("c1", Path(tmp))
                    # nenhum segmento presume palavras proibidas
                    self.assertEqual(c.palavras_proibidas, ())
                    self.assertEqual(c.secoes["revisao"]["exige_validacao_normativa"], seg == "saude")

    def test_nenhum_cliente_futuro_cadastrado_no_repositorio(self):
        nomes = [p.name.lower() for p in (RAIZ / "modelos").rglob("*")]
        for proibido in ("medicos", "médicos", "vtc", "lntd"):
            with self.subTest(nome=proibido):
                self.assertFalse(any(proibido in n for n in nomes))

    def test_cliente_ficticio_de_saude(self):
        c = carregar_cliente("exemplo-clinica")
        self.assertTrue(c.ficticio)
        self.assertEqual(c.secoes["revisao"]["categorias_validacao_normativa"], ["saude"])
        self.assertEqual(c.secoes["equipe"]["validadores_normativos"], ["resp-03"])


class TestListasDeValidacao(unittest.TestCase):
    def test_lista_de_saude_tem_motivo_para_cada_tema(self):
        temas = carregar_lista("saude")
        self.assertGreater(len(temas), 10)
        self.assertTrue(all(t and m for t, m in temas))

    def test_lista_inexistente(self):
        with self.assertRaises(ErroConfig):
            carregar_lista("nao-existe")


class TestRegraNormativa(unittest.TestCase):
    def test_tema_da_lista(self):
        a = normativos("Veja o antes e depois.")
        self.assertEqual([(x.regra, x.severidade, x.natureza) for x in a],
                         [("validacao_normativa", AVISO, NORMATIVA)])
        self.assertIn("não avalia se é permitido", a[0].mensagem)

    def test_marcador_de_saude(self):
        self.assertEqual(len(normativos("Ajuda a prevenir resfriados.")), 1)

    def test_fato_verificado_nao_dispensa_validacao(self):
        f = fato_completo(valores=("40",), categoria="saude", contexto=("consulta*",), unidade="minuto")
        a = normativos("A consulta dura 40 minutos.", fatos=[f])
        self.assertTrue(any("não substitui" in x.mensagem for x in a))

    def test_cliente_sem_exigencia_nao_gera_nada(self):
        c = dataclasses.replace(cliente(), secoes={})
        self.assertEqual(normativos("Veja o antes e depois do tratamento.", c), [])

    def test_texto_neutro(self):
        self.assertEqual(normativos("Abrimos às sete."), [])

    def test_mesmo_trecho_nao_duplica(self):
        a = normativos("Resultado garantido no tratamento.")
        posicoes = [(x.inicio, x.fim) for x in a]
        self.assertEqual(len(posicoes), len(set(posicoes)))

    def test_prefixo_mostra_palavra_inteira(self):
        texto = "Fale com nossos especialistas."
        a = normativos(texto)[0]
        self.assertEqual(texto[a.inicio:a.fim], "especialistas")


class TestLaudos(unittest.TestCase):
    def test_legenda_de_saude_nunca_fica_apta_so_pelo_tecnico(self):
        laudo = verificar("Conheça nosso tratamento.", cli_saude(), (), plataforma(), HOJE)
        self.assertEqual(laudo["resultado"], "passou")          # nada técnico bloqueia
        self.assertTrue(laudo["requer_validacao_normativa"])
        self.assertEqual(laudo["status_maximo"], "aguardando_validacao_normativa")
        self.assertIn("validacao_normativa_pelo_responsavel_competente", laudo["exigencias_aprovacao"])
        self.assertIn("NÃO pode ser aprovada", formatar_texto(laudo))

    def test_status_maximo_nunca_e_aprovado(self):
        for texto in ("Pão quente.", "Conheça nosso tratamento.", "98% garantido"):
            laudo = verificar(texto, cli_saude(), (), plataforma(), HOJE)
            self.assertNotIn("aprov", laudo["status_maximo"].replace("aprovacao", ""))
        self.assertEqual(verificar("Pão quente.", cliente(minimo=0), (), plataforma(), HOJE)["status_maximo"],
                         "aguardando_aprovacao_humana")

    def test_normas_registradas_aparecem_sem_interpretacao(self):
        c = carregar_cliente("exemplo-clinica", plataforma="instagram")
        laudo = verificar("Agende sua consulta.", c, carregar_fatos("exemplo-clinica"),
                          carregar_plataforma("instagram"), HOJE)
        self.assertEqual(laudo["normas_registradas"][0]["status"], "a_verificar")
        json.dumps(laudo)

    def test_roteiro_de_saude(self):
        r = interpretar_roteiro({"plataforma": "tiktok", "cena": [
            {"id": "c1", "inicio_s": 0, "fim_s": 5, "visual": "consultório", "fala": "Veja o antes e depois."}]})
        laudo = verificar_roteiro(r, cli_saude(), (), carregar_plataforma("tiktok"), HOJE)
        a = next(a for a in laudo["achados"] if a["natureza"] == NORMATIVA)
        self.assertEqual(a["local"], "cena c1 · fala")
        self.assertEqual(laudo["status_maximo"], "aguardando_validacao_normativa")

    def test_calendario_herda_exigencia_do_segmento(self):
        c = carregar_cliente("exemplo-clinica")
        cal = interpretar_calendario({"inicio": date(2026, 11, 2), "fim": date(2026, 11, 8), "peca": [
            {"id": "p1", "data": date(2026, 11, 3), "plataforma": "instagram", "responsavel": "resp-01",
             "status": "aprovado", "aprovado_por": "resp-02", "arquivo": ""}]})
        dados = dataclasses.replace(c, secoes=dict(c.secoes, calendario={"status_exigem_arquivo": []}))
        laudo = verificar_calendario(cal, dados, {"instagram"}, HOJE)
        self.assertIn(("calendario_validacao_normativa", BLOQUEANTE),
                      [(a["regra"], a["severidade"]) for a in laudo["achados"]])


class TestNormasCadastradas(unittest.TestCase):
    def carregar(self, referencias):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp) / "c1"
            pasta.mkdir()
            (pasta / "perfil.toml").write_text(textwrap.dedent(f"""
                id = "c1"
                nome = "Cliente fictício"
                ficticio = true
                segmento = "saude"
                [hashtags]
                minimo = 0
                maximo = 3
                [normas]
                referencias = {referencias}
            """), encoding="utf-8")
            return carregar_cliente("c1", Path(tmp))

    def test_validacoes(self):
        casos = {
            '[{ titulo = "x", status = "verificado" }]': "exige fonte",
            '[{ titulo = "x", status = "vigente" }]': "status",
            '[{ status = "a_verificar" }]': "titulo",
            '[{ titulo = "x", status = "a_verificar", artigo = "1" }]': "campos",
        }
        for refs, msg in casos.items():
            with self.subTest(refs=refs), self.assertRaisesRegex(ErroConfig, msg):
                self.carregar(refs)

    def test_referencia_valida(self):
        c = self.carregar('[{ titulo = "FICTÍCIO", status = "verificado", fonte = "https://exemplo.invalid", '
                          'consultado_em = "2026-10-23", verificado_por = "resp-03" }]')
        self.assertEqual(len(c.secoes["normas"]["referencias"]), 1)

    def test_lista_e_categoria_invalidas(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp) / "c1"
            pasta.mkdir()
            base = 'id = "c1"\nnome = "x"\nficticio = true\n[hashtags]\nminimo = 0\nmaximo = 3\n[revisao]\n'
            for extra, msg in (('listas_validacao = ["inventada"]', "inexistente"),
                               ('categorias_validacao_normativa = ["juridica"]', "desconhecida")):
                (pasta / "perfil.toml").write_text(base + extra + "\n", encoding="utf-8")
                with self.subTest(extra=extra), self.assertRaisesRegex(ErroConfig, msg):
                    carregar_cliente("c1", Path(tmp))


class TestMotorNaoFazConclusaoJuridica(unittest.TestCase):
    """Nenhum texto que o motor pode exibir afirma o que a lei permite ou proíbe."""
    PADROES = [
        r"(proibid|permitid)[oa]s?\s+por\s+lei",
        r"(proibid|permitid)[oa]s?\s+pel[oa]\s+(cfm|crm|anvisa|conselho|lei|resolu)",
        # "se é permitido" / "o que é permitido" são ressalvas, não conclusões.
        r"(?<!\bse )(?<!\bque )\b(é|e)\s+(ilegal|legal|permitido)\b",
        r"resolu[cç][aã]o\s+(cfm|crm|n[º°o.]?\s*\d)",
        r"\blei\s+n[º°o.]?\s*\d",
        r"(segundo|conforme|de acordo com)\s+(a|o)\s+(lei|resolu|cfm|crm|anvisa|c[oó]digo de [ée]tica)",
        r"(anvisa|cfm|crm)\s+(permite|pro[ií]be|autoriza|veda)",
    ]

    def test_o_detector_pega_conclusoes_e_ignora_ressalvas(self):
        conclusoes = ["isso é permitido", "anúncio é ilegal", "proibido por lei",
                      "segundo a resolução 123", "conforme o CFM", "a ANVISA proíbe", "lei nº 1"]
        ressalvas = ["o motor não avalia se é permitido", "não diz o que é permitido"]
        def acha(t):
            return any(re.search(p, t.lower()) for p in self.PADROES)
        for t in conclusoes:
            with self.subTest(conclusao=t):
                self.assertTrue(acha(t))
        for t in ressalvas:
            with self.subTest(ressalva=t):
                self.assertFalse(acha(t))

    def test_codigo_conhecimento_e_modelos(self):
        arquivos = (list((RAIZ / "shiba").glob("*.py")) + list((RAIZ / "conhecimento").rglob("*.toml"))
                    + list((RAIZ / "modelos").rglob("*.toml")))
        for arq in arquivos:
            texto = arq.read_text(encoding="utf-8").lower()
            for padrao in self.PADROES:
                with self.subTest(arquivo=arq.name, padrao=padrao):
                    self.assertIsNone(re.search(padrao, texto))


if __name__ == "__main__":
    unittest.main()
