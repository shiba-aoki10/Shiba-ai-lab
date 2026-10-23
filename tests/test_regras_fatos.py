"""Regras do Incremento 1: positivos, negativos e extremos."""
import unittest
from datetime import date

from apoio import cliente, fato_completo

from shiba.regras import (
    AVISO,
    BLOQUEANTE,
    regra_afirmacoes_sensiveis,
    regra_numero_por_extenso,
    regra_numero_sem_fato,
    regra_palavras_proibidas,
    regra_vinculo_fatos,
)

HOJE = date(2026, 10, 23)


def resumo(achados):
    return sorted((a.regra, a.severidade) for a in achados)


class TestNumeroSemFatoIncremento1(unittest.TestCase):
    def test_editorial_vira_aviso(self):
        self.assertEqual(resumo(regra_numero_sem_fato("5 dicas para dormir bem", (), HOJE)),
                         [("numero_sem_fato", AVISO)])

    def test_editorial_com_valor_de_fato_nao_gera_aviso_aqui(self):
        f = fato_completo(valores=("5",))
        self.assertEqual(regra_numero_sem_fato("5 dicas", (f,), HOJE), [])

    def test_validade_vencida_bloqueia(self):
        f = fato_completo(status="fornecido", valido_ate=date(2026, 1, 1))
        achados = regra_numero_sem_fato("massa 24", (f,), HOJE)
        self.assertEqual(resumo(achados), [("numero_sem_fato", BLOQUEANTE)])
        self.assertIn("expirado", achados[0].mensagem)

    def test_escala_mista(self):
        f = fato_completo(valores=("2.000",), contexto=("aluno*",))
        self.assertEqual(regra_numero_sem_fato("2 mil alunos", (f,), HOJE), [])


class TestNumeroPorExtenso(unittest.TestCase):
    def test_positivo_com_fato(self):
        f = fato_completo(valores=("3",), contexto=("unidade*",))
        self.assertEqual(regra_numero_por_extenso("três unidades", (f,), HOJE), [])

    def test_negativo_sem_fato(self):
        self.assertEqual(resumo(regra_numero_por_extenso("mais de três mil clientes", (), HOJE)),
                         [("numero_por_extenso", BLOQUEANTE)])

    def test_negativo_fato_contestado(self):
        f = fato_completo(valores=("3",), status="contestado")
        self.assertEqual(resumo(regra_numero_por_extenso("três unidades", (f,), HOJE)),
                         [("numero_por_extenso", BLOQUEANTE)])

    def test_vago_pede_revisao(self):
        self.assertEqual(resumo(regra_numero_por_extenso("o dobro de sabor", (), HOJE)),
                         [("quantidade_vaga", AVISO)])

    def test_extremo_editorial_por_extenso(self):
        self.assertEqual(resumo(regra_numero_por_extenso("três dicas", (), HOJE)),
                         [("numero_por_extenso", AVISO)])

    def test_extremo_sem_numero(self):
        self.assertEqual(regra_numero_por_extenso("um pão quentinho", (), HOJE), [])


class TestVinculoFatos(unittest.TestCase):
    def test_positivo_verificado_com_contexto(self):
        f = fato_completo(status="verificado", contexto=("massa",), unidade="hora")
        self.assertEqual(regra_vinculo_fatos("A massa descansa 24 horas.", (f,), cliente(), HOJE), [])

    def test_fornecido_exige_reconhecimento(self):
        f = fato_completo(status="fornecido", contexto=("massa",))
        self.assertEqual(resumo(regra_vinculo_fatos("A massa descansa 24 horas.", (f,), cliente(), HOJE)),
                         [("fato_nao_verificado", AVISO)])

    def test_ambiguo_pede_revisao(self):
        f = fato_completo(contexto=("massa",))
        self.assertEqual(resumo(regra_vinculo_fatos("Entregamos em 24 horas.", (f,), cliente(), HOJE)),
                         [("vinculo_fato", AVISO)])

    def test_unidade_divergente_bloqueia(self):
        f = fato_completo(contexto=("massa",), unidade="hora")
        self.assertEqual(resumo(regra_vinculo_fatos("A massa descansa 24 dias.", (f,), cliente(), HOJE)),
                         [("vinculo_fato", BLOQUEANTE)])

    def test_fato_sem_fonte_bloqueia(self):
        f = fato_completo(status="fornecido", com_fonte=False)
        self.assertEqual(resumo(regra_vinculo_fatos("massa de 24 horas", (f,), cliente(), HOJE)),
                         [("fato_sem_fonte", BLOQUEANTE)])

    def test_sensivel_fornecido_bloqueia(self):
        f = fato_completo(status="fornecido", categoria="saude", contexto=("reabilita*",))
        self.assertEqual(
            resumo(regra_vinculo_fatos("Reabilitação em 24 semanas.", (f,), cliente(), HOJE)),
            [("afirmacao_sensivel", BLOQUEANTE)])

    def test_sensivel_verificado_passa(self):
        f = fato_completo(status="verificado", categoria="saude", contexto=("reabilita*",))
        self.assertEqual(regra_vinculo_fatos("Reabilitação em 24 semanas.", (f,), cliente(), HOJE), [])

    def test_extremo_sem_fato_nao_e_problema_desta_regra(self):
        # "sem fato" é responsabilidade de numero_sem_fato; aqui não duplica.
        self.assertEqual(regra_vinculo_fatos("98% voltam", (), cliente(), HOJE), [])


