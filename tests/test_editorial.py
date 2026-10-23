"""Revisor editorial pt-BR (Incremento 3A). Textos fictícios."""
import json
import tempfile
import textwrap
import unittest
from pathlib import Path

from apoio import cliente, plataforma

from shiba.config import ErroConfig, carregar_cliente
from shiba.editorial import revisar
from shiba.lexico import carregar_lexico_editorial
from shiba.regras import AVISO, BLOQUEANTE, INFO, REVISAO
from shiba.verificar import formatar_texto, verificar

LEX = carregar_lexico_editorial()
PADRAO = {"ia_por_paragrafo_aviso": 2, "frase_max_palavras": 30, "paragrafo_max_frases": 5,
          "repeticao_min": 3, "palavra_min_letras": 4, "mente_max_por_frase": 1,
          "caixa_alta_min_palavras": 3}


def regras(texto, config=PADRAO):
    return [(a.regra, a.severidade) for a in revisar(texto, config, LEX)]


class TestLexico(unittest.TestCase):
    def test_toda_entrada_e_explicavel_e_nunca_bloqueia(self):
        self.assertGreater(len(LEX.expressoes), 30)
        for e in LEX.expressoes:
            with self.subTest(termo=e.termo):
                self.assertTrue(e.justificativa and e.sugestao)
                self.assertIn(e.severidade, (INFO, AVISO))
                self.assertIn(e.categoria, ("ia", "cliche", "muleta"))

    def _lexico(self, conteudo):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        caminho = Path(tmp.name) / "lex.toml"
        caminho.write_text(textwrap.dedent(conteudo), encoding="utf-8")
        carregar_lexico_editorial.cache_clear()
        self.addCleanup(carregar_lexico_editorial.cache_clear)
        return carregar_lexico_editorial(str(caminho))

    def test_entrada_sem_justificativa_e_recusada(self):
        with self.assertRaisesRegex(ErroConfig, "justificativa"):
            self._lexico('[[expressao]]\ntermo = "x"\ncategoria = "ia"\nsugestao = "y"\n')

    def test_severidade_bloqueante_e_recusada(self):
        with self.assertRaisesRegex(ErroConfig, "severidade"):
            self._lexico('[[expressao]]\ntermo = "x"\ncategoria = "ia"\njustificativa = "j"\n'
                         'sugestao = "s"\nseveridade = "bloqueante"\n')

    def test_termo_repetido_e_categoria_invalida(self):
        bloco = '[[expressao]]\ntermo = "Já"\ncategoria = "ia"\njustificativa = "j"\nsugestao = "s"\n'
        with self.assertRaisesRegex(ErroConfig, "repetido"):
            self._lexico(bloco + bloco.replace("Já", "ja"))
        with self.assertRaisesRegex(ErroConfig, "categoria"):
            self._lexico(bloco.replace('"ia"', '"proibida"'))


