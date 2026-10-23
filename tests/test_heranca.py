"""Regras de mesclagem da herança (unidade, sem arquivos)."""
import copy
import unittest

from shiba.heranca import ErroHeranca, mesclar, resolver, validar_camada


def efetiva(*camadas, plataforma=None):
    nomeadas = [(f"c{i}", c) for i, c in enumerate(camadas)]
    return resolver(nomeadas, plataforma)[0]


class TestMesclagem(unittest.TestCase):
    def test_valor_simples_mais_especifico_vence(self):
        self.assertEqual(efetiva({"hashtags": {"minimo": 3}}, {"hashtags": {"minimo": 1}}),
                         {"hashtags": {"minimo": 1}})

    def test_ausente_herda(self):
        r = efetiva({"hashtags": {"minimo": 3, "maximo": 5}}, {"hashtags": {"maximo": 4}})
        self.assertEqual(r["hashtags"], {"minimo": 3, "maximo": 4})

    def test_listas_somam_sem_repetir(self):
        r = efetiva({"hashtags": {"proibidas": ["#Sigam", "#a"]}},
                    {"hashtags": {"proibidas": ["sigam", "#B", "#á"]}})
        # "sigam" = "#Sigam" e "#á" = "#a" (sem maiúsculas, acentos e #)
        self.assertEqual(r["hashtags"]["proibidas"], ["#Sigam", "#a", "#B"])

    def test_substituir_troca_a_lista(self):
        r = efetiva({"palavras_proibidas": {"termos": ["x", "y"]}},
                    {"palavras_proibidas": {"termos__substituir": ["z"]}})
        self.assertEqual(r["palavras_proibidas"]["termos"], ["z"])

    def test_substituir_vazio_esvazia(self):
        r = efetiva({"palavras_proibidas": {"termos": ["x"]}},
                    {"palavras_proibidas": {"termos__substituir": []}})
        self.assertEqual(r["palavras_proibidas"]["termos"], [])

    def test_remover_e_depois_somar(self):
        r = efetiva({"palavras_proibidas": {"termos": ["light", "detox"]}},
                    {"palavras_proibidas": {"termos__remover": ["LIGHT"], "termos": ["barato"]}})
        self.assertEqual(r["palavras_proibidas"]["termos"], ["detox", "barato"])

    def test_remover_item_inexistente_nao_e_erro(self):
        r = efetiva({"palavras_proibidas": {"termos": ["x"]}},
                    {"palavras_proibidas": {"termos__remover": ["nada"]}})
        self.assertEqual(r["palavras_proibidas"]["termos"], ["x"])

    def test_conflito_de_tipo_e_erro(self):
        with self.assertRaises(ErroHeranca):
            mesclar({"a": [1]}, {"a": "texto"}, "c", {})
        with self.assertRaises(ErroHeranca):
            mesclar({"a": {"b": 1}}, {"a": 2}, "c", {})
        with self.assertRaises(ErroHeranca):
            mesclar({"a": 2}, {"a": {"b": 1}}, "c", {})

    def test_entradas_nao_sao_alteradas(self):
        base = {"hashtags": {"proibidas": ["#a"]}}
        camada = {"hashtags": {"proibidas": ["#b"]}}
        copias = copy.deepcopy((base, camada))
        mesclar(base, camada, "c", {})
        self.assertEqual((base, camada), copias)

    def test_sem_camadas(self):
        self.assertEqual(efetiva(), {})


class TestPlataforma(unittest.TestCase):
    CAMADAS = (
        {"hashtags": {"maximo": 5}, "plataformas": {"tiktok": {"hashtags": {"maximo": 4}}}},
        {"hashtags": {"maximo": 6}},  # cliente geral
    )

    def test_ajuste_geral_do_cliente_vence_ajuste_de_plataforma_do_segmento(self):
        self.assertEqual(efetiva(*self.CAMADAS, plataforma="tiktok")["hashtags"]["maximo"], 6)

    def test_ajuste_de_plataforma_da_mesma_camada_vence_o_geral(self):
        cliente = {"hashtags": {"maximo": 6}, "plataformas": {"tiktok": {"hashtags": {"maximo": 2}}}}
        self.assertEqual(efetiva(self.CAMADAS[0], cliente, plataforma="tiktok")["hashtags"]["maximo"], 2)

    def test_outra_plataforma_nao_recebe_o_ajuste(self):
        self.assertEqual(efetiva(self.CAMADAS[0], plataforma="instagram")["hashtags"]["maximo"], 5)
        self.assertNotIn("plataformas", efetiva(self.CAMADAS[0], plataforma="instagram"))

    def test_origens(self):
        _, origens = resolver([("padrao", {"hashtags": {"proibidas": ["#a"]}}),
                               ("cliente", {"hashtags": {"maximo": 3, "proibidas": ["#b"]},
                                            "plataformas": {"tiktok": {"hashtags": {"maximo": 2}}}})],
                              "tiktok")
        self.assertEqual(origens["hashtags.maximo"], "cliente@tiktok")
        self.assertEqual(origens["hashtags.proibidas"], {"a": "padrao", "b": "cliente"})


class TestValidacao(unittest.TestCase):
    def test_camada_valida(self):
        validar_camada({"id": "x", "nome": "X", "ficticio": True, "segmento": "s",
                        "hashtags": {"minimo": 1, "proibidas__remover": ["#a"]},
                        "plataformas": {"tiktok": {"hashtags": {"maximo": 2}}}}, "t", "cliente")

    def test_chaves_desconhecidas_sao_recusadas(self):
        casos = [
            ({"hashtag": {}}, "cliente"),                              # erro de digitação
            ({"hashtags": {"maxmo": 3}}, "cliente"),
            ({"ficticio": True}, "segmento"),                          # identidade fora do cliente
            ({"segmento": "x"}, "padrao"),
            ({"plataformas": {"tiktok": {"nome": "x"}}}, "cliente"),  # meta no ajuste
            ({"plataformas": {"tiktok": {"plataformas": {}}}}, "cliente"),
        ]
        for dados, tipo in casos:
            with self.subTest(dados=dados), self.assertRaises(ErroHeranca):
                validar_camada(dados, "t", tipo)

    def test_operador_so_em_lista(self):
        with self.assertRaises(ErroHeranca):
            validar_camada({"hashtags": {"minimo__substituir": [1]}}, "t", "cliente")
        with self.assertRaises(ErroHeranca):
            validar_camada({"hashtags": {"proibidas__remover": "#a"}}, "t", "cliente")

    def test_lista_e_substituir_juntos_e_ambiguo(self):
        with self.assertRaisesRegex(ErroHeranca, "OU"):
            validar_camada({"hashtags": {"proibidas": ["#a"], "proibidas__substituir": []}},
                           "t", "cliente")


if __name__ == "__main__":
    unittest.main()
