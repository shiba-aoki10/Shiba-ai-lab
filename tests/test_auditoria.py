"""Hashes canônicos e registro encadeado (Incremento 4A). Pastas temporárias fora do Git."""
import json
import tempfile
import threading
import unittest
from datetime import date
from pathlib import Path

from shiba.auditoria import GENESIS, ErroIntegridade, Registro, _hash_entrada, conferir_topo, exportar_topo
from shiba.hashes import canonico, hash_conteudo, hash_laudo, hash_objeto, id_do_achado


class TestHashes(unittest.TestCase):
    def test_canonico_independe_da_ordem_e_aceita_datas(self):
        self.assertEqual(canonico({"b": 1, "a": [1, (2, 3)]}), canonico({"a": [1, [2, 3]], "b": 1}))
        self.assertEqual(canonico({"d": date(2026, 10, 23)}), b'{"d":"2026-10-23"}')

    def test_conteudo_sensivel_a_qualquer_byte(self):
        base = hash_conteudo([("peca", "Pão quente.".encode())])
        for variante in ("Pão quente. ", "Pão quente.\n", "Pao quente.", "Pão  quente."):
            with self.subTest(variante=variante):
                self.assertNotEqual(hash_conteudo([("peca", variante.encode())]), base)

    def test_conteudo_inclui_cada_arquivo(self):
        a = hash_conteudo([("peca", b"x"), ("fatos_peca", b"1")])
        self.assertNotEqual(a, hash_conteudo([("peca", b"x"), ("fatos_peca", b"2")]))
        self.assertNotEqual(a, hash_conteudo([("peca", b"x")]))

    def test_laudo_ignora_data_mas_nao_o_resultado(self):
        laudo = {"esquema": "x", "resultado": "passou", "data_referencia": "2026-10-23",
                 "exigencias_aprovacao": ["aprovacao_humana"],
                 "achados": [{"regra": "r", "severidade": "aviso", "natureza": "tecnica", "mensagem": "m"}]}
        self.assertEqual(hash_laudo(laudo), hash_laudo(dict(laudo, data_referencia="2027-01-01")))
        outro = json.loads(json.dumps(laudo))
        outro["achados"][0]["severidade"] = "bloqueante"
        self.assertNotEqual(hash_laudo(laudo), hash_laudo(outro))

    def test_id_do_achado_estavel(self):
        a = {"regra": "r", "severidade": "aviso", "mensagem": "m", "inicio": 3}
        self.assertEqual(id_do_achado(a), id_do_achado(dict(a, inicio=99)))
        self.assertNotEqual(id_do_achado(a), id_do_achado(dict(a, mensagem="n")))
        self.assertEqual(len(id_do_achado(a)), 12)

    def test_hash_objeto(self):
        self.assertEqual(len(hash_objeto({"a": 1})), 64)


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.estado = Path(self._tmp.name)
        self.reg = Registro(self.estado, "c1")
        for i in range(3):
            self.reg.anexar("evento", {"i": i})

    def tearDown(self):
        self._tmp.cleanup()

    def linhas(self):
        return [json.loads(l) for l in self.reg.log.read_text(encoding="utf-8").splitlines()]

    def gravar(self, entradas, ancora=True):
        self.reg.log.write_text("".join(json.dumps(e) + "\n" for e in entradas), encoding="utf-8")
        if ancora:
            topo = {"seq": len(entradas), "hash": entradas[-1]["hash"] if entradas else GENESIS}
            self.reg.ancora.write_text(json.dumps(topo), encoding="utf-8")

    def assertAdulterado(self):
        with self.assertRaises(ErroIntegridade):
            self.reg.ler()
        with self.assertRaises(ErroIntegridade):
            self.reg.anexar("depois", {})  # não estende histórico adulterado


