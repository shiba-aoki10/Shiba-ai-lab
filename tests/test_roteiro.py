"""Roteiro audiovisual (Incremento 3B). Roteiros e clientes fictícios."""
import contextlib
import dataclasses
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apoio import cliente, fato_completo

from shiba.cli import main
from shiba.config import ErroConfig, Limite, Plataforma
from shiba.regras import AVISO, BLOQUEANTE, INFO, REVISAO
from shiba.roteiro import interpretar_roteiro
from shiba.verificar_roteiro import verificar_roteiro

FIXTURES = Path(__file__).parent / "fixtures" / "sinteticos"
CFG = {"janela_gancho_s": 3, "tolerancia_duracao_pct": 15, "texto_tela_max_palavras": 7}


def cli(cfg=CFG, **kw):
    c = cliente(minimo=0, palavras=())
    return dataclasses.replace(c, secoes={"roteiro": dict(cfg), "editorial": kw.get("editorial", {})})


def plat(duracao=None, status="a_verificar"):
    fonte, data = ("https://exemplo.invalid", "2026-10-23") if status == "verificado" else ("", "")
    lim = Limite(None, "a_verificar", "", "")
    dur = Limite(duracao, status, fonte, data)
    return Plataforma("tiktok", "TikTok", lim, limites=(("legenda_max_caracteres", lim),
                                                       ("duracao_max_segundos", dur)))


def base(**extra):
    r = {
        "plataforma": "tiktok",
        "duracao_alvo_s": 10,
        "mensagem_principal": "pão fresco",
        "termos_mensagem": ["pão"],
        "cta": {"texto": "Passa aqui", "forma": "falada"},
        "cena": [
            {"id": "c1", "inicio_s": 0, "fim_s": 5, "visual": "pão saindo do forno", "fala": "Pão saindo agora."},
            {"id": "c2", "inicio_s": 5, "fim_s": 10, "visual": "balcão", "fala": "Passa aqui."},
        ],
    }
    r.update(extra)
    return r


def laudo(dados, cfg=CFG, plataforma=None, fatos=()):
    return verificar_roteiro(interpretar_roteiro(dados), cli(cfg), tuple(fatos), plataforma or plat())


def achados(dados, **kw):
    return [(a["regra"], a["severidade"]) for a in laudo(dados, **kw)["achados"]
            if a["severidade"] != INFO]


class TestEstruturaDoArquivo(unittest.TestCase):
    def test_roteiro_valido(self):
        r = interpretar_roteiro(base())
        self.assertEqual((len(r.cenas), r.duracao_total), (2, 10.0))

    def test_erros_de_estrutura(self):
        casos = [
            ({"plataform": "x"}, "desconhecida"),
            ({"cena": []} | {"plataforma": ""}, "plataforma"),
            (base(cena=[{"id": "c1", "inicio_s": 3, "fim_s": 3, "visual": "x"}]), "maior"),
            (base(cena=[{"id": "c1", "inicio_s": -1, "fim_s": 3, "visual": "x"}]), "negativo"),
            (base(cena=[{"id": "c1", "inicio_s": "0", "fim_s": 3, "visual": "x"}]), "número"),
            (base(cena=[{"id": "c1", "inicio_s": 0, "fim_s": 3, "visual": "x"}],
                  elemento=[{"id": "c1", "tipo": "logo", "inicio_s": 0, "fim_s": 1}]), "repetido"),
            (base(cena=[{"id": "c1", "inicio_s": 0, "fim_s": 3, "visual": "x", "audio": ["musica"]}]), "audio"),
            (base(elemento=[{"id": "e", "tipo": "holograma", "inicio_s": 0, "fim_s": 1}]), "tipo"),
            (base(cta={"texto": "x", "forma": "telepatia"}), "forma"),
            (base(cta={"forma": "visual"}), "texto"),
            (base(duracao_alvo_s=0), "positiva"),
            (base(termos_mensagem=[""]), "termos_mensagem"),
            (base(cena=[{"id": "C 1", "inicio_s": 0, "fim_s": 3, "visual": "x"}]), "id"),
        ]
        for dados, msg in casos:
            with self.subTest(msg=msg), self.assertRaisesRegex(ErroConfig, msg):
                interpretar_roteiro(dados)


