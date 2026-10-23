import unittest

from shiba.numeros import chave_de, extrair_numeros


def brutos(texto):
    return [n.bruto for n in extrair_numeros(texto)]


class TestExtracao(unittest.TestCase):
    def test_inteiro_simples(self):
        self.assertEqual(brutos("abrimos em 2015."), ["2015"])

    def test_milhar_decimal_percentual_e_moeda(self):
        self.assertEqual(brutos("1.500 pães, 2,5 kg, 30% e R$ 49,90"),
                         ["1.500", "2,5", "30%", "49,90"])

    def test_percentual_com_espaco(self):
        self.assertEqual(brutos("cerca de 30 % menos"), ["30 %"])

    def test_texto_sem_numeros(self):
        self.assertEqual(brutos("nenhum número aqui"), [])
        self.assertEqual(brutos(""), [])

    def test_ignora_hashtag_mencao_url_e_email(self):
        texto = "#top10 @loja2024 https://ex.invalid/p/123 www.ex.invalid/9 joao2@ex.invalid"
        self.assertEqual(brutos(texto), [])

    def test_ignora_enumeracao_no_inicio_da_linha(self):
        self.assertEqual(brutos("1. primeiro\n2) segundo"), [])

    def test_enumeracao_nao_esconde_numero_real(self):
        self.assertEqual(brutos("1.500 clientes"), ["1.500"])

    def test_ignora_emoji_de_tecla(self):
        self.assertEqual(brutos("1️⃣ passo"), [])

    def test_detecta_numero_colado_em_letras(self):
        # Proposital: "covid19" e "4K" podem ser afirmações e são cobrados.
        self.assertEqual(brutos("covid19 e vídeo 4K"), ["19", "4"])

    def test_data_e_hora_sao_tokens_unicos(self):
        self.assertEqual(brutos("dia 23/10 às 18h30"), ["23/10", "18h30"])

    def test_pontuacao_final_nao_entra_no_numero(self):
        self.assertEqual(brutos("foram 24."), ["24"])

    def test_posicoes_apontam_para_o_texto_original(self):
        texto = "são 24 horas"
        n = extrair_numeros(texto)[0]
        self.assertEqual(texto[n.inicio:n.fim], "24")


class TestChave(unittest.TestCase):
    def test_milhar_e_inteiro_sao_equivalentes(self):
        self.assertEqual(chave_de("1.500"), chave_de("1500"))

    def test_zeros_a_direita_sao_equivalentes(self):
        self.assertEqual(chave_de("24,0"), chave_de("24"))

    def test_percentual_difere_de_valor(self):
        self.assertNotEqual(chave_de("30%"), chave_de("30"))
        self.assertEqual(chave_de("30 %"), chave_de("30%"))

    def test_ambiguidade_ptbr_documentada(self):
        # "1.500" é lido em pt-BR (1500), nunca como 1,5 en-US.
        self.assertEqual(chave_de("1.500"), ("valor", "1500"))
        self.assertEqual(chave_de("2.5"), ("valor", "2.5"))

    def test_data_e_comparada_literalmente(self):
        self.assertEqual(chave_de("23/10"), ("literal", "23/10"))


if __name__ == "__main__":
    unittest.main()
