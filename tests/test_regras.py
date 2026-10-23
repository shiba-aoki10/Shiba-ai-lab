import unittest

from apoio import cliente, fato, plataforma

from shiba.regras import (
    AVISO,
    BLOQUEANTE,
    INFO,
    regra_hashtags,
    regra_limite_caracteres,
    regra_numero_sem_fato,
    regra_palavras_proibidas,
)


def severidades(achados):
    return sorted(a.severidade for a in achados)


class TestHashtags(unittest.TestCase):
    def test_positivo_dentro_da_faixa(self):
        self.assertEqual(regra_hashtags("texto #a #b #c", cliente()), [])

    def test_negativo_abaixo_do_minimo(self):
        achados = regra_hashtags("texto #a #b", cliente())
        self.assertEqual(severidades(achados), [BLOQUEANTE])
        self.assertIn("2 hashtag(s)", achados[0].mensagem)

    def test_negativo_acima_do_maximo(self):
        achados = regra_hashtags("#a #b #c #d #e #f", cliente())
        self.assertEqual(severidades(achados), [BLOQUEANTE])

    def test_extremo_limites_exatos(self):
        self.assertEqual(regra_hashtags("#a #b #c", cliente(3, 5)), [])
        self.assertEqual(regra_hashtags("#a #b #c #d #e", cliente(3, 5)), [])

    def test_extremo_zero_hashtags_com_minimo_zero(self):
        self.assertEqual(regra_hashtags("sem hashtags", cliente(0, 5)), [])

    def test_negativo_hashtag_proibida_ignora_caixa_e_acento(self):
        achados = regra_hashtags("#a #b #SÍGAM", cliente())
        self.assertEqual(severidades(achados), [BLOQUEANTE])
        self.assertIn("#SÍGAM", achados[0].mensagem)

    def test_aviso_hashtag_repetida(self):
        achados = regra_hashtags("#pao #Pão #c", cliente())
        self.assertEqual(severidades(achados), [AVISO])

    def test_extremo_nao_conta_falsos_positivos(self):
        # C#, "#" solto, âncora de URL e e-mail não são hashtags.
        texto = "C# e # solto https://ex.invalid/#secao #a #b #c"
        self.assertEqual(regra_hashtags(texto, cliente()), [])

    def test_extremo_hashtag_com_acento_e_sublinhado(self):
        self.assertEqual(regra_hashtags("#educação #pão_de_queijo #c", cliente()), [])


class TestPalavrasProibidas(unittest.TestCase):
    def test_positivo_sem_termo(self):
        self.assertEqual(regra_palavras_proibidas("pão fresquinho", cliente()), [])

    def test_negativo_termo_presente(self):
        achados = regra_palavras_proibidas("resultado garantido", cliente())
        self.assertEqual(severidades(achados), [BLOQUEANTE])

    def test_negativo_ignora_caixa_e_acento(self):
        achados = regra_palavras_proibidas("é GARANTÍDO", cliente())
        self.assertEqual(len(achados), 1)

    def test_negativo_cada_ocorrencia_e_reportada(self):
        achados = regra_palavras_proibidas("garantido e garantido", cliente())
        self.assertEqual(len(achados), 2)

    def test_negativo_termo_dentro_de_hashtag(self):
        self.assertEqual(len(regra_palavras_proibidas("#garantido", cliente())), 1)

    def test_extremo_expressao_com_quebra_de_linha(self):
        c = cliente(palavras=("melhor do Brasil",))
        self.assertEqual(len(regra_palavras_proibidas("o melhor\ndo   brasil", c)), 1)

    def test_extremo_nao_casa_parte_de_palavra(self):
        self.assertEqual(regra_palavras_proibidas("garantidor", cliente()), [])

    def test_limitacao_nao_detecta_flexoes(self):
        # Limitação documentada: plural e feminino precisam ser cadastrados.
        self.assertEqual(regra_palavras_proibidas("garantidos, garantida", cliente()), [])

    def test_extremo_lista_vazia(self):
        self.assertEqual(regra_palavras_proibidas("garantido", cliente(palavras=())), [])

    def test_posicao_aponta_para_o_texto_original(self):
        texto = "Pão GARANTÍDO"
        a = regra_palavras_proibidas(texto, cliente())[0]
        self.assertEqual(texto[a.inicio:a.fim], "GARANTÍDO")