class TestCenasEElementos(unittest.TestCase):
    def test_roteiro_bem_formado_nao_tem_aviso(self):
        self.assertEqual(achados(base()), [])

    def test_cenas_sobrepostas_bloqueiam(self):
        cenas = [{"id": "a", "inicio_s": 0, "fim_s": 6, "visual": "x", "fala": "Pão."},
                 {"id": "b", "inicio_s": 5, "fim_s": 10, "visual": "y", "fala": "Passa aqui."}]
        self.assertIn(("roteiro_estrutura", BLOQUEANTE), achados(base(cena=cenas)))

    def test_elementos_simultaneos_podem_se_sobrepor(self):
        elementos = [
            {"id": "t", "tipo": "trilha", "inicio_s": 0, "fim_s": 10},
            {"id": "g", "tipo": "grafismo", "inicio_s": 2, "fim_s": 8},
            {"id": "x", "tipo": "texto_tela", "inicio_s": 3, "fim_s": 9, "conteudo": "Pão fresco"},
        ]
        self.assertEqual(achados(base(elemento=elementos)), [])

    def test_buraco_e_inicio_tardio_avisam(self):
        cenas = [{"id": "a", "inicio_s": 1, "fim_s": 4, "visual": "x", "fala": "Pão."},
                 {"id": "b", "inicio_s": 6, "fim_s": 10, "visual": "y", "fala": "Passa aqui."}]
        self.assertEqual(achados(base(cena=cenas)).count(("roteiro_estrutura", AVISO)), 2)

    def test_cenas_fora_de_ordem_no_arquivo(self):
        cenas = list(reversed(base()["cena"]))
        self.assertIn(("roteiro_estrutura", AVISO), achados(base(cena=cenas)))

    def test_cena_sem_visual_bloqueia(self):
        cenas = [dict(base()["cena"][0], visual=""), base()["cena"][1]]
        self.assertIn(("roteiro_cena_incompleta", BLOQUEANTE), achados(base(cena=cenas)))

    def test_cena_sem_locucao_com_trilha_e_valida(self):
        cenas = [{"id": "a", "inicio_s": 0, "fim_s": 5, "visual": "motion graphics", "texto_tela": "Pão fresco"},
                 {"id": "b", "inicio_s": 5, "fim_s": 10, "visual": "logo", "texto_tela": "Passa aqui"}]
        trilha = [{"id": "t", "tipo": "trilha", "inicio_s": 0, "fim_s": 10, "conteudo": "instrumental"}]
        self.assertEqual(achados(base(cena=cenas, elemento=trilha)), [])

    def test_silencio_declarado_e_audio_proprio_sao_validos(self):
        cenas = [{"id": "a", "inicio_s": 0, "fim_s": 5, "visual": "x", "texto_tela": "Pão", "audio": "silencio"},
                 {"id": "b", "inicio_s": 5, "fim_s": 10, "visual": "y", "texto_tela": "Passa aqui",
                  "audio": ["trilha_instrumental"]}]
        self.assertEqual(achados(base(cena=cenas)), [])

    def test_cena_sem_audio_nenhum_avisa(self):
        cenas = [{"id": "a", "inicio_s": 0, "fim_s": 5, "visual": "x", "texto_tela": "Pão"},
                 base()["cena"][1]]
        self.assertIn(("roteiro_cena_incompleta", AVISO), achados(base(cena=cenas)))

    def test_elemento_alem_da_ultima_cena_e_texto_vazio(self):
        el = [{"id": "e", "tipo": "texto_tela", "inicio_s": 8, "fim_s": 12}]
        r = achados(base(elemento=el))
        self.assertIn(("roteiro_estrutura", AVISO), r)
        self.assertIn(("roteiro_cena_incompleta", AVISO), r)

    def test_texto_na_tela_longo(self):
        cenas = [dict(base()["cena"][0], texto_tela="um dois três quatro cinco seis sete oito"),
                 base()["cena"][1]]
        self.assertIn(("roteiro_texto_tela", AVISO), achados(base(cena=cenas)))

    def test_sem_cenas_bloqueia(self):
        self.assertIn(("roteiro_estrutura", BLOQUEANTE), achados(base(cena=[])))