class TestCadeia(Base):
    def test_cadeia_integra(self):
        entradas = self.reg.ler()
        self.assertEqual([e["seq"] for e in entradas], [1, 2, 3])
        self.assertEqual(entradas[0]["anterior"], GENESIS)
        self.assertEqual(entradas[1]["anterior"], entradas[0]["hash"])
        self.assertEqual(self.reg.topo()["seq"], 3)

    def test_registro_vazio(self):
        self.assertEqual(Registro(self.estado, "outro").ler(), [])

    def test_campo_editado(self):
        e = self.linhas()
        e[1]["dados"]["i"] = 99
        self.gravar(e, ancora=False)
        self.assertAdulterado()

    def test_campo_editado_com_hash_recalculado_quebra_a_proxima(self):
        e = self.linhas()
        e[1]["dados"]["i"] = 99
        e[1]["hash"] = _hash_entrada(2, e[1]["anterior"], e[1]["evento"], e[1]["dados"])
        self.gravar(e, ancora=False)
        self.assertAdulterado()

    def test_ultima_linha_editada_com_hash_recalculado_quebra_a_ancora(self):
        e = self.linhas()
        e[2]["dados"]["i"] = 99
        e[2]["hash"] = _hash_entrada(3, e[2]["anterior"], e[2]["evento"], e[2]["dados"])
        self.gravar(e, ancora=False)
        self.assertAdulterado()

    def test_remocao_no_meio(self):
        e = self.linhas()
        self.gravar([e[0], e[2]], ancora=False)
        self.assertAdulterado()

    def test_troca_de_ordem(self):
        e = self.linhas()
        self.gravar([e[1], e[0], e[2]], ancora=False)
        self.assertAdulterado()

    def test_insercao_forjada(self):
        e = self.linhas()
        falsa = {"seq": 2, "anterior": e[0]["hash"], "evento": "aprovacao", "dados": {}}
        falsa["hash"] = _hash_entrada(2, falsa["anterior"], "aprovacao", {})
        self.gravar([e[0], falsa, e[1], e[2]], ancora=False)
        self.assertAdulterado()

    def test_truncamento_no_fim_pego_pela_ancora(self):
        self.gravar(self.linhas()[:2], ancora=False)
        self.assertAdulterado()

    def test_ancora_apagada_ou_log_apagado(self):
        self.reg.ancora.unlink()
        self.assertAdulterado()

    def test_log_apagado_com_ancora(self):
        self.reg.log.unlink()
        self.assertAdulterado()

    def test_json_corrompido_e_chave_extra(self):
        for estrago in ("{quebrado", json.dumps(dict(self.linhas()[0], extra=1))):
            with self.subTest(estrago=estrago[:10]):
                linhas = self.reg.log.read_text(encoding="utf-8").splitlines()
                linhas[0] = estrago
                self.reg.log.write_text("\n".join(linhas) + "\n", encoding="utf-8")
                self.assertAdulterado()


class TestLimiteDocumentado(Base):
    def reescrever_tudo(self):
        """Quem controla a máquina reescreve cadeia E âncora: a cadeia sozinha não vê."""
        novas, anterior = [], GENESIS
        for seq, i in enumerate([7, 8], 1):
            dados = {"i": i}
            h = _hash_entrada(seq, anterior, "evento", dados)
            novas.append({"seq": seq, "anterior": anterior, "evento": "evento", "dados": dados, "hash": h})
            anterior = h
        self.gravar(novas)

    def test_reescrita_total_nao_e_detectada_pela_cadeia(self):
        self.reescrever_tudo()
        self.assertEqual(len(self.reg.ler()), 2)  # limite: evidente a adulteração, não inviolável

    def test_reescrita_total_detectada_pelo_topo_exportado(self):
        copia = self.estado.parent / f"{self.estado.name}-topo.json"
        try:
            exportar_topo(self.reg, copia)
            conferir_topo(self.reg, copia)       # íntegro
            self.reg.anexar("depois", {})
            conferir_topo(self.reg, copia)       # crescer é aceito
            self.reescrever_tudo()
            with self.assertRaisesRegex(ErroIntegridade, "reescrito ou truncado"):
                conferir_topo(self.reg, copia)
        finally:
            copia.unlink(missing_ok=True)


class TestConcorrencia(unittest.TestCase):
    def test_escritas_simultaneas_mantem_a_cadeia(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = Registro(Path(tmp), "c1")

            def escrever(n):
                for i in range(25):
                    Registro(Path(tmp), "c1").anexar("evento", {"t": n, "i": i})

            threads = [threading.Thread(target=escrever, args=(n,)) for n in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual([e["seq"] for e in reg.ler()], list(range(1, 101)))


if __name__ == "__main__":
    unittest.main()
