"""Detecção de números escritos com algarismos, em convenção pt-BR.

Limitações conhecidas (ver docs/fase-1/INCREMENTO-0.md):
- números por extenso ("três", "mil", "o dobro") NÃO são detectados;
- "1.500" é lido como mil e quinhentos (pt-BR), nunca como 1,5 (en-US);
- sinal negativo é ignorado ("-5" vira 5);
- números colados a letras ("covid19", "4K") SÃO detectados, de propósito.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from .texto import EMAIL, URL, dentro, intervalos

# Número: dígitos com separadores . , / : opcionais, hora no formato 18h30 e
# percentual opcional. Não pode começar no meio de outro número.
_NUMERO = re.compile(r"(?<![\d.,])\d+(?:[.,/:]\d+)*(?:h\d{2}(?!\d))?(?:[  ]?%)?")
# Hashtags e menções: números dentro delas não são afirmações.
_MARCADORES = re.compile(r"(?<!\w)[#@][\w.]*\w")
# Enumeração no início da linha: "1. ", "2) ".
_ENUMERACAO = re.compile(r"(?m)^[ \t]*\d{1,2}[.)](?=\s)")
# Emoji de tecla numérica (1️⃣): o dígito é seguido de U+FE0F? U+20E3.
_TECLA = re.compile("️?⃣")

_MILHAR_PT = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?")
_DECIMAL_VIRGULA = re.compile(r"\d+,\d+")
_SIMPLES = re.compile(r"\d+(?:\.\d+)?")


@dataclass(frozen=True)
class Numero:
    bruto: str
    inicio: int
    fim: int
    chave: tuple[str, str]  # (tipo, valor canônico); tipo: valor | percentual | literal


def _para_decimal(corpo: str) -> Decimal | None:
    if _MILHAR_PT.fullmatch(corpo):
        return Decimal(corpo.replace(".", "").replace(",", "."))
    if _DECIMAL_VIRGULA.fullmatch(corpo):
        return Decimal(corpo.replace(",", "."))
    if _SIMPLES.fullmatch(corpo):
        return Decimal(corpo)
    return None


def chave_de(token: str) -> tuple[str, str]:
    """Forma canônica usada para comparar a legenda com os fatos.

    "1.500" e "1500" têm a mesma chave; "30%" e "30" têm chaves diferentes.
    Datas e horas ("23/10", "18h30") são comparadas literalmente.
    """
    percentual = token.endswith("%")
    corpo = token.rstrip("%").strip("  ")
    if re.search(r"[/:h]", corpo):
        return ("literal", corpo.lower())
    valor = _para_decimal(corpo)
    if valor is None:
        return ("literal", corpo)
    canonico = format(valor.normalize(), "f")
    return ("percentual" if percentual else "valor", canonico)


def extrair_numeros(texto: str) -> list[Numero]:
    ignorar = (
        intervalos(URL, texto)
        + intervalos(EMAIL, texto)
        + intervalos(_MARCADORES, texto)
        + intervalos(_ENUMERACAO, texto)
    )
    achados = []
    for m in _NUMERO.finditer(texto):
        if dentro(m.start(), ignorar) or _TECLA.match(texto, m.end()):
            continue
        achados.append(Numero(m.group(), m.start(), m.end(), chave_de(m.group())))
    return achados