class TestGanchoMensagemCta(unittest.TestCase):
    def sem_texto_inicial(self, **extra):
        cenas = [{"id": "a", "inicio_s": 0, "fim_s": 5, "visual": "x", "audio": "trilha"},
                 {"id": "b", "inicio_s": 5, "fim_s": 10, "visual": "y", "fala": "Pão. Passa aqui."}]
        return base(cena=cenas, **extra)

    def test_gancho_ausente_pede_revisao(self):
        self.assertIn(("roteiro_gancho", AVISO), achados(self.sem_texto_inicial()))

    def test_gancho_visual_declarado_resolve(self):
        self.assertNotIn(("roteiro_gancho", AVISO),
                         achados(self.sem_texto_inicial(gancho="close do pão estalando")))

    def test_texto_simultaneo_no_inicio_conta_como_gancho(self):
        el = [{"id": "t", "tipo": "texto_tela", "inicio_s": 0.5, "fim_s": 3, "conteudo": "Olha isso"}]
        self.assertNotIn(("roteiro_gancho", AVISO), achados(self.sem_texto_inicial(elemento=el)))

    def test_janela_nao_configurada_so_informa(self):
        r = laudo(self.sem_texto_inicial(), cfg={})
        self.assertIn(("roteiro_gancho", INFO), [(a["regra"], a["severidade"]) for a in r["achados"]])

    def test_mensagem(self):
        self.assertIn(("roteiro_mensagem", AVISO), achados(base(mensagem_principal="")))
        self.assertIn(("roteiro_mensagem", AVISO), achados(base(termos_mensagem=["croissant"])))

    def test_cta_ausente_e_referencias(self):
        dados = base()
        del dados["cta"]
        self.assertIn(("roteiro_cta", AVISO), achados(dados))
        self.assertIn(("roteiro_cta", BLOQUEANTE),
                      achados(base(cta={"texto": "x", "forma": "visual", "cena": "nao-existe"})))

    def test_cta_visual_por_elemento_no_final(self):
        el = [{"id": "botao", "tipo": "cta_visual", "inicio_s": 7, "fim_s": 10, "conteudo": "Siga"}]
        self.assertEqual(achados(base(cta={"texto": "Siga", "forma": "visual", "elemento": "botao"},
                                      elemento=el)), [])

    def test_cta_visual_sem_referencia_pede_revisao(self):
        self.assertIn(("roteiro_cta", AVISO), achados(base(cta={"texto": "botão animado", "forma": "visual"})))

    def test_cta_antes_do_final_pede_revisao(self):
        self.assertIn(("roteiro_cta", AVISO), achados(base(cta={"texto": "Pão saindo", "forma": "falada"})))


class TestDuracao(unittest.TestCase):
    def test_tolerancia_limite_exato_e_acima(self):
        self.assertNotIn(("roteiro_duracao", AVISO), achados(base(duracao_alvo_s=11.5)))   # 13% < 15%
        self.assertIn(("roteiro_duracao", AVISO), achados(base(duracao_alvo_s=8)))        # 25%

    def test_limite_da_plataforma(self):
        self.assertNotIn(("roteiro_duracao", BLOQUEANTE), achados(base(), plataforma=plat(None)))
        self.assertIn(("roteiro_duracao", AVISO), achados(base(), plataforma=plat(5)))
        self.assertIn(("roteiro_duracao", BLOQUEANTE), achados(base(), plataforma=plat(5, "verificado")))

    def test_sem_taxa_de_fala_estimativa_e_desligada(self):
        r = laudo(base())
        self.assertIsNone(r["metricas"]["fala_estimada_s"])
        self.assertTrue(any("taxa de fala" in a["mensagem"] for a in r["achados"]))

    def test_com_taxa_configurada(self):
        cfg = dict(CFG, palavras_por_segundo=1)
        cenas = [dict(base()["cena"][0], fala="um dois três quatro cinco seis sete"),
                 base()["cena"][1]]
        r = laudo(base(cena=cenas), cfg=cfg)
        self.assertEqual(r["metricas"]["fala_estimada_s"], 9.0)
        self.assertIn(("roteiro_duracao", AVISO), [(a["regra"], a["severidade"]) for a in r["achados"]])


class TestRegrasDeTextoNoRoteiro(unittest.TestCase):
    def test_numero_sem_fato_aponta_a_cena(self):
        cenas = [dict(base()["cena"][0], fala="Vendemos 500 pães."), base()["cena"][1]]
        r = laudo(base(cena=cenas))
        a = next(a for a in r["achados"] if a["regra"] == "numero_sem_fato")
        self.assertEqual((a["severidade"], a["local"]), (BLOQUEANTE, "cena c1 · fala"))
        self.assertIn("500", a["trecho"])

    def test_fato_libera_o_numero(self):
        f = fato_completo(valores=("500",), contexto=("pão*", "pães"))
        cenas = [dict(base()["cena"][0], fala="Vendemos 500 pães."), base()["cena"][1]]
        self.assertNotIn("numero_sem_fato", [a["regra"] for a in laudo(base(cena=cenas), fatos=[f])["achados"]])

    def test_editorial_em_texto_de_elemento(self):
        el = [{"id": "e", "tipo": "legenda", "inicio_s": 0, "fim_s": 3, "conteudo": "No cenário atual"}]
        a = next(a for a in laudo(base(elemento=el))["achados"] if a["regra"] == "editorial_ia")
        self.assertEqual((a["natureza"], a["local"]), (REVISAO, "elemento e · legenda"))

    def test_laudo_tem_limites_e_exige_aprovacao_humana(self):
        r = laudo(base())
        self.assertIn("aprovacao_humana", r["exigencias_aprovacao"])
        self.assertIn("não foram analisados", r["limites_da_verificacao"][0])
        json.dumps(r)