class TestNumeroSemFato(unittest.TestCase):
    def test_positivo_numero_com_fato(self):
        self.assertEqual(regra_numero_sem_fato("desde 2015", (fato(),)), [])

    def test_positivo_sem_numeros(self):
        self.assertEqual(regra_numero_sem_fato("pão quente", ()), [])

    def test_negativo_numero_sem_fato(self):
        achados = regra_numero_sem_fato("98% voltam", (fato(),))
        self.assertEqual(severidades(achados), [BLOQUEANTE])
        self.assertIn("nenhum fato", achados[0].mensagem)

    def test_negativo_sem_registro_de_fatos(self):
        self.assertEqual(len(regra_numero_sem_fato("são 24 horas", ())), 1)

    def test_negativo_fato_expirado_ou_contestado(self):
        for status in ("expirado", "contestado"):
            with self.subTest(status=status):
                achados = regra_numero_sem_fato("10% off", (fato(valores=("10%",), status=status),))
                self.assertEqual(len(achados), 1)
                self.assertIn(status, achados[0].mensagem)

    def test_positivo_fato_fornecido_e_aceito_no_prototipo(self):
        self.assertEqual(regra_numero_sem_fato("24 horas", (fato(valores=("24",), status="fornecido"),)), [])

    def test_extremo_formatos_equivalentes(self):
        self.assertEqual(regra_numero_sem_fato("1500 pães", (fato(valores=("1.500",)),)), [])

    def test_negativo_percentual_nao_casa_com_valor(self):
        self.assertEqual(len(regra_numero_sem_fato("30 clientes", (fato(valores=("30%",)),))), 1)

    def test_extremo_cada_ocorrencia_e_reportada(self):
        self.assertEqual(len(regra_numero_sem_fato("7 dias, 7 noites", ())), 2)

    def test_limitacao_numero_por_extenso_nao_e_detectado(self):
        # Limitação documentada.
        self.assertEqual(regra_numero_sem_fato("mais de três mil clientes", ()), [])


class TestLimiteCaracteres(unittest.TestCase):
    def test_positivo_no_limite_exato_verificado(self):
        self.assertEqual(regra_limite_caracteres("a" * 100, plataforma(100, "verificado")), [])

    def test_negativo_acima_do_limite_verificado_bloqueia(self):
        achados = regra_limite_caracteres("a" * 101, plataforma(100, "verificado"))
        self.assertEqual(severidades(achados), [BLOQUEANTE])
        self.assertIn("excede em 1", achados[0].mensagem)

    def test_negativo_limite_nao_verificado_so_avisa(self):
        achados = regra_limite_caracteres("a" * 101, plataforma(100, "a_verificar"))
        self.assertEqual(severidades(achados), [AVISO, INFO])

    def test_info_quando_limite_nao_verificado(self):
        achados = regra_limite_caracteres("curto", plataforma(100, "expirado"))
        self.assertEqual(severidades(achados), [INFO])

    def test_extremo_legenda_vazia_bloqueia(self):
        for texto in ("", "   \n "):
            with self.subTest(texto=repr(texto)):
                achados = regra_limite_caracteres(texto, plataforma())
                self.assertEqual(severidades(achados), [BLOQUEANTE])

    def test_extremo_emoji_conta_por_ponto_de_codigo(self):
        # Limitação documentada: a plataforma pode contar emoji de outro jeito.
        # "👍🏽" são 2 pontos de código; 50 deles = 100.
        self.assertEqual(regra_limite_caracteres("👍🏽" * 50, plataforma(100, "verificado")), [])


if __name__ == "__main__":
    unittest.main()
