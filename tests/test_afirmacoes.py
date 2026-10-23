import unittest
from datetime import date

from apoio import fato_completo

from shiba.afirmacoes import (
    frases,
    marcadores,
    quantidades,
    quantidades_algarismos,
    status_efetivo,
    vincular_quantidade,
)

HOJE = date(2026, 10, 23)


def vinculo(texto, fatos, indice=0):
    q = quantidades(texto)[indice]
    return vincular_quantidade(texto, q, tuple(fatos), HOJE)


class TestUnidadesEEscalas(unittest.TestCase):
    def test_unidades_reconhecidas(self):
        casos = {"24 horas": "hora", "18h": "hora", "2 kg de farinha": "kg",
                 "R$ 49,90": "brl", "R$12": "brl", "7 dias": "dia", "30 minutos": "minuto"}
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(quantidades_algarismos(texto)[0].unidade, esperado)

    def test_sem_unidade(self):
        for texto in ("desde 2015, a casa", "3 clientes", "4K"):
            with self.subTest(texto=texto):
                self.assertIsNone(quantidades_algarismos(texto)[0].unidade)

    def test_escala_apos_algarismo(self):
        q = quantidades_algarismos("2 mil alunos")[0]
        self.assertEqual((q.bruto, q.chave), ("2 mil", ("valor", "2000")))
        q = quantidades_algarismos("1,5 milhão")[0]
        self.assertEqual(q.chave, ("valor", "1500000"))


class TestEstruturais(unittest.TestCase):
    def test_positivo_numero_editorial(self):
        for texto in ("5 dicas para", "3 erros que", "parte 2", "top 10", "três passos"):
            with self.subTest(texto=texto):
                self.assertTrue(quantidades(texto)[0].estrutural)

    def test_negativo_numero_factual(self):
        for texto in ("5 clientes", "3 unidades", "24 horas"):
            with self.subTest(texto=texto):
                self.assertFalse(quantidades(texto)[0].estrutural)

    def test_limitacao_adjetivo_no_meio(self):
        # Limitação documentada: "3 grandes erros" não é reconhecido como editorial.
        self.assertFalse(quantidades("3 grandes erros")[0].estrutural)


class TestFrasesEStatus(unittest.TestCase):
    def test_frases_respeitam_decimais(self):
        texto = "Custa 1.500 reais. Aberto às 18h!\nOutra linha"
        self.assertEqual([texto[a:b] for a, b in frases(texto)],
                         ["Custa 1.500 reais.", "Aberto às 18h!", "Outra linha"])

    def test_validade_vencida_vira_expirado(self):
        f = fato_completo(status="fornecido", valido_ate=date(2026, 10, 22))
        self.assertEqual(status_efetivo(f, HOJE), "expirado")
        self.assertEqual(status_efetivo(f, date(2026, 10, 22)), "fornecido")  # último dia vale

    def test_contestado_nao_muda(self):
        self.assertEqual(status_efetivo(fato_completo(status="contestado"), HOJE), "contestado")


class TestVinculo(unittest.TestCase):
    def test_forte_valor_unidade_e_contexto(self):
        f = fato_completo(contexto=("massa",), unidade="hora")
        self.assertEqual(vinculo("A massa descansa 24 horas.", [f]).situacao, "forte")

    def test_ambiguo_sem_contexto_na_frase(self):
        f = fato_completo(contexto=("massa",))
        self.assertEqual(vinculo("Entregamos em 24 horas.", [f]).situacao, "ambiguo")

    def test_ambiguo_quando_fato_nao_tem_contexto(self):
        f = fato_completo(contexto=())
        self.assertEqual(vinculo("A massa descansa 24 horas.", [f]).situacao, "ambiguo")

    def test_contexto_de_outra_frase_nao_conta(self):
        f = fato_completo(contexto=("massa",))
        self.assertEqual(vinculo("Nossa massa é caseira. Entregamos em 24 horas.", [f]).situacao,
                         "ambiguo")

    def test_unidade_divergente(self):
        f = fato_completo(contexto=("massa",), unidade="hora")
        self.assertEqual(vinculo("A massa descansa 24 dias.", [f]).situacao, "unidade_divergente")

    def test_sem_unidade_na_legenda_e_compativel(self):
        f = fato_completo(contexto=("massa",), unidade="hora")
        self.assertEqual(vinculo("A massa: 24, sempre.", [f]).situacao, "forte")

    def test_invalido_e_sem_fato(self):
        self.assertEqual(vinculo("massa 24", [fato_completo(status="contestado")]).situacao, "invalido")
        self.assertEqual(vinculo("massa 25", [fato_completo()]).situacao, "sem_fato")

    def test_verificado_tem_prioridade(self):
        fornecido = fato_completo(id="F-1", status="fornecido")
        verificado = fato_completo(id="F-2", status="verificado")
        v = vinculo("A massa descansa 24 horas.", [fornecido, verificado])
        self.assertEqual(v.fatos[0].id, "F-2")

    def test_extenso_casa_com_algarismo(self):
        f = fato_completo(valores=("3",), contexto=("unidade*",))
        self.assertEqual(vinculo("Temos três unidades.", [f]).situacao, "forte")

    def test_contexto_por_prefixo_e_sem_acento(self):
        f = fato_completo(contexto=("ferment*",))
        self.assertEqual(vinculo("FERMENTAÇÃO de 24 horas", [f]).situacao, "forte")


class TestMarcadores(unittest.TestCase):
    def test_forte_e_fraco(self):
        ms = {(m.categoria, m.forca) for m in marcadores("Resultado garantido e o melhor sabor")}
        self.assertIn(("resultado", "forte"), ms)
        self.assertIn(("comparativo", "fraco"), ms)

    def test_fraco_dentro_de_forte_e_descartado(self):
        ms = marcadores("o melhor do bairro")
        self.assertEqual([(m.forca, m.termo) for m in ms], [("forte", "melhor do bairro")])

    def test_ignora_hashtag(self):
        self.assertEqual(marcadores("#resultadogarantido #melhor"), [])

    def test_categoria_desligada_pelo_cliente(self):
        self.assertEqual(marcadores("o melhor pão", categorias=("saude",)), [])


if __name__ == "__main__":
    unittest.main()
