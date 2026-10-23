"""Orquestra as regras e monta o laudo (dict serializável em JSON)."""
from __future__ import annotations

from datetime import date

from .afirmacoes import analisar, status_efetivo
from .config import Cliente, Fato, Plataforma
from .numeros import extrair_numeros
from .editorial import revisar
from .lexico import Lexico, carregar_lexico_editorial
from .regras import (
    AVISO,
    BLOQUEANTE,
    NATUREZAS,
    NORMATIVA,
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

# O motor só lê texto. Declarado em todo laudo, para ninguém confundir
# "passou" com uma análise da peça final.
LIMITES_DA_VERIFICACAO = (
    "Só o texto foi verificado. Imagem, áudio e vídeo finais NÃO foram analisados "
    "(legendas queimadas, falas gravadas, trilha, cortes e elementos visuais podem "
    "conter afirmações que este laudo não viu).",
    "Alertas editoriais são heurísticas de estilo: explicáveis, configuráveis e "
    "sujeitos à revisão humana; não são erros obrigatórios.",
    "Nenhuma conclusão jurídica ou normativa é feita pelo motor.",
)


def exigencias_aprovacao(achados: list[dict]) -> list[str]:
    """O que uma pessoa precisa fazer antes de qualquer aprovação.

    Sempre inclui aprovação humana: nenhum laudo aprova uma peça sozinho.
    """
    exigencias = ["aprovacao_humana"]
    if any(a["severidade"] == BLOQUEANTE for a in achados):
        exigencias.insert(0, "corrigir_bloqueantes")
    if any(a["severidade"] == AVISO for a in achados):
        exigencias.append("reconhecer_avisos")
    if any(a["natureza"] == NORMATIVA for a in achados):
        exigencias.append("validacao_normativa_pelo_responsavel_competente")
    return exigencias


def _achado_para_dict(texto: str, a: Achado) -> dict:
    d = {"regra": a.regra, "severidade": a.severidade, "natureza": a.natureza,
         "mensagem": a.mensagem}
    if a.justificativa:
        d["justificativa"] = a.justificativa
    if a.sugestao:
        d["sugestao"] = a.sugestao
    if a.local:
        d["local"] = a.local
    if a.inicio is not None and a.fim is not None:
        d.update(inicio=a.inicio, fim=a.fim, linha=linha_de(texto, a.inicio),
                 trecho=trecho(texto, a.inicio, a.fim))
    return d


def achados_de_texto(texto: str, cliente: Cliente, fatos: tuple[Fato, ...], hoje: date,
                     lexico: Lexico) -> list[Achado]:
    """Regras que valem para QUALQUER texto de uma peça (legenda, fala, texto na tela).

    Não inclui o que é próprio da legenda (hashtags, limite de caracteres).
    """
    return (
        regra_palavras_proibidas(texto, cliente)
        + regra_numero_sem_fato(texto, fatos, hoje)
        + regra_numero_por_extenso(texto, fatos, hoje)
        + regra_vinculo_fatos(texto, fatos, cliente, hoje)
        + regra_afirmacoes_sensiveis(texto, fatos, cliente, hoje)
        + revisar(texto, cliente.secoes.get("editorial", {}), lexico)
    )


def ordenar(achados: list[Achado]) -> list[Achado]:
    return sorted(achados, key=lambda a: (SEVERIDADES.index(a.severidade),
                                          a.inicio if a.inicio is not None else -1))


def resumo_de(achados: list[Achado]) -> dict:
    return {s: sum(a.severidade == s for a in achados) for s in SEVERIDADES}


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
              plataforma: Plataforma, hoje: date | None = None,
              lexico: Lexico | None = None) -> dict:
    hoje = hoje or date.today()
    lexico = lexico or carregar_lexico_editorial()
    achados = ordenar(
        regra_hashtags(texto, cliente)
        + achados_de_texto(texto, cliente, fatos, hoje, lexico)
        + regra_limite_caracteres(texto, plataforma)
    )
    resumo = resumo_de(achados)
    vinculos = _vinculos_para_dict(texto, fatos, hoje, cliente.categorias_sensiveis)
    achados_dict = [_achado_para_dict(texto, a) for a in achados]
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
        "por_natureza": {n: sum(a.natureza == n for a in achados) for n in NATUREZAS},
        "requer_validacao_normativa": any(a.natureza == NORMATIVA for a in achados),
        "exigencias_aprovacao": exigencias_aprovacao(achados_dict),
        "limites_da_verificacao": list(LIMITES_DA_VERIFICACAO),
        "achados": achados_dict,
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
    if laudo.get("requer_validacao_normativa"):
        linhas.append("Validação normativa obrigatória: a peça NÃO pode ser aprovada para "
                      "publicação sem o responsável competente.")
    for a in laudo["achados"]:
        local = f" (linha {a['linha']})" if "linha" in a else ""
        marca = "" if a.get("natureza", "tecnica") == "tecnica" else f" <{a['natureza']}>"
        linhas.append(f"[{a['severidade'].upper()}]{marca} {a['regra']}{local}: {a['mensagem']}")
        if "trecho" in a:
            linhas.append(f"    trecho: {a['trecho']}")
        if a.get("sugestao"):
            linhas.append(f"    sugestão: {a['sugestao']}")
    if laudo.get("exigencias_aprovacao"):
        linhas.append("Antes de aprovar: " + ", ".join(laudo["exigencias_aprovacao"]) + ".")
    linhas.append("Limite: só o texto foi verificado; imagem, áudio e vídeo não foram analisados.")
    linhas.append("Passar na verificação NÃO é aprovação humana.")
    return "\n".join(linhas)