def rodar(*args, ambiente=None):
    saida, erro = io.StringIO(), io.StringIO()
    with mock.patch.dict(os.environ, ambiente or {"SHIBA_DADOS": "", "GIT_DIR": "", "GIT_WORK_TREE": ""}), \
            contextlib.redirect_stdout(saida), contextlib.redirect_stderr(erro):
        codigo = main(list(args))
    return codigo, saida.getvalue(), erro.getvalue()


class TestCliRoteiro(unittest.TestCase):
    def test_fixtures(self):
        codigo, saida, _ = rodar("roteiro", "verificar", str(FIXTURES / "roteiro_ok.toml"),
                                 "--cliente", "exemplo-cafe", "--formato", "json",
                                 "--data-referencia", "2026-10-23")
        laudo_ok = json.loads(saida)
        self.assertEqual((codigo, laudo_ok["resumo"]["bloqueante"], laudo_ok["resumo"]["aviso"]), (0, 0, 0))
        codigo, saida, _ = rodar("roteiro", "verificar", str(FIXTURES / "roteiro_problemas.toml"),
                                 "--cliente", "exemplo-cafe", "--data-referencia", "2026-10-23")
        self.assertEqual(codigo, 1)
        self.assertIn("[cena meio]", saida)
        self.assertIn("não foram analisados", saida)

    def test_plataforma_do_roteiro_inexistente(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = Path(tmp) / "r.toml"
            r.write_text('plataforma = "orkut"\n', encoding="utf-8")
            codigo, _, erro = rodar("roteiro", "verificar", str(r), "--cliente", "exemplo-cafe")
            self.assertEqual(codigo, 2)
            self.assertIn("orkut", erro)


class TestIsolamentoRoteiro(unittest.TestCase):
    SEGREDO = "MARCADOR-SIGILOSO-RT9"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name).resolve()
        from shiba.dados import repositorio_que_contem
        if repositorio_que_contem(self.tmp):
            self.skipTest("pasta temporária dentro de repositório Git")
        self.dados = self.tmp / "dados"
        pasta = self.dados / "clientes" / "real1"
        pasta.mkdir(parents=True)
        (pasta / "perfil.toml").write_text('id = "real1"\nnome = "x"\nficticio = false\nsegmento = "gastronomia"\n',
                                           encoding="utf-8")
        (pasta / "fatos.toml").write_text("", encoding="utf-8")
        self.repo = self.tmp / "repo"
        (self.repo / ".git").mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def test_roteiro_real_dentro_de_repositorio_e_recusado(self):
        r = self.repo / "roteiro.toml"
        r.write_text((FIXTURES / "roteiro_ok.toml").read_text(encoding="utf-8"), encoding="utf-8")
        codigo, saida, erro = rodar("roteiro", "verificar", str(r), "--cliente", "real1",
                                    "--dados", str(self.dados))
        self.assertEqual((codigo, saida), (2, ""))
        self.assertIn("roteiro", erro)

    def test_roteiro_real_fora_do_git_funciona(self):
        r = self.tmp / "roteiro.toml"
        r.write_text((FIXTURES / "roteiro_ok.toml").read_text(encoding="utf-8"), encoding="utf-8")
        codigo, _, erro = rodar("roteiro", "verificar", str(r), "--cliente", "real1", "--dados", str(self.dados))
        self.assertEqual(erro, "")
        self.assertIn(codigo, (0, 1))

    def test_erro_de_roteiro_real_nao_vaza_conteudo_nem_caminho(self):
        r = self.tmp / "roteiro.toml"
        r.write_text(f'plataforma = "tiktok"\n[[cena]]\nid = "c1"\ninicio_s = "{self.SEGREDO}"\n',
                     encoding="utf-8")
        codigo, saida, erro = rodar("roteiro", "verificar", str(r), "--cliente", "real1", "--dados", str(self.dados))
        self.assertEqual(codigo, 2)
        self.assertNotIn(self.SEGREDO, erro + saida)
        self.assertNotIn(str(self.tmp), erro)


if __name__ == "__main__":
    unittest.main()
