"""Isolamento de dados reais: fora do Git, fora do código, sem vazamento em mensagens.

Os "dados reais" aqui são FICTÍCIOS, criados em pastas temporárias. Os
"repositórios" são falsos: só uma pasta ou arquivo `.git`; o Git não é executado.
"""
import contextlib
import io
import os
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from shiba.cli import main
from shiba.config import RAIZ
from shiba.dados import (
    ErroIsolamento,
    garantir_fora_do_git,
    preparar_dir_dados,
    repositorio_que_contem,
    resolver_dir_dados,
)

FIXTURES = Path(__file__).parent / "fixtures" / "sinteticos"
SEGREDO = "MARCADOR-SIGILOSO-7Q4Z"  # nunca pode aparecer em saída de erro
AMBIENTE_LIMPO = {"GIT_DIR": "", "GIT_WORK_TREE": "", "SHIBA_DADOS": ""}


def rodar(*args, ambiente=None):
    saida, erro = io.StringIO(), io.StringIO()
    with mock.patch.dict(os.environ, ambiente or AMBIENTE_LIMPO), \
            contextlib.redirect_stdout(saida), contextlib.redirect_stderr(erro):
        codigo = main(list(args))
    return codigo, saida.getvalue(), erro.getvalue()


def foto(pasta: Path) -> dict:
    """Retrato do conteúdo de uma pasta (para provar que nada foi criado ou alterado)."""
    return {str(p.relative_to(pasta)): p.read_bytes() for p in sorted(pasta.rglob("*")) if p.is_file()}


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name).resolve()
        if repositorio_que_contem(self.tmp) is not None:
            self.skipTest("a pasta temporária do sistema está dentro de um repositório Git")
        # "Dados reais" fictícios, fora de qualquer repositório.
        self.dados = self.tmp / "dados"
        self.escrever(self.dados / "clientes" / "real1" / "perfil.toml", f"""
            id = "real1"
            nome = "{SEGREDO}"
            ficticio = false
            segmento = "gastronomia"
        """)
        self.escrever(self.dados / "clientes" / "real1" / "fatos.toml", "")
        self.legenda = self.tmp / "legenda.md"
        self.legenda.write_text("Pão quentinho.\n\n#pao #padaria #fornada", encoding="utf-8")
        # Repositório falso.
        self.repo = self.tmp / "repo"
        (self.repo / ".git").mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    @staticmethod
    def escrever(caminho: Path, conteudo: str):
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(textwrap.dedent(conteudo), encoding="utf-8")

    def verificar_real(self, *extra, dados=None, legenda=None):
        return rodar("verificar", str(legenda or self.legenda), "--cliente", "real1",
                     "--plataforma", "instagram", "--dados", str(dados or self.dados), *extra)


