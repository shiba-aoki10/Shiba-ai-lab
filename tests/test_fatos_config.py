"""Validação dos campos de fato do Incremento 1 (só dados fictícios)."""
import tempfile
import unittest
from datetime import date
from pathlib import Path

from shiba.config import ErroConfig, carregar_cliente, carregar_fatos, carregar_fatos_arquivo, juntar_fatos

FONTE = """
[fato.fonte]
tipo = "cliente_declarou"
referencia = "FICTÍCIO"
informado_por = "teste"
informado_em = 2026-10-23
"""
VERIFICACAO = """
[fato.verificacao]
fonte = "FICTÍCIO"
metodo = "teste"
verificado_por = "teste"
verificado_em = 2026-10-23
"""


def bloco(status="fornecido", extra="", fonte=FONTE, verificacao=""):
    return f'[[fato]]\nid = "F-1"\ntexto = "x"\nvalores = ["1"]\nstatus = "{status}"\n{extra}\n{fonte}{verificacao}'


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.arq = Path(self._tmp.name) / "fatos.toml"

    def tearDown(self):
        self._tmp.cleanup()

    def carregar(self, conteudo):
        self.arq.write_text(conteudo, encoding="utf-8")
        return carregar_fatos_arquivo(self.arq)


class TestCamposNovos(Base):
    def test_positivo_completo(self):
        f = self.carregar(bloco("verificado", 'categoria = "saude"\ncontexto = ["massa"]\n'
                                'unidade = "horas"\nvalido_ate = 2027-01-31', FONTE, VERIFICACAO))[0]
        self.assertEqual((f.categoria, f.contexto, f.unidade), ("saude", ("massa",), "hora"))
        self.assertEqual(f.valido_ate, date(2027, 1, 31))
        self.assertEqual(dict(f.fonte)["informado_em"], "2026-10-23")
        self.assertEqual(dict(f.verificacao)["metodo"], "teste")

    def test_padroes_quando_ausentes(self):
        f = self.carregar(bloco())[0]
        self.assertEqual((f.categoria, f.contexto, f.unidade, f.valido_ate),
                         ("institucional", (), "", None))

    def test_verificado_sem_verificacao_e_recusado(self):
        with self.assertRaisesRegex(ErroConfig, "verificado"):
            self.carregar(bloco("verificado"))

    def test_verificado_sem_fonte_e_recusado(self):
        with self.assertRaisesRegex(ErroConfig, "verificado"):
            self.carregar(bloco("verificado", fonte="", verificacao=VERIFICACAO))

    def test_fornecido_com_verificacao_e_recusado(self):
        with self.assertRaisesRegex(ErroConfig, "fornecido"):
            self.carregar(bloco("fornecido", verificacao=VERIFICACAO))

    def test_fonte_incompleta_e_recusada(self):
        with self.assertRaisesRegex(ErroConfig, "informado_por"):
            self.carregar(bloco(fonte=FONTE.replace('informado_por = "teste"', "")))

    def test_categoria_desconhecida(self):
        with self.assertRaisesRegex(ErroConfig, "categoria"):
            self.carregar(bloco(extra='categoria = "fofoca"'))

    def test_data_invalida(self):
        with self.assertRaisesRegex(ErroConfig, "valido_ate"):
            self.carregar(bloco(extra='valido_ate = "31/12/2026"'))

    def test_data_em_texto_iso_e_aceita(self):
        self.assertEqual(self.carregar(bloco(extra='valido_ate = "2026-12-31"'))[0].valido_ate,
                         date(2026, 12, 31))

    def test_contexto_vazio_e_recusado(self):
        with self.assertRaisesRegex(ErroConfig, "contexto"):
            self.carregar(bloco(extra='contexto = [""]'))


class TestJuntarFatos(Base):
    def test_ids_repetidos_entre_arquivos(self):
        fatos = self.carregar(bloco())
        with self.assertRaisesRegex(ErroConfig, "repetido"):
            juntar_fatos(fatos, fatos)


class TestModelosDoRepositorio(unittest.TestCase):
    def test_academia_ficticia_carrega(self):
        c = carregar_cliente("exemplo-academia")
        self.assertTrue(c.ficticio)
        self.assertIn("saude", c.categorias_sensiveis)
        status = {f.id: f.status for f in carregar_fatos("exemplo-academia")}
        self.assertEqual(set(status.values()), {"verificado", "fornecido", "contestado"})

    def test_todos_os_modelos_marcam_fonte_como_ficticia(self):
        for cliente_id in ("exemplo", "exemplo-academia"):
            for f in carregar_fatos(cliente_id):
                with self.subTest(fato=f.id):
                    self.assertIn("FICTÍCIO", dict(f.fonte)["referencia"])


if __name__ == "__main__":
    unittest.main()
