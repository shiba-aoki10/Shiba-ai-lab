"""Laudo de roteiro audiovisual (Incremento 3B).

Estrutura e tempo são verificações técnicas; gancho, mensagem e CTA são
heurísticas e pedem revisão humana. Todo texto falado ou exibido passa pelas
mesmas regras de texto da legenda (fatos, afirmações sensíveis, palavras
proibidas, revisor editorial), com o achado apontando a cena ou o elemento.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date

from .config import Cliente, Fato, Plataforma
from .lexico import Lexico, carregar_lexico_editorial
from .regras import AVISO, BLOQUEANTE, INFO, NATUREZAS, NORMATIVA, REVISAO, Achado
from .roteiro import ELEMENTOS_DE_AUDIO, Roteiro, contem, palavras, unidades_de_texto
from .verificar import (
    LIMITES_DA_VERIFICACAO,
    _achado_para_dict,
    achados_de_texto,
    exigencias_aprovacao,
    ordenar,
    resumo_de,
)

ESQUEMA_ROTEIRO = "shiba.roteiro/0.1"
LIMITE_ROTEIRO = ("Este laudo verifica o ROTEIRO (texto e marcação de tempo). O vídeo, a "
                  "imagem e o áudio finais não foram analisados; a edição pode divergir do roteiro.")


def _a(regra, severidade, mensagem, local="", natureza="tecnica", sugestao="") -> Achado:
    return Achado(f"roteiro_{regra}", severidade, mensagem, natureza=natureza, local=local,
                  sugestao=sugestao)


def _fmt(s: float) -> str:
    return f"{s:g}s"


def _estrutura(r: Roteiro, cfg: dict) -> list[Achado]:
    achados = []
    if not r.cenas:
        return [_a("estrutura", BLOQUEANTE, "roteiro sem nenhuma [[cena]]")]
    cenas = sorted(r.cenas, key=lambda c: c.inicio)
    if [c.id for c in cenas] != [c.id for c in r.cenas]:
        achados.append(_a("estrutura", AVISO, "as cenas não estão em ordem de tempo no arquivo"))
    if cenas[0].inicio > 0:
        achados.append(_a("estrutura", AVISO, f"a primeira cena começa em {_fmt(cenas[0].inicio)}, não em 0s",
                          f"cena {cenas[0].id}"))
    for ant, prox in zip(cenas, cenas[1:]):
        if prox.inicio < ant.fim:
            achados.append(_a("estrutura", BLOQUEANTE,
                              f"cenas sequenciais {ant.id} e {prox.id} se sobrepõem "
                              f"({_fmt(prox.inicio)} < {_fmt(ant.fim)})", f"cena {prox.id}",
                              sugestao="Para algo que aparece AO MESMO TEMPO, use [[elemento]]."))
        elif prox.inicio > ant.fim:
            achados.append(_a("estrutura", AVISO,
                              f"intervalo sem cena entre {ant.id} e {prox.id} "
                              f"({_fmt(ant.fim)} a {_fmt(prox.inicio)})", f"cena {prox.id}"))
    total = r.duracao_total
    audio_el = [e for e in r.elementos if e.tipo in ELEMENTOS_DE_AUDIO]
    maximo_tela = cfg.get("texto_tela_max_palavras")
    for c in r.cenas:
        local = f"cena {c.id}"
        if not c.visual:
            achados.append(_a("cena_incompleta", BLOQUEANTE, "cena sem descrição do que se vê (visual)",
                              local, sugestao="Descreva a imagem, o motion graphics ou a tela."))
        coberta = any(e.inicio < c.fim and e.fim > c.inicio for e in audio_el)
        if not (c.fala or c.audio or coberta):
            achados.append(_a("cena_incompleta", AVISO, "cena sem áudio definido", local,
                              sugestao="Declare fala, trilha ou ambiente; se for silêncio "
                                       "intencional, use audio = [\"silencio\"]."))
        if maximo_tela and c.texto_tela and palavras(c.texto_tela) > maximo_tela:
            achados.append(_a("texto_tela", AVISO,
                              f"texto na tela com {palavras(c.texto_tela)} palavras "
                              f"(referência configurada: até {maximo_tela})", f"{local} · texto na tela",
                              REVISAO))
    for e in r.elementos:
        local = f"elemento {e.id} · {e.tipo}"
        if e.fim > total:
            achados.append(_a("estrutura", AVISO,
                              f"elemento termina em {_fmt(e.fim)}, depois da última cena ({_fmt(total)})", local))
        if e.tipo in ("texto_tela", "legenda", "cta_visual", "locucao") and not e.conteudo:
            achados.append(_a("cena_incompleta", AVISO, f"elemento {e.tipo} sem conteúdo", local))
        if maximo_tela and e.tipo == "texto_tela" and palavras(e.conteudo) > maximo_tela:
            achados.append(_a("texto_tela", AVISO,
                              f"texto na tela com {palavras(e.conteudo)} palavras "
                              f"(referência configurada: até {maximo_tela})", local, REVISAO))
    return achados


def _gancho(r: Roteiro, cfg: dict) -> list[Achado]:
    janela = cfg.get("janela_gancho_s")
    if janela is None:
        return [_a("gancho", INFO, "janela do gancho não configurada; abertura não conferida")]
    if r.gancho:
        return []
    textos = [u for u in unidades_de_texto(r) if u[2] < janela]
    if textos:
        return []
    return [_a("gancho", AVISO,
               f"nenhuma fala ou texto nos primeiros {_fmt(janela)} e nenhum gancho declarado",
               natureza=REVISAO,
               sugestao="Se o gancho for só visual, declare-o em `gancho`; senão, traga a "
                        "promessa ou a tensão para o início.")]


def _mensagem(r: Roteiro) -> list[Achado]:
    if not r.mensagem_principal:
        return [_a("mensagem", AVISO, "mensagem principal não declarada", natureza=REVISAO,
                   sugestao="Escreva em uma frase o que a pessoa deve entender ou lembrar.")]
    if not r.termos_mensagem:
        return [_a("mensagem", INFO, "presença da mensagem no roteiro não conferida "
                                     "(sem termos_mensagem)")]
    corpo = " \n ".join(u[1] for u in unidades_de_texto(r))
    faltando = [t for t in r.termos_mensagem if not contem(corpo, t)]
    if not faltando:
        return []
    return [_a("mensagem", AVISO,
               f"termo(s) da mensagem sem fala ou texto correspondente: {', '.join(faltando)}",
               natureza=REVISAO,
               sugestao="Se a mensagem estiver só na imagem, confirme na revisão do vídeo.")]


def _cta(r: Roteiro) -> list[Achado]:
    if r.cta is None:
        return [_a("cta", AVISO, "chamada para ação (CTA) não declarada", natureza=REVISAO,
                   sugestao="Declare [cta] com texto e forma, mesmo que seja visual.")]
    cta = r.cta
    cenas = {c.id: c for c in r.cenas}
    elementos = {e.id: e for e in r.elementos}
    if cta.cena and cta.cena not in cenas:
        return [_a("cta", BLOQUEANTE, f"[cta] aponta para cena inexistente: {cta.cena}")]
    if cta.elemento and cta.elemento not in elementos:
        return [_a("cta", BLOQUEANTE, f"[cta] aponta para elemento inexistente: {cta.elemento}")]
    if cta.cena:
        inicio, fim = cenas[cta.cena].inicio, cenas[cta.cena].fim
    elif cta.elemento:
        inicio, fim = elementos[cta.elemento].inicio, elementos[cta.elemento].fim
    else:
        achados = [(u[2], u[3]) for u in unidades_de_texto(r) if contem(u[1], cta.texto)]
        if not achados:
            if cta.forma == "visual":
                return [_a("cta", AVISO, "CTA visual sem cena ou elemento indicado; posição não conferida",
                           natureza=REVISAO)]
            return [_a("cta", AVISO, "o texto do CTA não aparece em nenhuma fala ou texto na tela",
                       natureza=REVISAO)]
        inicio, fim = max(achados)
    ultima = max(r.cenas, key=lambda c: c.fim) if r.cenas else None
    if ultima and fim <= ultima.inicio:
        return [_a("cta", AVISO, f"o CTA termina em {_fmt(fim)}, antes da última cena "
                                 f"({ultima.id}, a partir de {_fmt(ultima.inicio)})",
                   natureza=REVISAO, sugestao="Confirme se a chamada no meio do vídeo é intencional.")]
    return []


def _duracao(r: Roteiro, cfg: dict, plataforma: Plataforma) -> tuple[list[Achado], float | None]:
    achados, total = [], r.duracao_total
    tolerancia = cfg.get("tolerancia_duracao_pct")
    if r.duracao_alvo is not None and tolerancia is not None:
        desvio = abs(total - r.duracao_alvo) / r.duracao_alvo * 100
        if desvio > tolerancia:
            achados.append(_a("duracao", AVISO,
                              f"duração das cenas {_fmt(total)} × alvo {_fmt(r.duracao_alvo)} "
                              f"(desvio de {desvio:.0f}%, tolerância configurada {tolerancia:g}%)"))
    limite = dict(plataforma.limites).get("duracao_max_segundos")
    if limite is None or limite.valor is None:
        achados.append(_a("duracao", INFO, f"{plataforma.nome} sem duração máxima definida; não conferida"))
    elif total > limite.valor:
        achados.append(_a("duracao", BLOQUEANTE if limite.verificado else AVISO,
                          f"{_fmt(total)} acima do máximo de {plataforma.nome} ({limite.valor}s, "
                          f"status {limite.status})"))
    taxa = cfg.get("palavras_por_segundo")
    if taxa is None:
        achados.append(_a("duracao", INFO, "estimativa de tempo de fala desligada: nenhuma taxa de "
                                           "fala calibrada (roteiro.palavras_por_segundo)"))
        return achados, None
    falado = 0.0
    for c in r.cenas:
        if c.fala:
            estimado = palavras(c.fala) / taxa
            falado += estimado
            if estimado > c.duracao:
                achados.append(_a("duracao", AVISO,
                                  f"fala estimada em {estimado:.1f}s numa cena de {_fmt(c.duracao)}",
                                  f"cena {c.id} · fala", REVISAO,
                                  "Encurte a fala ou aumente a cena; a taxa é uma estimativa."))
    for e in r.elementos:
        if e.tipo == "locucao" and e.conteudo:
            estimado = palavras(e.conteudo) / taxa
            falado += estimado
            if estimado > e.fim - e.inicio:
                achados.append(_a("duracao", AVISO,
                                  f"locução estimada em {estimado:.1f}s num trecho de "
                                  f"{_fmt(e.fim - e.inicio)}", f"elemento {e.id} · locucao", REVISAO))
    return achados, round(falado, 1)


def verificar_roteiro(r: Roteiro, cliente: Cliente, fatos: tuple[Fato, ...], plataforma: Plataforma,
                      hoje: date | None = None, lexico: Lexico | None = None) -> dict:
    hoje = hoje or date.today()
    lexico = lexico or carregar_lexico_editorial()
    cfg = cliente.secoes.get("roteiro", {})
    duracao, falado = _duracao(r, cfg, plataforma)
    estruturais = ordenar(_estrutura(r, cfg) + _gancho(r, cfg) + _mensagem(r) + _cta(r) + duracao)
    dicts = [_achado_para_dict("", a) for a in estruturais]
    textuais = []
    for local, texto, _, _ in unidades_de_texto(r):
        for a in ordenar(achados_de_texto(texto, cliente, fatos, hoje, lexico)):
            a = replace(a, local=local)
            textuais.append(a)
            dicts.append(_achado_para_dict(texto, a))
    todos = estruturais + textuais
    dicts.sort(key=lambda d: ("bloqueante", "aviso", "info").index(d["severidade"]))
    resumo = resumo_de(todos)
    return {
        "esquema": ESQUEMA_ROTEIRO,
        "cliente": cliente.id,
        "plataforma": plataforma.id,
        "data_referencia": hoje.isoformat(),
        "resultado": "bloqueado" if resumo[BLOQUEANTE] else "passou",
        "requer_revisao_humana": resumo[AVISO] > 0,
        "requer_validacao_normativa": any(a.natureza == NORMATIVA for a in todos),
        "resumo": resumo,
        "por_natureza": {n: sum(a.natureza == n for a in todos) for n in NATUREZAS},
        "metricas": {
            "cenas": len(r.cenas),
            "elementos": len(r.elementos),
            "duracao_total_s": r.duracao_total,
            "duracao_alvo_s": r.duracao_alvo,
            "fala_estimada_s": falado,
        },
        "exigencias_aprovacao": exigencias_aprovacao(dicts),
        "limites_da_verificacao": [LIMITE_ROTEIRO, *LIMITES_DA_VERIFICACAO[1:]],
        "achados": dicts,
    }
