"""Herança aplicada à carga de clientes e de plataformas (dados fictícios)."""
import tempfile
import textwrap
import unittest
from pathlib import Path

from apoio import plataforma

from shiba.config import (
    ErroConfig,
    carregar_cliente,
    carregar_plataforma,
    configuracao_efetiva,
    plataformas_disponiveis,
)
from shiba.regras import BLOQUEANTE, INFO, regra_limite_caracteres
from shiba.config import Limite, Plataforma


class BaseModelos(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self._tmp.name)
        self.modelos = self.raiz / "modelos"
        self.clientes = self.modelos / "clientes"
        self.escrever("modelos/padrao.toml", """
            [hashtags]
            proibidas = ["#padrao"]
            [palavras_proibidas]
            termos = ["termo-padrao"]
        """)
        self.escrever("modelos/segmentos/seg.toml", """
            id = "seg"
            nome = "Segmento"
            [hashtags]
            minimo = 3
            maximo = 5
            proibidas = ["#segmento"]
        """)

    def tearDown(self):
        self._tmp.cleanup()

    def escrever(self, relativo, conteudo):
        caminho = self.raiz / relativo
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(textwrap.dedent(conteudo), encoding="utf-8")

    def cliente(self, extra="", segmento='segmento = "seg"'):
        self.escrever("modelos/clientes/c1/perfil.toml", f"""
            id = "c1"
            nome = "Cliente fictício"
            ficticio = true
            {segmento}
        """ + textwrap.dedent(extra))
        return carregar_cliente("c1", self.clientes, dir_modelos=self.modelos)


class TestCadeia(BaseModelos):
    def test_padrao_segmento_cliente(self):
        c = self.cliente("""
            [hashtags]
            maximo = 4
            proibidas = ["#cliente"]
        """)
        self.assertEqual((c.hashtags_minimo, c.hashtags_maximo), (3, 4))
        self.assertEqual(c.hashtags_proibidas, ("padrao", "segmento", "cliente"))
        self.assertEqual(c.palavras_proibidas, ("termo-padrao",))

    def test_sem_segmento_herda_so_o_padrao(self):
        c = self.cliente("""
            [hashtags]
            minimo = 1
            maximo = 2
        """, segmento="")
        self.assertEqual(c.hashtags_proibidas, ("padrao",))

    def test_faixa_de_hashtags_ausente_em_todas_as_camadas_e_erro(self):
        with self.assertRaisesRegex(ErroConfig, "hashtags"):
            self.cliente(segmento="")

    def test_identidade_nao_e_herdada(self):
        # O segmento tem nome, mas o cliente sem nome é recusado.
        self.escrever("modelos/clientes/c1/perfil.toml", 'id = "c1"\nficticio = true\nsegmento = "seg"\n')
        with self.assertRaisesRegex(ErroConfig, "nome"):
            carregar_cliente("c1", self.clientes, dir_modelos=self.modelos)

    def test_segmento_inexistente_ou_invalido(self):
        for seg in ('segmento = "nao-existe"', 'segmento = "../fora"'):
            with self.subTest(seg=seg), self.assertRaises(ErroConfig):
                self.cliente(segmento=seg)

    def test_segmento_nao_pode_declarar_ficticio(self):
        self.escrever("modelos/segmentos/seg.toml", 'id = "seg"\nficticio = false\n')
        with self.assertRaisesRegex(ErroConfig, "desconhecida"):
            self.cliente()

    def test_chave_digitada_errada_e_recusada(self):
        with self.assertRaisesRegex(ErroConfig, "desconhecida"):
            self.cliente("""
                [palavras_proibida]
                termos = ["x"]
            """)

    def test_ajuste_para_plataforma_inexistente_e_recusado(self):
        self.escrever("modelos/clientes/c1/perfil.toml", """
            id = "c1"
            nome = "x"
            ficticio = true
            segmento = "seg"
            [plataformas.tiktk.hashtags]
            maximo = 2
        """)
        with self.assertRaisesRegex(ErroConfig, "tiktk"):
            carregar_cliente("c1", self.clientes, dir_modelos=self.modelos,
                             plataformas_validas={"tiktok", "instagram"})

    def test_padrao_ausente_e_opcional_mas_campos_obrigatorios_continuam(self):
        (self.modelos / "padrao.toml").unlink()
        # Sem o padrão, ninguém define [palavras_proibidas]: valor obrigatório
        # ausente em TODAS as camadas é erro, nunca um valor suposto.
        with self.assertRaisesRegex(ErroConfig, "palavras_proibidas"):
            self.cliente()
        c = self.cliente("""
            [palavras_proibidas]
            termos = []
        """)
        self.assertEqual(c.hashtags_proibidas, ("segmento",))

    def test_resultado_minimo_maior_que_maximo_apos_heranca_e_erro(self):
        with self.assertRaisesRegex(ErroConfig, "minimo <= maximo"):
            self.cliente("""
                [hashtags]
                minimo = 9
            """)


