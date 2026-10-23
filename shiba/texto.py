"""Utilitários de texto que preservam posições (offsets) do texto original."""
from __future__ import annotations

import re
import unicodedata

# Trechos em que números e hashtags não devem ser procurados.
URL = re.compile(r"https?://\S+|www\.\S+")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def dobrar(texto: str) -> str:
    """Minúsculas e sem acentos, com o MESMO comprimento do original.

    Cada caractere vira exatamente um caractere, para que uma posição
    encontrada no texto dobrado valha também no texto original. Caracteres
    cuja forma dobrada teria outro comprimento (ex.: "ß") ficam como estão.
    """
    saida = []
    for c in texto:
        base = "".join(
            ch for ch in unicodedata.normalize("NFD", c) if not unicodedata.combining(ch)
        ).casefold()
        if len(base) == 1:
            saida.append(base)
        elif len(c.lower()) == 1:
            saida.append(c.lower())
        else:
            saida.append(c)
    return "".join(saida)


def padrao_termo(termo: str) -> re.Pattern[str]:
    """Padrão para buscar `termo` no texto DOBRADO, como palavra ou expressão inteira.

    Espaços no termo aceitam qualquer espaço ou quebra de linha. Um "*" no fim
    vira busca por prefixo: "ferment*" casa "fermenta", "fermentação".
    """
    prefixo = termo.endswith("*")
    partes = [re.escape(p) for p in dobrar(termo.rstrip("*")).split()]
    fim = "" if prefixo else r"(?!\w)"
    return re.compile(r"(?<!\w)" + r"\s+".join(partes) + fim)


def intervalos(padrao: re.Pattern[str], texto: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in padrao.finditer(texto)]


def dentro(pos: int, faixas: list[tuple[int, int]]) -> bool:
    return any(ini <= pos < fim for ini, fim in faixas)


def linha_de(texto: str, pos: int) -> int:
    return texto.count("\n", 0, pos) + 1


def trecho(texto: str, inicio: int, fim: int, margem: int = 25) -> str:
    """Contexto curto ao redor de [inicio, fim), numa linha só."""
    a = max(0, inicio - margem)
    b = min(len(texto), fim + margem)
    corte = texto[a:b].replace("\n", " ⏎ ")
    return ("…" if a > 0 else "") + corte + ("…" if b < len(texto) else "")
