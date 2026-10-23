"""Carga e validação dos léxicos versionados em conhecimento/pt-BR/."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .config import RAIZ, ErroConfig
from .texto import dobrar

DIR_CONHECIMENTO = RAIZ / "conhecimento" / "pt-BR"
CATEGORIAS_EDITORIAIS = ("ia", "cliche", "muleta")


@dataclass(frozen=True)
class Expressao:
    termo: str
    categoria: str
    justificativa: str
    sugestao: str
    severidade: str = "info"


@dataclass(frozen=True)
class Lexico:
    expressoes: tuple[Expressao, ...]
    stopwords: frozenset[str]


def _ler(caminho: Path) -> dict:
    try:
        with caminho.open("rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        raise ErroConfig(f"léxico não encontrado: {caminho.name}") from None
    except tomllib.TOMLDecodeError as e:
        raise ErroConfig(f"léxico inválido em {caminho.name}: {e}") from None


def _texto(entrada: dict, campo: str, origem: str) -> str:
    valor = entrada.get(campo)
    if not isinstance(valor, str) or not valor.strip():
        raise ErroConfig(f"{origem}: campo obrigatório ausente ou vazio: {campo}")
    return valor.strip()


@lru_cache(maxsize=8)
def carregar_lexico_editorial(caminho: str = str(DIR_CONHECIMENTO / "editorial.toml")) -> Lexico:
    """Léxico editorial validado: toda entrada tem categoria, justificativa e sugestão."""
    dados = _ler(Path(caminho))
    entradas, vistos = [], set()
    for i, e in enumerate(dados.get("expressao", []), 1):
        origem = f"editorial.toml expressão #{i}"
        if not isinstance(e, dict):
            raise ErroConfig(f"{origem}: formato inválido")
        termo = _texto(e, "termo", origem)
        categoria = _texto(e, "categoria", origem)
        if categoria not in CATEGORIAS_EDITORIAIS:
            raise ErroConfig(f"{origem}: categoria deve ser uma de {CATEGORIAS_EDITORIAIS}")
        severidade = e.get("severidade", "info")
        if severidade not in ("info", "aviso"):
            # Alerta editorial nunca bloqueia: é heurística, não verdade absoluta.
            raise ErroConfig(f"{origem}: severidade deve ser 'info' ou 'aviso'")
        chave = dobrar(termo)
        if chave in vistos:
            raise ErroConfig(f"{origem}: termo repetido: {termo}")
        vistos.add(chave)
        entradas.append(Expressao(termo, categoria, _texto(e, "justificativa", origem),
                                  _texto(e, "sugestao", origem), severidade))
    stop = dados.get("stopwords", {}).get("palavras", [])
    if not isinstance(stop, list) or not all(isinstance(p, str) for p in stop):
        raise ErroConfig("editorial.toml: [stopwords] palavras deve ser lista de textos")
    return Lexico(tuple(entradas), frozenset(dobrar(p) for p in stop))
