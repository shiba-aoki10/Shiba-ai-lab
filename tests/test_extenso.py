import unittest

from shiba.afirmacoes import quantidades_extenso


def achados(texto):
    return [(q.bruto, q.chave) for q in quantidades_extenso(texto)]


class TestCardinais(unittest.TestCase):
    def test_positivo_simples_e_composto(self):
        self.assertEqual(achados("três pães e vinte e cinco bolos"),
                         [("três", ("valor", "3")), ("vinte e cinco", ("valor", "25"))])

    def test_positivo_milhares_e_milhoes(self):
        self.assertEqual(achados("dois mil e quinhentos"), [("dois mil e quinhentos", ("valor", "2500"))])
        self.assertEqual(achados("um milhão e duzentos mil"),
                         [("um milhão e duzentos mil", ("valor", "1200000"))])
        self.assertEqual(achados("mil quinhentos"), [("mil quinhentos", ("valor", "1500"))])

    def test_positivo_cento_e(self):
        self.assertEqual(achados("cento e vinte e cinco"), [("cento e vinte e cinco", ("valor", "125"))])

    def test_positivo_por_cento(self):
        self.assertEqual(achados("dez por cento"), [("dez por cento", ("percentual", "10"))])
        self.assertEqual(achados("cem por cento"), [("cem por cento", ("percentual", "100"))])

    def test_negativo_sem_numeros(self):
        self.assertEqual(achados("pão quente e café"), [])
        self.assertEqual(achados(""), [])

    def test_extremo_e_nao_une_numeros_independentes(self):
        # "entre três e cinco" são dois números, não oito.
        self.assertEqual(achados("entre três e cinco dias"),
                         [("três", ("valor", "3")), ("cinco", ("valor", "5"))])

    def test_extremo_basicos_sem_e_ficam_separados(self):
        self.assertEqual(achados("dois três"), [("dois", ("valor", "2")), ("três", ("valor", "3"))])

    def test_extremo_artigo_um_e_ignorado(self):
        self.assertEqual(achados("um pão e uma broa"), [])

    def test_extremo_palavras_parecidas_nao_casam(self):
        self.assertEqual(achados("milho, seiscentistas, dezembro, novena"), [])

    def test_extremo_virgula_interrompe(self):
        self.assertEqual(achados("vinte, e três"), [("vinte", ("valor", "20")), ("três", ("valor", "3"))])

    def test_extremo_ignora_hashtag_e_mencao(self):
        self.assertEqual(achados("#tres @dez"), [])

    def test_mistura_com_algarismos_nao_duplica(self):
        # "2 mil" é algarismo com escala; o "mil" não pode virar outro número.
        self.assertEqual(achados("2 mil clientes"), [])


class TestVagos(unittest.TestCase):
    def test_vagos_e_relativos(self):
        for texto, bruto in (("o dobro", "dobro"), ("metade do preço", "metade"),
                             ("dezenas de alunos", "dezenas"), ("milhões de pessoas", "milhões")):
            with self.subTest(texto=texto):
                self.assertEqual(achados(texto), [(bruto, None)])

    def test_vezes_mais(self):
        self.assertIn(("vezes mais", None), achados("três vezes mais sabor"))
        self.assertIn(("vezes menos", None), achados("5 vezes menos açúcar"))


if __name__ == "__main__":
    unittest.main()
