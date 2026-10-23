import tempfile
import textwrap
import unittest
from pathlib import Path

from shiba.config import ErroConfig, carregar_cliente, carregar_fatos, carregar_plataforma

PERFIL_OK = """
id = "c1"
nome = "Fictício"
ficticio = true
[hashtags]
minimo = 3
maximo = 5
proibidas = ["#sigam"]
[palavras_proibidas]
termos = ["garantido"]
"""

PLATAFORMA = """
id = "p1"
nome = "P1"
[limites.legenda_max_caracteres]
valor = 100
status = "{status}"
fonte = "{fonte}"
consultado_em = "{data}"
"""


class BaseTemp(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def escrever(self, relativo, conteudo):
        caminho = self.dir / relativo
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(textwrap.dedent(conteudo), encoding="utf-8")


class TestCliente(BaseTemp):
    def test_positivo_perfil_valido(self):
        self.escrever("c1/perfil.toml", PERFIL_OK)
        c = carregar_cliente("c1", self.dir)
        self.assertEqual(c.hashtags_proibidas, ("sigam",))

    def test_negativo_cliente_nao_ficticio_e_recusado(self):
        self.escrever("c1/perfil.toml", PERFIL_OK.replace("ficticio = true", "ficticio = false"))
        with self.assertRaisesRegex(ErroConfig, "ficticio = true"):
            carregar_cliente("c1", self.dir)

    def test_negativo_campo_ausente(self):
        self.escrever("c1/perfil.toml", PERFIL_OK.replace('nome = "Fictício"', ""))
        with self.assertRaisesRegex(ErroConfig, "nome"):
            carregar_cliente("c1", self.dir)

    def test_negativo_faixa_invertida(self):
        self.escrever("c1/perfil.toml", PERFIL_OK.replace("minimo = 3", "minimo = 9"))
        with self.assertRaisesRegex(ErroConfig, "minimo <= maximo"):
            carregar_cliente("c1", self.dir)

    def test_negativo_booleano_onde_se_espera_numero(self):
        self.escrever("c1/perfil.toml", PERFIL_OK.replace("minimo = 3", "minimo = true"))
        with self.assertRaisesRegex(ErroConfig, "int"):
            carregar_cliente("c1", self.dir)

    def test_extremo_id_com_caminho_e_recusado(self):
        for ruim in ("../c1", "/etc", "C1", "", "a/b"):
            with self.subTest(id=ruim), self.assertRaises(ErroConfig):
                carregar_cliente(ruim, self.dir)

    def test_negativo_toml_malformado(self):
        self.escrever("c1/perfil.toml", "id = ")
        with self.assertRaisesRegex(ErroConfig, "TOML inválido"):
            carregar_cliente("c1", self.dir)

    def test_negativo_arquivo_inexistente(self):
        with self.assertRaisesRegex(ErroConfig, "não encontrado"):
            carregar_cliente("c1", self.dir)


class TestFatos(BaseTemp):
    def test_positivo_e_status_invalido(self):
        self.escrever("c1/fatos.toml", '[[fato]]\nid="F-1"\ntexto="x"\nvalores=["1"]\nstatus="fornecido"\n')
        self.assertEqual(carregar_fatos("c1", self.dir)[0].status, "fornecido")
        self.escrever("c1/fatos.toml", '[[fato]]\nid="F-1"\ntexto="x"\nvalores=["1"]\nstatus="talvez"\n')
        with self.assertRaisesRegex(ErroConfig, "status"):
            carregar_fatos("c1", self.dir)

    def test_negativo_id_duplicado(self):
        bloco = '[[fato]]\nid="F-1"\ntexto="x"\nvalores=["1"]\nstatus="fornecido"\n'
        self.escrever("c1/fatos.toml", bloco * 2)
        with self.assertRaisesRegex(ErroConfig, "duplicado"):
            carregar_fatos("c1", self.dir)

    def test_extremo_arquivo_sem_fatos(self):
        self.escrever("c1/fatos.toml", "# vazio\n")
        self.assertEqual(carregar_fatos("c1", self.dir), ())


class TestPlataforma(BaseTemp):
    def test_positivo_a_verificar_sem_fonte(self):
        self.escrever("p1.toml", PLATAFORMA.format(status="a_verificar", fonte="", data=""))
        self.assertFalse(carregar_plataforma("p1", self.dir).legenda_max_caracteres.verificado)

    def test_negativo_verificado_sem_fonte_e_recusado(self):
        self.escrever("p1.toml", PLATAFORMA.format(status="verificado", fonte="", data="2026-10-23"))
        with self.assertRaisesRegex(ErroConfig, "exige fonte"):
            carregar_plataforma("p1", self.dir)

    def test_positivo_verificado_com_fonte(self):
        self.escrever("p1.toml", PLATAFORMA.format(
            status="verificado", fonte="https://exemplo.invalid", data="2026-10-23"))
        self.assertTrue(carregar_plataforma("p1", self.dir).legenda_max_caracteres.verificado)

    def test_negativo_status_desconhecido(self):
        self.escrever("p1.toml", PLATAFORMA.format(status="talvez", fonte="", data=""))
        with self.assertRaisesRegex(ErroConfig, "status"):
            carregar_plataforma("p1", self.dir)


class TestArquivosDoRepositorio(unittest.TestCase):
    def test_cliente_exemplo_e_instagram_carregam(self):
        self.assertTrue(carregar_cliente("exemplo").ficticio)
        self.assertEqual(len(carregar_fatos("exemplo")), 3)
        self.assertFalse(carregar_plataforma("instagram").legenda_max_caracteres.verificado)


if __name__ == "__main__":
    unittest.main()
