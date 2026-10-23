"""Orquestra as regras e monta o laudo (dict serializável em JSON)."""
from __future__ import annotations

from datetime import date

from .afirmacoes import analisar, status_efetivo
from .config import Cliente, Fato, Plataforma
from .numeros import extrair_numeros
from .regras import (
    AVISO,
    BLOQUEANTE,
    SEVERIDADES,
    Achado,
    extrair_hashtags,
    regra_afirmacoes_sensiveis,
    regra_hashtags,
    regra_limite_caracteres,
    regra_numero_por_extenso,
    regra_numero_sem_fato,
    regra_palavras_proibidas,
    regra_vinculo_fatos,
)
from .texto import linha_de, trecho

# Os campos do Incremento 1 (data_referencia, requer_revisao_humana, vinculos,
# fatos_usados) foram ADICIONADOS; nenhum campo do 0.1 mudou de sentido.
ESQUEMA = "shiba.laudo/0.1"


def _achado_para_dict(texto: str, a: Achado) -> dict:
    d = {"regra": a.regra, "severidade": a.severidade, "mensagem": a.mensagem}
    if a.inicio is not None and a.fim is not None:
        d.update(inicio=a.inicio, fim=a.fim, linha=linha_de(texto, a.inicio),
                 trecho=trecho(texto, a.inicio, a.fim))
    return d


def _vinculos_para_dict(texto: str, fatos: tuple[Fato, ...], hoje: date,
                        categorias: tuple[str, ...]) -> list[dict]:
    saida = []
    for v in analisar(texto, fatos, hoje, categorias):
        d = {
            "elemento": v.elemento,
            "tipo": v.tipo,
            "situacao": v.situacao,
            "linha": linha_de(texto, v.inicio),
            "inicio": v.inicio,
            "fim": v.fim,
            "frase": texto[v.frase[0]:v.frase[1]],
            "fatos": [f.id for f in v.fatos],
        }
        if v.categoria:
            d.update(categoria=v.categoria, forca=v.forca)
        saida.append(d)
    return saida


def _fatos_usados(vinculos: list[dict], fatos: tuple[Fato, ...], hoje: date) -> list[dict]:
    """Fatos citados por vínculos que sustentam (forte, apoiado) ou que pedem revisão."""
    por_id = {f.id: f for f in fatos}
    usados: dict[str, set[str]] = {}
    for v in vinculos:
        for fid in v["fatos"]:
            usados.setdefault(fid, set()).add(v["situacao"])
    return [
        {"id": fid, "status": status_efetivo(por_id[fid], hoje),
         "categoria": por_id[fid].categoria, "situacoes": sorted(sits),
         "tem_fonte": por_id[fid].fonte is not None}
        for fid, sits in usados.items()
    ]


def verificar(texto: str, cliente: Cliente, fatos: tuple[Fato, ...],
              plataforma: Plataforma, hoje: date | None = None) -> dict:
    hoje = hoje or date.today()
    achados = (
        regra_hashtags(texto, cliente)
        + regra_palavras_proibidas(texto, cliente)
        + regra_numero_sem_fato(texto, fatos, hoje)
        + regra_numero_por_extenso(texto, fatos, hoje)
        + regra_vinculo_fatos(texto, fatos, cliente, hoje)
        + regra_afirmacoes_sensiveis(texto, fatos, cliente, hoje)
        + regra_limite_caracteres(texto, plataforma)
    )
    achados.sort(key=lambda a: (SEVERIDADES.index(a.severidade),
                                a.inicio if a.inicio is not None else -1))
    resumo = {s: sum(a.severidade == s for a in achados) for s in SEVERIDADES}
    vinculos = _vinculos_para_dict(texto, fatos, hoje, cliente.categorias_sensiveis)
    return {
        "esquema": ESQUEMA,
        "cliente": cliente.id,
        "plataforma": plataforma.id,
        "data_referencia": hoje.isoformat(),
        # "passou" significa só "sem achado bloqueante". Não é aprovação humana.
        "resultado": "bloqueado" if resumo[BLOQUEANTE] else "passou",
        # Todo aviso precisa ser reconhecido por uma pessoa antes de aprovar.
        "requer_revisao_humana": resumo[AVISO] > 0,
        "resumo": resumo,
        "metricas": {
            "caracteres": len(texto),
            "hashtags": len(extrair_hashtags(texto)),
            "numeros": len(extrair_numeros(texto)),
        },
        "achados": [_achado_para_dict(texto, a) for a in achados],
        "vinculos": vinculos,
        "fatos_usados": _fatos_usados(vinculos, fatos, hoje),
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
    if laudo.get("requer_revisao_humana"):
        linhas.append(f"Revisão humana obrigatória: {r['aviso']} aviso(s) a reconhecer.")
    for a in laudo["achados"]:
        local = f" (linha {a['linha']})" if "linha" in a else ""
        linhas.append(f"[{a['severidade'].upper()}] {a['regra']}{local}: {a['mensagem']}")
        if "trecho" in a:
            linhas.append(f"    trecho: {a['trecho']}")
    linhas.append("Passar na verificação NÃO é aprovação humana.")
    return "\n".join(linhas)
