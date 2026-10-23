"""fontes.md e opções novas da CLI (fatos da peça, data de referência)."""
import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from shiba.cli import main

FIXTURES = Path(__file__).parent / "fixtures" / "sinteticos"
DATA = "2026-10-23"


def rodar(*args):
    saida, erro = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(saida), contextlib.redirect_stderr(erro):
        codigo = main(list(args))
    return codigo, saida.getvalue(), erro.getvalue()


def academia(arquivo, *extra):
    return rodar("verificar", str(FIXTURES / arquivo), "--cliente", "exemplo-academia",
                 "--plataforma", "instagram", "--data-referencia", DATA, *extra)


class TestAcademia(unittest.TestCase):
    def test_legenda_com_fatos_verificados_passa(self):
        codigo, saida, _ = academia("academia_passa.md", "--formato", "json")
        laudo = json.loads(saida)
        self.assertEqual(codigo, 0)
        self.assertEqual(laudo["resumo"]["bloqueante"], 0)
        self.assertFalse(laudo["requer_revisao_humana"])
        self.assertEqual({u["id"] for u in laudo["fatos_usados"]}, {"A-0001", "A-0002"})

    def test_legenda_sensivel_bloqueada(self):
        codigo, saida, _ = academia("academia_bloqueada.md", "--formato", "json")
        laudo = json.loads(saida)
        self.assertEqual(codigo, 1)
        regras = {a["regra"] for a in laudo["achados"] if a["severidade"] == "bloqueante"}
        self.assertEqual(regras, {"afirmacao_sensivel", "promessa_resultado", "numero_por_extenso"})
        self.assertTrue(laudo["requer_revisao_humana"])  # "o dobro", "12" ambíguo

    def test_data_de_referencia_faz_fato_expirar(self):
        with tempfile.TemporaryDirectory() as tmp:
            legenda = Path(tmp) / "promo.md"
            legenda.write_text("Matrícula com 50% de desconto!\n\n#treino #academia", encoding="utf-8")
            base = ("verificar", str(legenda), "--cliente", "exemplo-academia",
                    "--plataforma", "instagram")
            self.assertEqual(rodar(*base, "--data-referencia", "2026-12-31")[0], 0)
            codigo, saida, _ = rodar(*base, "--data-referencia", "2027-01-01")
            self.assertEqual(codigo, 1)
            self.assertIn("expirado", saida)

    def test_data_invalida_e_erro_de_uso(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            academia("academia_passa.md", "--data-referencia", "23/10/2026")


class TestFatosDaPeca(unittest.TestCase):
    def test_fato_da_peca_libera_numero(self):
        with tempfile.TemporaryDirectory() as tmp:
            legenda = Path(tmp) / "turma.md"
            legenda.write_text("A turma de sábado tem 15 vagas.\n\n#treino #academia", encoding="utf-8")
            base = ("verificar", str(legenda), "--cliente", "exemplo-academia",
                    "--plataforma", "instagram", "--data-referencia", DATA)
            self.assertEqual(rodar(*base)[0], 1)
            self.assertEqual(rodar(*base, "--fatos-peca", str(FIXTURES / "fatos_peca.toml"))[0], 0)

    def test_id_repetido_entre_cliente_e_peca(self):
        with tempfile.TemporaryDirectory() as tmp:
            peca = Path(tmp) / "peca.toml"
            peca.write_text((FIXTURES / "fatos_peca.toml").read_text(encoding="utf-8")
                            .replace("P-0001", "A-0001"), encoding="utf-8")
            codigo, _, erro = academia("academia_passa.md", "--fatos-peca", str(peca))
            self.assertEqual(codigo, 2)
            self.assertIn("repetido", erro)


class TestFontesMd(unittest.TestCase):
    def test_gera_fontes_rastreaveis(self):
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "fontes.md"
            codigo, _, _ = academia("academia_passa.md", "--fontes", str(destino))
            self.assertEqual(codigo, 0)
            md = destino.read_text(encoding="utf-8")
            texto = (FIXTURES / "academia_passa.md").read_text(encoding="utf-8").strip()
            self.assertIn(hashlib.sha256(texto.encode("utf-8")).hexdigest(), md)
            self.assertIn("### A-0002", md)
            self.assertIn("referencia: FICTÍCIO", md)
            self.assertIn("verificado_por: equipe de teste", md)
            self.assertIn("não garantem", md)
            self.assertIn("vínculo forte", md)

    def test_fontes_marca_pendencias_e_sem_fato(self):
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "fontes.md"
            academia("academia_bloqueada.md", "--fontes", str(destino))
            md = destino.read_text(encoding="utf-8")
            self.assertIn("SEM FATO", md)
            self.assertIn("AMBÍGUO", md)
            self.assertIn("A-0004 (contestado)", md)
            self.assertIn("**bloqueante** `promessa_resultado`", md)

    def test_recusa_sobrescrever_sem_opcao(self):
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "fontes.md"
            destino.write_text("anterior", encoding="utf-8")
            codigo, saida, erro = academia("academia_passa.md", "--fontes", str(destino))
            self.assertEqual((codigo, saida), (2, ""))
            self.assertIn("já existe", erro)
            self.assertEqual(destino.read_text(encoding="utf-8"), "anterior")
            codigo, _, _ = academia("academia_passa.md", "--fontes", str(destino), "--sobrescrever")
            self.assertEqual(codigo, 0)
            self.assertIn("# Fontes da peça", destino.read_text(encoding="utf-8"))

    def test_celula_com_barra_vertical_e_escapada(self):
        with tempfile.TemporaryDirectory() as tmp:
            legenda, destino = Path(tmp) / "l.md", Path(tmp) / "f.md"
            legenda.write_text("Pão | café: 99 itens\n#a #b", encoding="utf-8")
            rodar("verificar", str(legenda), "--cliente", "exemplo-academia", "--plataforma",
                  "instagram", "--data-referencia", DATA, "--fontes", str(destino))
            self.assertIn("Pão \\| café", destino.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