class TestAfirmacoesSensiveis(unittest.TestCase):
    def test_positivo_sem_marcadores(self):
        self.assertEqual(regra_afirmacoes_sensiveis("Pão quentinho às 7h.", (), cliente(), HOJE), [])

    def test_promessa_forte_bloqueia(self):
        self.assertEqual(resumo(regra_afirmacoes_sensiveis("Sabor garantido!", (), cliente(), HOJE)),
                         [("promessa_resultado", BLOQUEANTE)])

    def test_saude_forte_bloqueia(self):
        self.assertEqual(resumo(regra_afirmacoes_sensiveis("Esse chá cura a gripe.", (), cliente(), HOJE)),
                         [("afirmacao_sensivel", BLOQUEANTE)])

    def test_fraco_pede_revisao(self):
        self.assertEqual(resumo(regra_afirmacoes_sensiveis("O melhor jeito de guardar pão.", (), cliente(), HOJE)),
                         [("afirmacao_sensivel", AVISO)])

    def test_apoiado_por_fato_verificado_da_categoria(self):
        f = fato_completo(valores=(), status="verificado", categoria="comparativo",
                          contexto=("bairro",), texto="Somos a maior do bairro.")
        self.assertEqual(regra_afirmacoes_sensiveis("A maior do bairro.", (f,), cliente(), HOJE), [])

    def test_fato_que_nao_afirma_a_mesma_coisa_nao_apoia(self):
        # Mesma categoria e mesmo contexto, mas o fato não fala em "garantido".
        f = fato_completo(valores=("80%",), status="verificado", categoria="resultado",
                          contexto=("aluno*",), texto="80% dos alunos avaliaram as aulas como boas.")
        achados = regra_afirmacoes_sensiveis("80% dos alunos: resultado garantido.", (f,), cliente(), HOJE)
        self.assertIn(("promessa_resultado", BLOQUEANTE), resumo(achados))

    def test_fato_de_outra_categoria_nao_apoia(self):
        # 80% liga-se a um fato de RESULTADO; isso não apoia uma promessa de SAÚDE.
        f = fato_completo(valores=("80%",), status="verificado", categoria="resultado",
                          contexto=("aluno*",))
        achados = regra_afirmacoes_sensiveis("80% dos alunos emagrecem.", (f,), cliente(), HOJE)
        self.assertEqual(resumo(achados), [("afirmacao_sensivel", BLOQUEANTE)])

    def test_fato_contestado_ou_fornecido_nao_apoia(self):
        for status in ("contestado", "fornecido"):
            with self.subTest(status=status):
                f = fato_completo(valores=(), status=status, categoria="comparativo",
                                  contexto=("bairro",), texto="A maior do bairro.")
                achados = regra_afirmacoes_sensiveis("A maior do bairro.", (f,), cliente(), HOJE)
                self.assertEqual(resumo(achados), [("afirmacao_sensivel", BLOQUEANTE)])
                self.assertIn(status, achados[0].mensagem)

    def test_extremo_categoria_desligada(self):
        c = cliente()
        c = type(c)(**{**c.__dict__, "categorias_sensiveis": ("saude",)})
        self.assertEqual(regra_afirmacoes_sensiveis("Sabor garantido!", (), c, HOJE), [])


class TestPalavraProibidaComPrefixo(unittest.TestCase):
    def test_prefixo_pega_flexoes(self):
        achados = regra_palavras_proibidas("garantida e garantidos", cliente(palavras=("garantid*",)))
        self.assertEqual(len(achados), 2)


if __name__ == "__main__":
    unittest.main()
