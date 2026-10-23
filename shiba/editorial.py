"""Revisor editorial pt-BR: alertas explicáveis, configuráveis, nunca bloqueantes.

Todo alerta tem natureza "revisao_humana", justificativa e sugestão. São
heurísticas de estilo: podem errar para os dois lados, e a pessoa que revisa
decide. Nada aqui detecta "texto feito por IA"; as listas apontam padrões
frequentes que costumam enfraquecer o texto.

Cada regra só roda se o seu limiar estiver configurado em [editorial] (pela
herança) e se não estiver em `regras_desativadas`. URLs, e-mails, hashtags e
@menções são ignorados.
"""
from __future__ import annotations

import re

from .afirmacoes import frases
from .lexico import Lexico
from .numeros import zonas_ignoradas
from .regras import AVISO, INFO, REVISAO, Achado
from .texto import dobrar, padrao_termo

_PARAGRAFO = re.compile(r"\n[ \t]*\n\s*")
_PALAVRA = re.compile(r"[^\W\d_]+")
_PONTUACAO = re.compile(r"[!?]{2,}|\.{4,}")
_NAO_ADVERBIOS = {"mente", "semente", "demente", "clemente", "veemente", "implemente",
                  "complemente", "suplemente"}
_FINAIS_ADJETIVO = ("a", "e", "l", "z", "r", "m", "s")

JUSTIFICATIVAS = {
    "frase_longa": ("Frases longas exigem mais atenção, sobretudo em tela pequena ou narradas.",
                    "Divida em duas frases ou corte o que não for essencial."),
    "paragrafo_longo": ("Blocos longos são pulados em leitura rápida.",
                        "Quebre em parágrafos curtos, um por ideia."),
    "repeticao_palavra": ("A mesma palavra repetida no parágrafo cansa e pode indicar redundância.",
                          "Troque por sinônimo, pronome ou reestruture; repetição intencional é válida."),
    "repeticao_inicio": ("Frases seguidas que começam igual soam mecânicas.",
                         "Varie o início ou junte as frases; anáfora intencional é válida."),
    "adverbios_mente": ("Vários advérbios em -mente na mesma frase deixam o texto pesado.",
                        "Mantenha o mais importante ou troque por verbo mais preciso."),
    "pontuacao": ("Pontuação repetida (!!, ?!, ....) costuma soar exagerada.",
                  "Use um sinal só; a ênfase pode vir da palavra."),
    "caixa_alta": ("Trechos longos em caixa alta são lidos como grito e dificultam a leitura.",
                   "Use caixa alta só em uma ou duas palavras de destaque."),
    "termos_cliente": ("Termo marcado pelo cliente para revisão.",
                       "Confira se o uso está de acordo com a orientação do cliente."),
}


def _mascarar(texto: str) -> str:
    """Troca URL, e-mail, hashtag e @menção por espaços (mesmo comprimento)."""
    chars = list(texto)
    for ini, fim in zonas_ignoradas(texto):
        for i in range(ini, fim):
            if chars[i] != "\n":
                chars[i] = " "
    return "".join(chars)


def _paragrafos(texto: str) -> list[tuple[int, int]]:
    spans, ini = [], 0
    for m in _PARAGRAFO.finditer(texto):
        if texto[ini:m.start()].strip():
            spans.append((ini, m.start()))
        ini = m.end()
    if texto[ini:].strip():
        spans.append((ini, len(texto)))
    return spans


def _paragrafo_de(spans, pos):
    return next((s for s in spans if s[0] <= pos < s[1]), (pos, pos))


def _alerta(regra: str, severidade: str, mensagem: str, ini=None, fim=None,
            justificativa: str = "", sugestao: str = "") -> Achado:
    j, s = JUSTIFICATIVAS.get(regra, ("", ""))
    return Achado(f"editorial_{regra}", severidade, mensagem, ini, fim, natureza=REVISAO,
                  justificativa=justificativa or j, sugestao=sugestao or s)


def _fim_da_palavra(dob: str, fim: int) -> int:
    while fim < len(dob) and (dob[fim].isalnum() or dob[fim] == "_"):
        fim += 1
    return fim


def _expressoes(texto, mascarado, dob, pars, config, lexico, ativa) -> list[Achado]:
    ignorados = {dobrar(t) for t in config.get("termos_ignorados", [])}
    ocorrencias = []
    for e in lexico.expressoes:
        if ativa(e.categoria) and dobrar(e.termo) not in ignorados:
            for m in padrao_termo(e.termo).finditer(dob):
                ocorrencias.append((e, m.start(), _fim_da_palavra(dob, m.end())))
    limiar = config.get("ia_por_paragrafo_aviso")
    por_paragrafo: dict = {}
    for e, ini, _ in ocorrencias:
        if e.categoria == "ia":
            chave = _paragrafo_de(pars, ini)
            por_paragrafo[chave] = por_paragrafo.get(chave, 0) + 1
    achados = []
    for e, ini, fim in ocorrencias:
        severidade, extra = e.severidade, ""
        if e.categoria == "ia":
            n = por_paragrafo[_paragrafo_de(pars, ini)]
            if limiar and n >= limiar:
                severidade = AVISO
                extra = f" ({n} expressões desse tipo no mesmo parágrafo)"
        achados.append(_alerta(e.categoria, severidade,
                               f"{texto[ini:fim]!r}: {e.justificativa}{extra}", ini, fim,
                               e.justificativa, e.sugestao))
    if ativa("termos_cliente"):
        for termo in config.get("termos_extras", []):
            for m in padrao_termo(termo).finditer(dob):
                fim = _fim_da_palavra(dob, m.end())
                achados.append(_alerta("termos_cliente", INFO,
                                       f"{texto[m.start():fim]!r}: termo marcado pelo cliente para revisão",
                                       m.start(), fim))
    return achados