class TestExpressoes(unittest.TestCase):
    def test_uma_expressao_e_so_info(self):
        self.assertEqual(regras("Vale ressaltar que abrimos cedo."), [("editorial_ia", INFO)])

    def test_acumulo_no_paragrafo_vira_aviso(self):
        self.assertEqual(regras("No cenário atual, vale ressaltar que abrimos cedo."),
                         [("editorial_ia", AVISO), ("editorial_ia", AVISO)])

    def test_acumulo_em_paragrafos_diferentes_continua_info(self):
        self.assertEqual(regras("No cenário atual, abrimos.\n\nVale ressaltar o horário."),
                         [("editorial_ia", INFO), ("editorial_ia", INFO)])

    def test_sem_limiar_configurado_nunca_vira_aviso(self):
        self.assertEqual(regras("No cenário atual, vale ressaltar.", {}),
                         [("editorial_ia", INFO), ("editorial_ia", INFO)])

    def test_cliche_e_muleta(self):
        self.assertEqual(sorted(regras("Basicamente um divisor de águas.")),
                         [("editorial_cliche", INFO), ("editorial_muleta", INFO)])

    def test_prefixo_mostra_palavra_inteira(self):
        a = revisar("Isso potencializa tudo.", PADRAO, LEX)[0]
        self.assertEqual("Isso potencializa tudo."[a.inicio:a.fim], "potencializa")

    def test_sem_acento_e_maiusculas(self):
        self.assertEqual(regras("NO CENARIO ATUAL", {}), [("editorial_ia", INFO)])

    def test_texto_limpo_nao_gera_alerta(self):
        self.assertEqual(regras("Pão quentinho às sete. Passa aqui."), [])

    def test_hashtag_url_e_mencao_sao_ignoradas(self):
        self.assertEqual(regras("#jornada @jornada https://ex.invalid/jornada"), [])

    def test_termos_ignorados_e_extras_do_cliente(self):
        cfg = dict(PADRAO, termos_ignorados=["jornada"], termos_extras=["fornada"])
        self.assertEqual(regras("Nossa jornada começa na fornada.", cfg),
                         [("editorial_termos_cliente", INFO)])

    def test_regras_desativadas(self):
        cfg = dict(PADRAO, regras_desativadas=["ia", "cliche"])
        self.assertEqual(regras("No cenário atual, um divisor de águas.", cfg), [])


class TestEstrutura(unittest.TestCase):
    def test_frase_longa_limite_exato_e_acima(self):
        cfg = {"frase_max_palavras": 5}
        self.assertEqual(regras("um dois três quatro cinco.", cfg), [])
        self.assertEqual(regras("um dois três quatro cinco seis.", cfg),
                         [("editorial_frase_longa", AVISO)])

    def test_paragrafo_longo(self):
        cfg = {"paragrafo_max_frases": 2}
        self.assertEqual(regras("Um. Dois.", cfg), [])
        self.assertEqual(regras("Um. Dois. Três.", cfg), [("editorial_paragrafo_longo", INFO)])

    def test_repeticao_de_palavra(self):
        cfg = {"repeticao_min": 3, "palavra_min_letras": 4}
        self.assertEqual(regras("massa, massa e massa", cfg), [("editorial_repeticao_palavra", AVISO)])
        self.assertEqual(regras("massa e massa", cfg), [])
        # palavras curtas e stopwords não contam
        self.assertEqual(regras("pão pão pão; para para para", cfg), [])
        # em parágrafos diferentes não acumula
        self.assertEqual(regras("massa massa\n\nmassa", cfg), [])

    def test_repeticao_sem_acento(self):
        self.assertEqual(regras("Fermentação, fermentacao, FERMENTAÇÃO.",
                                {"repeticao_min": 3}), [("editorial_repeticao_palavra", AVISO)])

    def test_repeticao_de_inicio_de_frase(self):
        cfg = {"repeticao_min": 3}
        self.assertEqual(regras("Nosso pão. Nosso café. Nosso bolo.", cfg),
                         [("editorial_repeticao_inicio", AVISO)])
        self.assertEqual(regras("Nosso pão. Nosso café. Seu bolo.", cfg), [])

    def test_adverbios_mente_e_verbos_parecidos(self):
        cfg = {"mente_max_por_frase": 1}
        self.assertEqual(regras("Rapidamente e facilmente feito.", cfg),
                         [("editorial_adverbios_mente", INFO)])
        # "comente" e "experimente" não são advérbios
        self.assertEqual(regras("Comente e experimente rapidamente.", cfg), [])

    def test_pontuacao(self):
        self.assertEqual(regras("Corre!! Sério?! Bom....", {}), [("editorial_pontuacao", INFO)] * 3)
        self.assertEqual(regras("Corre! Sério? Bom...", {}), [])

    def test_caixa_alta(self):
        cfg = {"caixa_alta_min_palavras": 3}
        self.assertEqual(regras("VEM PROVAR HOJE", cfg), [("editorial_caixa_alta", INFO)])
        self.assertEqual(regras("A ONU e o SUS hoje", cfg), [])
        self.assertEqual(regras("VEM PROVAR\nHOJE", cfg), [])  # quebra de linha separa

    def test_texto_vazio(self):
        self.assertEqual(regras(""), [])


