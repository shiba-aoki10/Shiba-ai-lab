import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from shiba.cli import main

FIXTURES = Path(__file__).parent / "fixtures" / "sinteticos"


def rodar(*args):
    saida, erro = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(saida), contextlib.redirect_stderr(erro):
        codigo = main(list(args))
    return codigo, saida.getvalue(), erro.getvalue()


class TestCli(unittest.TestCase):
    def test_legenda_que_passa(self):
        codigo, saida, _ = rodar("verificar", str(FIXTURES / "legenda_passa.md"),
                                 "--cliente", "exemplo", "--plataforma", "instagram",
                                 "--formato", "json")
        laudo = json.loads(saida)
        self.assertEqual(codigo, 0)
        self.assertEqual(laudo["resultado"], "passou")
        self.assertEqual(laudo["resumo"]["bloqueante"], 0)
        self.assertEqual(laudo["esquema"], "shiba.laudo/0.1")

    def test_legenda_bloqueada(self):
        codigo, saida, _ = rodar("verificar", str(FIXTURES / "legenda_bloqueada.md"),
                                 "--cliente", "exemplo", "--plataforma", "instagram",
                                 "--formato", "json")
        laudo = json.loads(saida)
        self.assertEqual(codigo, 1)
        self.assertEqual(laudo["resultado"], "bloqueado")
        regras = {a["regra"] for a in laudo["achados"] if a["severidade"] == "bloqueante"}
        # Incremento 1 acrescentou promessa_resultado ("Aqui é garantido").
        self.assertEqual(regras, {"hashtags", "palavra_proibida", "numero_sem_fato",
                                  "promessa_resultado"})
        for a in laudo["achados"]:
            if "inicio" in a:
                self.assertIn("trecho", a)
                self.assertIn("linha", a)

    def test_formato_texto_lembra_que_nao_e_aprovacao(self):
        _, saida, _ = rodar("verificar", str(FIXTURES / "legenda_passa.md"),
                            "--cliente", "exemplo", "--plataforma", "instagram")
        self.assertIn("NÃO é aprovação humana", saida)

    def test_erros_retornam_2(self):
        casos = [
            ("verificar", "/nao/existe.md", "--cliente", "exemplo", "--plataforma", "instagram"),
            ("verificar", str(FIXTURES / "legenda_passa.md"), "--cliente", "../x", "--plataforma", "instagram"),
            ("verificar", str(FIXTURES / "legenda_passa.md"), "--cliente", "exemplo", "--plataforma", "nenhuma"),
        ]
        for args in casos:
            with self.subTest(args=args):
                codigo, saida, erro = rodar(*args)
                self.assertEqual(codigo, 2)
                self.assertEqual(saida, "")
                self.assertTrue(erro.startswith("erro:"))

    def test_arquivo_nao_utf8_e_arquivo_grande(self):
        with tempfile.TemporaryDirectory() as tmp:
            latin = Path(tmp) / "latin.md"
            latin.write_bytes("pão".encode("latin-1"))
            grande = Path(tmp) / "grande.md"
            grande.write_bytes(b"a" * (64 * 1024 + 1))
            for arquivo, msg in ((latin, "UTF-8"), (grande, "maior que")):
                with self.subTest(arquivo=arquivo.name):
                    codigo, _, erro = rodar("verificar", str(arquivo), "--cliente", "exemplo",
                                            "--plataforma", "instagram")
                    self.assertEqual(codigo, 2)
                    self.assertIn(msg, erro)


if __name__ == "__main__":
    unittest.main()