def _palavras(texto: str, ini: int, fim: int):
    return [m for m in _PALAVRA.finditer(texto, ini, fim)]


def revisar(texto: str, config: dict, lexico: Lexico) -> list[Achado]:
    """Alertas editoriais do texto. `config` = seção [editorial] efetiva do cliente."""
    desligadas = set(config.get("regras_desativadas", []))

    def ativa(nome: str) -> bool:
        return nome not in desligadas

    mascarado = _mascarar(texto)
    dob = dobrar(mascarado)
    pars = _paragrafos(mascarado)
    sentencas = [(a, b) for a, b in frases(mascarado) if mascarado[a:b].strip()]
    achados = _expressoes(texto, mascarado, dob, pars, config, lexico, ativa)

    maximo = config.get("frase_max_palavras")
    if maximo and ativa("frase_longa"):
        for a, b in sentencas:
            n = len(_palavras(mascarado, a, b))
            if n > maximo:
                achados.append(_alerta("frase_longa", AVISO,
                                       f"frase com {n} palavras (referência configurada: até {maximo})",
                                       a, b))

    maximo = config.get("paragrafo_max_frases")
    if maximo and ativa("paragrafo_longo"):
        for a, b in pars:
            n = sum(1 for s in sentencas if a <= s[0] < b)
            if n > maximo:
                achados.append(_alerta("paragrafo_longo", INFO,
                                       f"parágrafo com {n} frases (referência configurada: até {maximo})",
                                       a, min(b, a + 60)))

    minimo_rep = config.get("repeticao_min")
    if minimo_rep and ativa("repeticao_palavra"):
        min_letras = config.get("palavra_min_letras", 1)
        for a, b in pars:
            contagem: dict[str, list] = {}
            for m in _palavras(dob, a, b):
                w = m.group()
                if len(w) >= min_letras and w not in lexico.stopwords:
                    contagem.setdefault(w, []).append(m)
            for w, ms in contagem.items():
                if len(ms) >= minimo_rep:
                    achados.append(_alerta("repeticao_palavra", AVISO,
                                           f"{texto[ms[0].start():ms[0].end()]!r} aparece "
                                           f"{len(ms)} vezes no mesmo parágrafo",
                                           ms[0].start(), ms[0].end()))

    if minimo_rep and ativa("repeticao_inicio"):
        primeiras = []
        for a, b in sentencas:
            ps = _palavras(dob, a, b)
            primeiras.append((ps[0].group(), ps[0]) if ps else ("", None))
        seguidas = 1
        for i in range(1, len(primeiras)):
            seguidas = seguidas + 1 if primeiras[i][0] and primeiras[i][0] == primeiras[i - 1][0] else 1
            if seguidas == minimo_rep:
                m = primeiras[i][1]
                achados.append(_alerta("repeticao_inicio", AVISO,
                                       f"{seguidas} frases seguidas começam com "
                                       f"{texto[m.start():m.end()]!r}", m.start(), m.end()))

    maximo = config.get("mente_max_por_frase")
    if maximo and ativa("adverbios_mente"):
        for a, b in sentencas:
            advs = [m for m in _palavras(dob, a, b)
                    if m.group().endswith("mente") and m.group() not in _NAO_ADVERBIOS
                    and len(m.group()) - 5 >= 4 and m.group()[:-5].endswith(_FINAIS_ADJETIVO)]
            if len(advs) > maximo:
                achados.append(_alerta("adverbios_mente", INFO,
                                       f"{len(advs)} advérbios em -mente na mesma frase "
                                       f"(referência configurada: até {maximo})",
                                       advs[0].start(), advs[-1].end()))

    if ativa("pontuacao"):
        for m in _PONTUACAO.finditer(mascarado):
            achados.append(_alerta("pontuacao", INFO, f"pontuação repetida {m.group()!r}",
                                   m.start(), m.end()))

    minimo_caixa = config.get("caixa_alta_min_palavras")
    if minimo_caixa and ativa("caixa_alta"):
        sequencia: list = []
        for m in list(_PALAVRA.finditer(mascarado)) + [None]:
            alta = m is not None and len(m.group()) >= 2 and m.group().isupper()
            junto = alta and (not sequencia or "\n" not in mascarado[sequencia[-1].end():m.start()])
            if alta and junto:
                sequencia.append(m)
                continue
            if len(sequencia) >= minimo_caixa:
                achados.append(_alerta("caixa_alta", INFO,
                                       f"{len(sequencia)} palavras seguidas em caixa alta",
                                       sequencia[0].start(), sequencia[-1].end()))
            sequencia = [m] if alta else []
    return achados
