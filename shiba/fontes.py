"""Gera o fontes.md: a trilha de cada afirmação até o fato e a fonte que a sustentam."""
from __future__ import annotations

import hashlib

from .config import Fato

ROTULOS = {
    "forte": "vínculo forte (valor, unidade e contexto coincidem)",
    "apoiado": "apoiado por fato verificado da mesma categoria",
    "ambiguo": "AMBÍGUO: revisão humana",
    "unidade_divergente": "unidade divergente",
    "invalido": "fato sem validade (expirado ou contestado)",
    "nao_verificado": "fato não verificado (insuficiente para afirmação sensível)",
    "sem_fato": "SEM FATO",
    "estrutural": "número editorial: revisão humana",
    "vago": "quantidade vaga: revisão humana",
}


def _celula(valor: str) -> str:
    return str(valor).replace("|", "\\|").replace("\n", " ⏎ ")


def gerar_fontes_md(laudo: dict, texto: str, fatos: tuple[Fato, ...], arquivo: str = "") -> str:
    por_id = {f.id: f for f in fatos}
    status = {u["id"]: u["status"] for u in laudo["fatos_usados"]}
    resumo = laudo["resumo"]
    linhas = [
        "# Fontes da peça",
        "",
        "> Gerado automaticamente pelo `shiba verificar`. Os vínculos são **heurísticos** "
        "(valor, unidade e palavras de contexto): eles **não garantem** que uma afirmação "
        "seja verdadeira nem que se refira ao fato indicado. Cada linha precisa de revisão "
        "humana. Este arquivo não é aprovação.",
        "",
        "| Campo | Valor |",
        "|---|---|",
        f"| Cliente | {_celula(laudo['cliente'])} |",
        f"| Plataforma | {_celula(laudo['plataforma'])} |",
        f"| Arquivo | {_celula(arquivo or '—')} |",
        f"| SHA-256 do texto verificado | `{hashlib.sha256(texto.encode('utf-8')).hexdigest()}` |",
        f"| Data de referência | {laudo['data_referencia']} |",
        f"| Resultado da verificação | {laudo['resultado']} ({resumo['bloqueante']} bloqueante(s), "
        f"{resumo['aviso']} aviso(s)) |",
        "",
        "## Afirmações e vínculos",
        "",
    ]
    if laudo["vinculos"]:
        linhas += ["| # | Linha | Elemento | Frase | Fato(s) | Situação |",
                   "|---|---|---|---|---|---|"]
        for i, v in enumerate(laudo["vinculos"], 1):
            fatos_txt = ", ".join(f"{fid} ({status.get(fid, '?')})" for fid in v["fatos"]) or "—"
            linhas.append(
                f"| {i} | {v['linha']} | {_celula(v['elemento'])} | {_celula(v['frase'])} | "
                f"{_celula(fatos_txt)} | {ROTULOS.get(v['situacao'], v['situacao'])} |"
            )
    else:
        linhas.append("Nenhuma quantidade nem marcador sensível encontrado.")
    linhas += ["", "## Fatos citados", ""]
    if not laudo["fatos_usados"]:
        linhas.append("Nenhum fato citado.")
    for usado in laudo["fatos_usados"]:
        f = por_id[usado["id"]]
        linhas += [
            f"### {f.id}: {_celula(f.texto)}",
            "",
            f"- Status na data de referência: **{usado['status']}**"
            + (f" (válido até {f.valido_ate.isoformat()})" if f.valido_ate else ""),
            f"- Categoria: {f.categoria}",
            f"- Registro: `{_celula(f.origem or '—')}`",
        ]
        if f.fonte:
            linhas.append("- Fonte: " + "; ".join(f"{k}: {_celula(v)}" for k, v in f.fonte))
        else:
            linhas.append("- Fonte: **NÃO REGISTRADA** (sem rastreabilidade)")
        if f.verificacao:
            linhas.append("- Verificação: " + "; ".join(f"{k}: {_celula(v)}" for k, v in f.verificacao))
        else:
            linhas.append("- Verificação: não verificado")
        linhas.append("")
    pendentes = [a for a in laudo["achados"] if a["severidade"] in ("bloqueante", "aviso")]
    linhas += ["## Pendências", ""]
    if not pendentes:
        linhas.append("Nenhuma pendência automática. A revisão humana continua obrigatória.")
    for a in pendentes:
        local = f"linha {a['linha']}: " if "linha" in a else ""
        linhas.append(f"- **{a['severidade']}** `{a['regra']}`: {local}{_celula(a['mensagem'])}")
    return "\n".join(linhas) + "\n"