class TestDeteccaoDeRepositorio(Base):
    def test_fora_de_repositorio(self):
        self.assertIsNone(repositorio_que_contem(self.dados))
        self.assertEqual(preparar_dir_dados(self.dados), self.dados)

    def test_dentro_de_repositorio_em_qualquer_nivel_acima(self):
        fundo = self.repo / "a" / "b" / "c" / "dados"
        fundo.mkdir(parents=True)
        self.assertEqual(repositorio_que_contem(fundo), self.repo)
        with self.assertRaisesRegex(ErroIsolamento, "repositório Git"):
            preparar_dir_dados(fundo)

    def test_o_proprio_repositorio(self):
        with self.assertRaises(ErroIsolamento):
            preparar_dir_dados(self.repo)

    def test_git_como_arquivo_worktree_ou_submodulo(self):
        outro = self.tmp / "worktree"
        outro.mkdir()
        (outro / ".git").write_text("gitdir: /em/outro/lugar\n", encoding="utf-8")
        (outro / "dados").mkdir()
        with self.assertRaises(ErroIsolamento):
            preparar_dir_dados(outro / "dados")

    def test_repositorio_nu(self):
        nu = self.tmp / "nu.git"
        for sub in ("objects", "refs"):
            (nu / sub).mkdir(parents=True)
        (nu / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        (nu / "dados").mkdir()
        with self.assertRaises(ErroIsolamento):
            preparar_dir_dados(nu / "dados")

    def test_link_simbolico_que_aponta_para_dentro_de_repositorio(self):
        alvo = self.repo / "dados"
        alvo.mkdir()
        link = self.tmp / "atalho"
        try:
            link.symlink_to(alvo, target_is_directory=True)
        except OSError:
            self.skipTest("sistema sem suporte a link simbólico")
        with self.assertRaises(ErroIsolamento):
            preparar_dir_dados(link)

    def test_caminho_com_ponto_ponto_que_volta_para_o_repositorio(self):
        (self.repo / "dados").mkdir()
        disfarçado = self.tmp / "dados" / ".." / "repo" / "dados"
        with self.assertRaises(ErroIsolamento):
            preparar_dir_dados(disfarçado)

    def test_dentro_do_codigo_mesmo_sem_git(self):
        codigo = self.tmp / "codigo-exportado"
        (codigo / "dados").mkdir(parents=True)
        with self.assertRaisesRegex(ErroIsolamento, "código"):
            garantir_fora_do_git(codigo / "dados", "x", raiz_codigo=codigo, ambiente={})

    def test_o_repositorio_do_shiba_e_recusado(self):
        with self.assertRaises(ErroIsolamento):
            garantir_fora_do_git(RAIZ / "modelos", "x", ambiente={})

    def test_variaveis_git_no_ambiente_recusam(self):
        for variavel in ("GIT_DIR", "GIT_WORK_TREE"):
            with self.subTest(variavel=variavel), self.assertRaisesRegex(ErroIsolamento, variavel):
                garantir_fora_do_git(self.dados, "x", ambiente={variavel: "/qualquer"})

    def test_diretorio_inexistente_ou_arquivo(self):
        with self.assertRaisesRegex(ErroIsolamento, "não existe"):
            preparar_dir_dados(self.tmp / "nao-existe")
        with self.assertRaises(ErroIsolamento):
            preparar_dir_dados(self.legenda)

    @unittest.skipIf(os.name != "posix" or os.geteuid() == 0,
                     "root ignora permissões de pasta; teste só faz sentido para usuário comum")
    def test_pasta_sem_permissao_e_recusada(self):
        trancada = self.tmp / "trancada"
        (trancada / "dados").mkdir(parents=True)
        trancada.chmod(0)
        try:
            with self.assertRaisesRegex(ErroIsolamento, "inspecionar"):
                repositorio_que_contem(trancada / "dados")
        finally:
            trancada.chmod(0o700)

    def test_resolver_dir_dados(self):
        self.assertEqual(resolver_dir_dados("/a/b", {}), Path("/a/b"))
        self.assertEqual(resolver_dir_dados("", {"SHIBA_DADOS": "/c"}), Path("/c"))
        with self.assertRaisesRegex(ErroIsolamento, "SHIBA_DADOS"):
            resolver_dir_dados("", {})


class TestCliComDadosReais(Base):
    def test_uso_seguro_funciona_e_aceita_cliente_nao_ficticio(self):
        codigo, saida, erro = self.verificar_real("--data-referencia", "2026-10-23")
        self.assertEqual((codigo, erro), (0, ""))
        self.assertIn("PASSOU", saida)

    def test_sem_dados_cliente_real_nao_e_encontrado_nos_modelos(self):
        codigo, _, erro = rodar("verificar", str(self.legenda), "--cliente", "real1",
                                "--plataforma", "instagram")
        self.assertEqual(codigo, 2)
        self.assertIn("não encontrado", erro)

    def test_modelos_continuam_exigindo_ficticio(self):
        codigo, _, erro = rodar("verificar", str(self.legenda), "--cliente", "real1",
                                "--plataforma", "instagram", "--dir-clientes", str(self.dados / "clientes"))
        self.assertEqual(codigo, 2)
        self.assertIn("ficticio = true", erro)

    def test_variavel_de_ambiente(self):
        amb = dict(AMBIENTE_LIMPO, SHIBA_DADOS=str(self.dados))
        codigo, _, _ = rodar("verificar", str(self.legenda), "--cliente", "real1",
                             "--plataforma", "instagram", "--dados", ambiente=amb)
        self.assertEqual(codigo, 0)

    def test_dados_e_dir_clientes_juntos_e_erro(self):
        codigo, _, erro = self.verificar_real("--dir-clientes", str(self.dados / "clientes"))
        self.assertEqual(codigo, 2)
        self.assertIn("não os dois", erro)

    def test_dados_dentro_de_repositorio_sao_recusados(self):
        dentro = self.repo / "dados"
        (dentro / "clientes" / "real1").mkdir(parents=True)
        codigo, saida, erro = self.verificar_real(dados=dentro)
        self.assertEqual((codigo, saida), (2, ""))
        self.assertIn("repositório Git", erro)

    def test_legenda_dentro_de_repositorio_e_recusada(self):
        legenda = self.repo / "rascunho.md"
        legenda.write_text("Pão.\n#a #b #c", encoding="utf-8")
        codigo, _, erro = self.verificar_real(legenda=legenda)
        self.assertEqual(codigo, 2)
        self.assertIn("legenda", erro)

    def test_fontes_dentro_de_repositorio_e_recusado_e_nada_e_gravado(self):
        destino = self.repo / "fontes.md"
        codigo, _, erro = self.verificar_real("--fontes", str(destino))
        self.assertEqual(codigo, 2)
        self.assertIn("fontes.md", erro)
        self.assertFalse(destino.exists())

    def test_fatos_da_peca_dentro_de_repositorio_e_recusado(self):
        peca = self.repo / "peca.toml"
        peca.write_text("", encoding="utf-8")
        codigo, _, erro = self.verificar_real("--fatos-peca", str(peca))
        self.assertEqual(codigo, 2)
        self.assertIn("fatos da peça", erro)

    def test_fontes_fora_do_repositorio_e_gravado(self):
        destino = self.tmp / "saida" / "fontes.md"
        destino.parent.mkdir()
        codigo, _, _ = self.verificar_real("--fontes", str(destino), "--data-referencia", "2026-10-23")
        self.assertEqual(codigo, 0)
        self.assertTrue(destino.is_file())

    def test_nada_e_criado_nem_alterado_no_diretorio_de_dados(self):
        antes = foto(self.dados)
        self.verificar_real("--formato", "json")
        rodar("config", "mostrar", "--cliente", "real1", "--dados", str(self.dados))
        rodar("dados", "verificar", str(self.dados))
        self.assertEqual(foto(self.dados), antes)


class TestSemVazamento(Base):
    def test_erro_de_campo_nao_mostra_conteudo_nem_caminho_real(self):
        self.escrever(self.dados / "clientes" / "real1" / "perfil.toml", f"""
            id = "real1"
            nome = "{SEGREDO}"
            ficticio = false
            [hashtags]
            minimo = "{SEGREDO}"
            maximo = 3
        """)
        codigo, saida, erro = self.verificar_real()
        self.assertEqual(codigo, 2)
        self.assertNotIn(SEGREDO, erro + saida)
        self.assertNotIn(str(self.dados), erro)
        self.assertIn("<dados>/clientes/real1/perfil.toml", erro)

    def test_toml_quebrado_nao_mostra_a_linha(self):
        self.escrever(self.dados / "clientes" / "real1" / "perfil.toml",
                      f'id = "real1"\nnome = "{SEGREDO}\nficticio = false\n')
        codigo, saida, erro = self.verificar_real()
        self.assertEqual(codigo, 2)
        self.assertNotIn(SEGREDO, erro + saida)
        self.assertNotIn(str(self.dados), erro)

    def test_fatos_quebrados_nao_mostram_caminho_real(self):
        self.escrever(self.dados / "clientes" / "real1" / "fatos.toml", "[[fato]]\nid = \n")
        codigo, _, erro = self.verificar_real()
        self.assertEqual(codigo, 2)
        self.assertNotIn(str(self.dados), erro)
        self.assertIn("<dados>/clientes/real1/fatos.toml", erro)

    def test_dados_verificar_nao_lista_conteudo(self):
        (self.dados / f"{SEGREDO}.txt").write_text(SEGREDO, encoding="utf-8")
        codigo, saida, erro = rodar("dados", "verificar", str(self.dados))
        self.assertEqual(codigo, 0)
        self.assertNotIn(SEGREDO, saida + erro)
        self.assertIn("seguro", saida)

    def test_laudo_nao_inclui_dados_do_perfil(self):
        _, saida, _ = self.verificar_real("--formato", "json")
        self.assertNotIn(SEGREDO, saida)

    @unittest.skipIf(os.name != "posix", "permissões POSIX")
    def test_aviso_de_permissoes_abertas(self):
        self.dados.chmod(0o755)
        self.assertIn("aviso", rodar("dados", "verificar", str(self.dados))[1])
        self.dados.chmod(0o700)
        self.assertNotIn("aviso", rodar("dados", "verificar", str(self.dados))[1])

    def test_dados_verificar_inseguro(self):
        (self.repo / "dados").mkdir()
        codigo, saida, erro = rodar("dados", "verificar", str(self.repo / "dados"))
        self.assertEqual((codigo, saida), (2, ""))
        self.assertTrue(erro.startswith("inseguro:"))


class TestConfigMostrar(unittest.TestCase):
    def test_mostra_camadas_e_origens(self):
        import json
        codigo, saida, _ = rodar("config", "mostrar", "--cliente", "exemplo-cafe", "--plataforma", "tiktok")
        self.assertEqual(codigo, 0)
        d = json.loads(saida)
        self.assertEqual(d["ordem_das_camadas"][-1], "cliente@tiktok")
        self.assertEqual(d["configuracao"]["hashtags"]["maximo"], 3)
        self.assertEqual(d["origens"]["hashtags.maximo"], "cliente@tiktok")

    def test_plataforma_inexistente(self):
        codigo, _, erro = rodar("config", "mostrar", "--cliente", "exemplo-cafe", "--plataforma", "orkut")
        self.assertEqual(codigo, 2)
        self.assertIn("orkut", erro)


if __name__ == "__main__":
    unittest.main()