class TestPropriedades(unittest.TestCase):
    TEXTOS = (
        "No cenário atual, vale ressaltar que é importante destacar a jornada!! VEM VER JÁ AGORA.",
        "massa massa massa. Nosso. Nosso. Nosso. Rapidamente e facilmente, basicamente.",
        "",
    )

    def test_nenhum_alerta_editorial_bloqueia_e_todos_sao_explicaveis(self):
        for texto in self.TEXTOS:
            for a in revisar(texto, PADRAO, LEX):
                with self.subTest(regra=a.regra):
                    self.assertNotEqual(a.severidade, BLOQUEANTE)
                    self.assertEqual(a.natureza, REVISAO)
                    self.assertTrue(a.justificativa and a.sugestao)
                    self.assertTrue(a.regra.startswith("editorial_"))


class TestHerancaEditorial(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def carregar(self, editorial):
        pasta = self.dir / "c1"
        pasta.mkdir(exist_ok=True)
        (pasta / "perfil.toml").write_text(textwrap.dedent("""
            id = "c1"
            nome = "Cliente fictício"
            ficticio = true
            [hashtags]
            minimo = 0
            maximo = 5
            [palavras_proibidas]
            termos = []
            [editorial]
        """) + textwrap.dedent(editorial), encoding="utf-8")
        return carregar_cliente("c1", self.dir)

    def test_padrao_e_herdado_e_cliente_ajusta(self):
        c = self.carregar("frase_max_palavras = 12\nregras_desativadas = [\"muleta\"]\n")
        ed = c.secoes["editorial"]
        self.assertEqual(ed["frase_max_palavras"], 12)       # cliente
        self.assertEqual(ed["repeticao_min"], 3)              # padrão
        self.assertEqual(ed["regras_desativadas"], ["muleta"])

    def test_valores_invalidos(self):
        casos = {
            'frase_max_palavras = "trinta"': "deve ser int",
            "frase_max_palavras = 0": "positivo",
            'regras_desativadas = ["muletas"]': "regra desconhecida",
            "termos_extras = [\"\"]": "não vazios",
            "limiar_inventado = 3": "desconhecida",
        }
        for linha, msg in casos.items():
            with self.subTest(linha=linha), self.assertRaisesRegex(ErroConfig, msg):
                self.carregar(linha + "\n")


class TestLaudo(unittest.TestCase):
    def laudo(self, texto):
        return verificar(texto, cliente(minimo=0), (), plataforma())

    def test_campos_novos(self):
        laudo = self.laudo("No cenário atual, vale ressaltar.")
        self.assertTrue(all("natureza" in a for a in laudo["achados"]))
        self.assertEqual(laudo["por_natureza"]["revisao_humana"], 2)
        self.assertIn("aprovacao_humana", laudo["exigencias_aprovacao"])
        self.assertFalse(laudo["requer_validacao_normativa"])
        self.assertTrue(any("imagem, áudio e vídeo" in t.lower()
                            for t in laudo["limites_da_verificacao"]))
        json.dumps(laudo)  # serializável

    def test_aprovacao_humana_sempre_exigida_mesmo_sem_achados(self):
        self.assertEqual(self.laudo("Pão quente.")["exigencias_aprovacao"], ["aprovacao_humana"])

    def test_texto_mostra_sugestao_e_limite(self):
        saida = formatar_texto(self.laudo("Vale ressaltar o pão."))
        self.assertIn("sugestão:", saida)
        self.assertIn("<revisao_humana>", saida)
        self.assertIn("imagem, áudio e vídeo não foram analisados", saida)


if __name__ == "__main__":
    unittest.main()
