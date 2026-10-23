"""Unidades de medida reconhecidas logo depois de um número (forma dobrada → canônica)."""
from __future__ import annotations

from .texto import dobrar

SINONIMOS = {
    "h": "hora", "hr": "hora", "hrs": "hora", "hora": "hora", "horas": "hora",
    "min": "minuto", "minuto": "minuto", "minutos": "minuto",
    "seg": "segundo", "segundo": "segundo", "segundos": "segundo",
    "dia": "dia", "dias": "dia",
    "semana": "semana", "semanas": "semana",
    "mes": "mes", "meses": "mes",
    "ano": "ano", "anos": "ano",
    "kg": "kg", "quilo": "kg", "quilos": "kg",
    "g": "g", "grama": "g", "gramas": "g",
    "l": "litro", "litro": "litro", "litros": "litro", "ml": "ml",
    "km": "km", "m": "metro", "metro": "metro", "metros": "metro", "cm": "cm",
    "real": "brl", "reais": "brl", "brl": "brl",
}


def normalizar(unidade: str) -> str:
    """Forma canônica de uma unidade. Desconhecida: devolvida dobrada, sem espaços extras."""
    chave = dobrar(unidade.strip())
    return SINONIMOS.get(chave, chave)
