"""Orquestra as regras e monta o laudo (dict serializável em JSON)."""
from __future__ import annotations

from .config import Cliente, Fato, Plataforma
from .numeros import extrair_numeros
from .regras import (
    BLOQUEANTE,
    SEVERIDADES,
    Achado,
    extrair_hashtags,
    regra_hashtags,
    regra_limite_caracteres,
    regra_numero_sem_fato,
    regra_palavras_proibidas,
)
from .texto import linha_de, trecho

ESQUEMA = "shiba.laudo/0.1"


def _achado_para_dict(texto: str, a: Achado) -> dict:
    d = {"regra": a.regra, "severidade": a.severidade, "mensagem": a.mensagem}
    if a.inicio is not None and a.fim is not None:
        d.update(inicio=a.inicio, fim=a.fim, linha=linha_de(texto, a.inicio),
                 trecho=trecho(texto, a.inicio, a.fim))
    return d


def verificar(texto: str, cliente: Cliente, fatos: tuple[Fato, ...],
              plataforma: Plataforma) -> dict:
    achados = (
        regra_hashtags(texto, cliente)
        + regra_palavras_proibidas(texto, cliente)
        + regra_numero_sem_fato(texto, fatos)
        + regra_limite_caracteres(texto, plataforma)
    )
    achados.sort(key=lambda a: (SEVERIDADES.index(a.severidade),
                                a.inicio if a.inicio is not None else -1))
    resumo = {s: sum(a.severidade == s for a in achados) for s in SEVERIDADES}
    return {
        "esquema": ESQUEMA,
        "cliente": cliente.id,
        "plataforma": plataforma.id,
        # "passou" significa só "sem achado bloqueante". Não é aprovação humana.
        "resultado": "bloqueado" if resumo[BLOQUEANTE] else "passou",
        "resumo": resumo,
        "metricas": {
            "caracteres": len(texto),
            "hashtags": len(extrair_hashtags(texto)),
            "numeros": len(extrair_numeros(texto)),
        },
        "achados": [_achado_para_dict(texto, a) for a in achados],
    }


def formatar_texto(laudo: dict, arquivo: str = "") -> str:
    r = laudo["resumo"]
    linhas = [
        f"Verificação · cliente {laudo['cliente']} · {laudo['plataforma']}"
        + (f" · {arquivo}" if arquivo else ""),
        f"Resultado: {laudo['resultado'].upper()} "
        f"({r['bloqueante']} bloqueante(s), {r['aviso']} aviso(s), {r['info']} info)",
        f"Métricas: {laudo['metricas']['caracteres']} caracteres, "
        f"{laudo['metricas']['hashtags']} hashtag(s), {laudo['metricas']['numeros']} número(s)",
    ]
    for a in laudo["achados"]:
        local = f" (linha {a['linha']})" if "linha" in a else ""
        linhas.append(f"[{a['severidade'].upper()}] {a['regra']}{local}: {a['mensagem']}")
        if "trecho" in a:
            linhas.append(f"    trecho: {a['trecho']}")
    linhas.append("Passar na verificação NÃO é aprovação humana.")
    return "\n".join(linhas)
