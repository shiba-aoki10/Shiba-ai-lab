"""Garante que o motor usa só a biblioteca padrão e nenhum módulo de rede (CA-03)."""
import ast
import sys
import unittest
from pathlib import Path

PACOTE = Path(__file__).resolve().parent.parent / "shiba"
PROIBIDOS = {"socket", "ssl", "http", "urllib", "ftplib", "smtplib", "subprocess",
             "asyncio", "requests", "httpx"}


def imports_de(arquivo):
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            for alias in no.names:
                yield alias.name.split(".")[0]
        elif isinstance(no, ast.ImportFrom) and no.level == 0 and no.module:
            yield no.module.split(".")[0]


class TestDependencias(unittest.TestCase):
    def test_so_biblioteca_padrao_e_sem_rede(self):
        arquivos = sorted(PACOTE.glob("*.py"))
        self.assertTrue(arquivos)
        for arquivo in arquivos:
            for modulo in imports_de(arquivo):
                with self.subTest(arquivo=arquivo.name, modulo=modulo):
                    self.assertIn(modulo, sys.stdlib_module_names)
                    self.assertNotIn(modulo, PROIBIDOS)


if __name__ == "__main__":
    unittest.main()