class TestModelosDoRepositorio(unittest.TestCase):
    def test_exemplo_cafe_por_plataforma(self):
        esperado = {
            "instagram": (2, 4, ("sigam", "likeforlike", "cafezinho"), ("milagr*", "detox", "barato")),
            "tiktok": (2, 3, ("sigam", "likeforlike", "cafezinho"), ("milagr*", "detox", "barato", "promoção")),
            "youtube-shorts": (0, 4, ("shorts",), ("milagr*", "detox", "barato")),
        }
        for pid, (minimo, maximo, proibidas, termos) in esperado.items():
            with self.subTest(plataforma=pid):
                c = carregar_cliente("exemplo-cafe", plataforma=pid,
                                     plataformas_validas=plataformas_disponiveis())
                self.assertEqual((c.hashtags_minimo, c.hashtags_maximo), (minimo, maximo))
                self.assertEqual(c.hashtags_proibidas, proibidas)
                self.assertEqual(c.palavras_proibidas, termos)

    def test_clientes_anteriores_mantem_a_configuracao(self):
        # Compatibilidade: o padrão neutro não muda nada nos clientes dos incrementos 0 e 1.
        c = carregar_cliente("exemplo", plataforma="instagram")
        self.assertEqual((c.hashtags_minimo, c.hashtags_maximo), (3, 5))
        self.assertEqual(c.hashtags_proibidas, ("sigam", "sigoDeVolta", "likeforlike"))
        self.assertEqual(c.palavras_proibidas, ("garantido", "milagroso", "cura", "melhor do Brasil"))
        a = carregar_cliente("exemplo-academia")
        self.assertEqual((a.hashtags_minimo, a.hashtags_maximo, a.hashtags_proibidas), (2, 5, ("sigam",)))

    def test_origens_dizem_de_onde_veio_cada_valor(self):
        _, _, origens = configuracao_efetiva("exemplo-cafe", plataforma="tiktok")
        self.assertEqual(origens["hashtags.maximo"], "cliente@tiktok")
        self.assertEqual(origens["hashtags.minimo"], "cliente")
        self.assertEqual(origens["palavras_proibidas.termos"]["detox"], "segmento:gastronomia")
        self.assertNotIn("light", origens["palavras_proibidas.termos"])

    def test_todos_os_clientes_versionados_sao_ficticios(self):
        from shiba.config import DIR_CLIENTES
        for pasta in sorted(p for p in DIR_CLIENTES.iterdir() if p.is_dir()):
            with self.subTest(cliente=pasta.name):
                self.assertTrue(carregar_cliente(pasta.name).ficticio)


class TestPlataformas(unittest.TestCase):
    def test_tres_plataformas_disponiveis(self):
        self.assertEqual(plataformas_disponiveis(), {"instagram", "tiktok", "youtube-shorts"})

    def test_nenhum_limite_inventado(self):
        # Todo limite com valor precisa de origem registrada; TikTok e Shorts não têm nenhum.
        for pid in ("tiktok", "youtube-shorts"):
            for nome, limite in carregar_plataforma(pid).limites:
                with self.subTest(plataforma=pid, limite=nome):
                    self.assertIsNone(limite.valor)
                    self.assertEqual(limite.status, "a_verificar")

    def test_instagram_herda_limites_do_padrao(self):
        p = carregar_plataforma("instagram")
        limites = dict(p.limites)
        self.assertEqual(limites["legenda_max_caracteres"].valor, 2200)
        self.assertIsNone(limites["duracao_max_segundos"].valor)

    def test_shorts_usa_descricao(self):
        self.assertEqual(carregar_plataforma("youtube-shorts").texto_principal, "descricao")
        self.assertEqual(carregar_plataforma("tiktok").texto_principal, "legenda")


class TestPlataformaArquivos(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def escrever(self, nome, conteudo):
        (self.dir / nome).write_text(textwrap.dedent(conteudo), encoding="utf-8")

    def test_padrao_nao_pode_ter_id(self):
        self.escrever("_padrao.toml", 'id = "x"\n[limites.legenda_max_caracteres]\nstatus = "a_verificar"\n')
        self.escrever("p1.toml", 'id = "p1"\nnome = "P1"\n')
        with self.assertRaisesRegex(ErroConfig, "id nem nome"):
            carregar_plataforma("p1", self.dir)

    def test_verificado_sem_valor_e_recusado(self):
        self.escrever("p1.toml", """
            id = "p1"
            nome = "P1"
            [limites.legenda_max_caracteres]
            status = "verificado"
            fonte = "https://exemplo.invalid"
            consultado_em = "2026-10-23"
        """)
        with self.assertRaisesRegex(ErroConfig, "exige valor"):
            carregar_plataforma("p1", self.dir)

    def test_chave_desconhecida_no_limite(self):
        self.escrever("p1.toml", """
            id = "p1"
            nome = "P1"
            [limites.legenda_max_caracteres]
            status = "a_verificar"
            valr = 100
        """)
        with self.assertRaisesRegex(ErroConfig, "valr"):
            carregar_plataforma("p1", self.dir)

    def test_padrao_nao_e_selecionavel(self):
        with self.assertRaises(ErroConfig):
            carregar_plataforma("_padrao", self.dir)


class TestLimiteSemValor(unittest.TestCase):
    def test_sem_valor_so_informa(self):
        p = Plataforma("t", "T", Limite(None, "a_verificar", "", ""))
        self.assertEqual([a.severidade for a in regra_limite_caracteres("x" * 10_000, p)], [INFO])

    def test_sem_valor_legenda_vazia_continua_bloqueando(self):
        p = Plataforma("t", "T", Limite(None, "a_verificar", "", ""))
        self.assertEqual([a.severidade for a in regra_limite_caracteres("", p)], [BLOQUEANTE])

    def test_compatibilidade_construtor_antigo(self):
        self.assertEqual(plataforma().texto_principal, "legenda")


if __name__ == "__main__":
    unittest.main()
