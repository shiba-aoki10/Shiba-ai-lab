"""Números escritos por extenso em pt-BR (heurística, não garantia).

Reconhece cardinais ("três", "vinte e cinco", "dois mil e quinhentos",
"um milhão") e quantidades vagas ou relativas ("dezenas", "o dobro",
"metade", "três vezes mais"). Limitações em docs/fase-1/INCREMENTO-1.md:
- "um"/"uma" sozinhos são tratados como artigo e ignorados;
- ordinais por extenso ("primeiro", "terceira") não são números aqui;
- frações e decimais por extenso ("dois e meio") não são reconhecidos.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .texto import dentro, dobrar

BASICOS = {
    "zero": 0, "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4,
    "cinco": 5, "seis": 6, "sete": 7, "oito": 8, "nove": 9, "dez": 10, "onze": 11,
    "doze": 12, "treze": 13, "catorze": 14, "quatorze": 14, "quinze": 15,
    "dezesseis": 16, "dezessete": 17, "dezoito": 18, "dezenove": 19, "vinte": 20,
    "trinta": 30, "quarenta": 40, "cinquenta": 50, "sessenta": 60, "setenta": 70,
    "oitenta": 80, "noventa": 90, "cem": 100, "cento": 100,
    "duzentos": 200, "duzentas": 200, "trezentos": 300, "trezentas": 300,
    "quatrocentos": 400, "quatrocentas": 400, "quinhentos": 500, "quinhentas": 500,
    "seiscentos": 600, "seiscentas": 600, "setecentos": 700, "setecentas": 700,
    "oitocentos": 800, "oitocentas": 800, "novecentos": 900, "novecentas": 900,
}
ESCALAS = {"mil": 1000, "milhao": 10**6, "milhoes": 10**6, "bilhao": 10**9, "bilhoes": 10**9}
VAGOS = {"dezenas", "centenas", "milhares", "dobro", "triplo", "quadruplo", "metade"}
ARTIGOS = {"um", "uma"}

_PALAVRA = re.compile(r"\w+")
_POR_CENTO = re.compile(r"[ \t]+por[ \t]+cento(?!\w)")
_VEZES = re.compile(r"(?<!\w)vezes[ \t]+(?:mais|menos)(?!\w)")


@dataclass(frozen=True)
class Extenso:
    inicio: int
    fim: int
    valor: int | None  # None: quantidade vaga ou relativa
    percentual: bool = False


def _so_espaco(texto: str, a: int, b: int) -> bool:
    return texto[a:b].strip() == ""


def extrair_extenso(texto: str, ignorar: list[tuple[int, int]] = ()) -> list[Extenso]:
    """Números por extenso e quantidades vagas, com posições no texto original."""
    dob = dobrar(texto)
    toks = [m for m in _PALAVRA.finditer(dob) if not dentro(m.start(), ignorar)]
    achados: list[Extenso] = []
    i = 0
    while i < len(toks):
        palavra = toks[i].group()
        if palavra in VAGOS:
            achados.append(Extenso(toks[i].start(), toks[i].end(), None))
            i += 1
            continue
        if palavra not in BASICOS and palavra not in ESCALAS:
            i += 1
            continue
        total, atual, j, usadas = 0, 0, i, []
        while j < len(toks):
            w = toks[j].group()
            if j > i and not _so_espaco(dob, toks[j - 1].end(), toks[j].start()):
                break
            if w in BASICOS:
                # Sem "e", dois básicos seguidos não se combinam ("três cinco").
                if usadas and usadas[-1] in BASICOS:
                    break
                atual += BASICOS[w]
            elif w in ESCALAS:
                if usadas and usadas[-1] in ESCALAS:
                    break
                total += (atual or 1) * ESCALAS[w]
                atual = 0
            elif w == "e" and j + 1 < len(toks) and toks[j + 1].group() in BASICOS:
                # "vinte e três", "cento e vinte", "mil e quinhentos": o "e" só une
                # uma parte redonda a uma menor. "três e cinco" não é um número.
                proximo = BASICOS[toks[j + 1].group()]
                base = atual if atual else total
                if not (base and base % 10 == 0 and base > proximo):
                    break
                if not _so_espaco(dob, toks[j].end(), toks[j + 1].start()):
                    break
            else:
                break
            usadas.append(w)
            j += 1
        while usadas and usadas[-1] == "e":  # nunca termina em "e"
            usadas.pop()
            j -= 1
        inicio, fim = toks[i].start(), toks[j - 1].end()
        valor = total + atual
        if usadas in (["um"], ["uma"]):
            pass  # artigo
        elif len(usadas) == 1 and usadas[0] in ("milhoes", "bilhoes"):
            achados.append(Extenso(inicio, fim, None))  # "milhões de pessoas": vago
        else:
            m = _POR_CENTO.match(dob, fim)
            if m:
                fim = m.end()
            achados.append(Extenso(inicio, fim, valor, bool(m)))
        i = j
        while i < len(toks) and toks[i].start() < fim:  # pula "por cento" já consumido
            i += 1
    # "três vezes mais", "5 vezes menos": comparação relativa, sempre vaga.
    for m in _VEZES.finditer(dob):
        if not dentro(m.start(), ignorar):
            achados.append(Extenso(m.start(), m.end(), None))
    return sorted(achados, key=lambda e: e.inicio)
