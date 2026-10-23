"""Registro de auditoria encadeado por hashes (Incremento 4A).

Cada linha (JSON) = {seq, anterior, evento, dados, hash}, onde
hash = SHA-256(canônico({seq, anterior, evento, dados})) e `anterior` é o
hash da linha anterior (a primeira usa 64 zeros). Uma âncora separada guarda
o último seq e hash.

O que isso DETECTA: edição de qualquer campo, remoção no meio, troca de
ordem, inserção forjada, hash adulterado e, pela âncora, remoção de linhas
do fim.

O que isso NÃO impede: quem controla a máquina pode reescrever a cadeia
INTEIRA e a âncora juntas. O registro é EVIDENTE A ADULTERAÇÕES, NÃO
INVIOLÁVEL. Para detectar até isso, exporte o hash de topo para um lugar
independente (`exportar_topo`) e compare depois.

Toda leitura confere a cadeia inteira e FALHA FECHADA: se a integridade não
puder ser confirmada, nada é considerado válido.
"""
from __future__ import annotations

import contextlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .config import ErroConfig
from .hashes import canonico, sha256

GENESIS = "0" * 64


class ErroIntegridade(ErroConfig):
    """Histórico ou dependência cuja integridade não pôde ser confirmada."""


def _hash_entrada(seq: int, anterior: str, evento: str, dados: dict) -> str:
    return sha256(canonico({"seq": seq, "anterior": anterior, "evento": evento, "dados": dados}))


@contextlib.contextmanager
def trava(caminho: Path):
    """Trava exclusiva entre processos (POSIX: flock; Windows: msvcrt)."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(caminho, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        if os.name == "posix":
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX)
        else:  # pragma: no cover - Windows
            import msvcrt
            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        yield
    finally:
        if os.name == "posix":
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _gravar_atomico(caminho: Path, conteudo: bytes) -> None:
    tmp = caminho.with_name(caminho.name + ".tmp")
    with open(tmp, "wb") as f:
        f.write(conteudo)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, caminho)


class Registro:
    """Registro encadeado de UM cliente, dentro do diretório de estado."""

    def __init__(self, estado: Path, cliente: str):
        base = Path(estado) / "auditoria"
        self.log = base / f"{cliente}.jsonl"
        self.ancora = base / f"{cliente}.ancora"
        self.trava = base / f"{cliente}.trava"
        self.cliente = cliente

    # ---- leitura (sempre verificada) ------------------------------------

    def ler(self) -> list[dict]:
        """Todas as entradas, depois de conferir cadeia e âncora. Falha fechada."""
        existe_log, existe_ancora = self.log.exists(), self.ancora.exists()
        if not existe_log and not existe_ancora:
            return []
        if existe_log != existe_ancora:
            raise ErroIntegridade("histórico ou âncora ausente; integridade não confirmada")
        try:
            linhas = self.log.read_bytes().decode("utf-8").splitlines()
            ancora = json.loads(self.ancora.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            raise ErroIntegridade("histórico ou âncora ilegível; integridade não confirmada") from None
        entradas, anterior = [], GENESIS
        for n, linha in enumerate(linhas, 1):
            try:
                e = json.loads(linha)
                seq, ant, evento, dados, h = e["seq"], e["anterior"], e["evento"], e["dados"], e["hash"]
            except (json.JSONDecodeError, KeyError, TypeError):
                raise ErroIntegridade(f"histórico corrompido na linha {n}") from None
            if seq != n or ant != anterior or set(e) != {"seq", "anterior", "evento", "dados", "hash"}:
                raise ErroIntegridade(f"cadeia quebrada na linha {n} (ordem, remoção ou inserção)")
            if _hash_entrada(seq, ant, evento, dados) != h:
                raise ErroIntegridade(f"hash não confere na linha {n} (conteúdo alterado)")
            entradas.append(e)
            anterior = h
        topo = {"seq": len(entradas), "hash": anterior}
        if ancora != topo:
            raise ErroIntegridade("histórico não confere com a âncora (linhas removidas do fim "
                                  "ou âncora alterada)")
        return entradas

    def topo(self) -> dict:
        entradas = self.ler()
        return {"cliente": self.cliente, "seq": len(entradas),
                "hash": entradas[-1]["hash"] if entradas else GENESIS}

    # ---- escrita (só acréscimo, sob trava) ------------------------------

    def anexar(self, evento: str, dados: dict) -> dict:
        """Acrescenta um evento. Recusa se o histórico atual não estiver íntegro."""
        with trava(self.trava):
            return self.anexar_sem_trava(evento, dados)

    def anexar_sem_trava(self, evento: str, dados: dict) -> dict:
        """Para quem JÁ detém a trava (operações compostas, como a liberação)."""
        entradas = self.ler()
        seq = len(entradas) + 1
        anterior = entradas[-1]["hash"] if entradas else GENESIS
        dados = dict(dados, registrado_em=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        entrada = {"seq": seq, "anterior": anterior, "evento": evento, "dados": dados,
                   "hash": _hash_entrada(seq, anterior, evento, dados)}
        self.log.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log, "ab") as f:
            f.write(canonico(entrada) + b"\n")
            f.flush()
            os.fsync(f.fileno())
        _gravar_atomico(self.ancora, canonico({"seq": seq, "hash": entrada["hash"]}))
        return entrada


def exportar_topo(registro: Registro, destino: Path) -> dict:
    """Grava o hash de topo num arquivo, para guardar num lugar INDEPENDENTE.

    Comparar depois com `conferir_topo` revela até reescrita total do
    histórico, desde que a cópia exportada não tenha sido alterada também.
    """
    topo = registro.topo()
    topo["exportado_em"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    Path(destino).write_bytes(canonico(topo) + b"\n")
    return topo


def conferir_topo(registro: Registro, exportado: Path) -> None:
    """Confere que o histórico atual CONTÉM o topo exportado antes (prefixo)."""
    try:
        salvo = json.loads(Path(exportado).read_text(encoding="utf-8"))
        seq, h = salvo["seq"], salvo["hash"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        raise ErroIntegridade("topo exportado ilegível") from None
    entradas = registro.ler()
    if seq == 0:
        return
    if seq > len(entradas) or entradas[seq - 1]["hash"] != h:
        raise ErroIntegridade("o histórico atual não contém o topo exportado: o histórico foi "
                              "reescrito ou truncado depois da exportação")
