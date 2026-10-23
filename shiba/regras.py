"""Regras do verificador. Cada regra é uma função pura que devolve achados.

Incremento 0: hashtags, palavra_proibida, numero_sem_fato, limite_caracteres.
Incremento 1: numero_por_extenso, quantidade_vaga, vinculo_fato,
fato_nao_verificado, fato_sem_fonte, afirmacao_sensivel, promessa_resultado.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from .afirmacoes import (
    Quantidade,
    frases,
    marcadores,
    quantidades,
    quantidades_algarismos,
    quantidades_extenso,
    status_efetivo,
    vincular_marcador,
    vincular_quantidade,
)
from .config import Cliente, Fato, Plataforma
from .texto import URL, dentro, dobrar, intervalos, padrao_termo

BLOQUEANTE, AVISO, INFO = "bloqueante", "aviso", "info"
SEVERIDADES = (BLOQUEANTE, AVISO, INFO)

# Natureza do achado: quem resolve.
#   tecnica              conferência automática (estrutura, formato, fatos)
#   revisao_humana       julgamento editorial; heurística, nunca verdade absoluta
#   validacao_normativa  exige o responsável competente (técnico, jurídico);
#                        o motor NÃO interpreta normas nem conclui o que é permitido
TECNICA, REVISAO, NORMATIVA = "tecnica", "revisao_humana", "validacao_normativa"
NATUREZAS = (TECNICA, REVISAO, NORMATIVA)

# Hashtag: "#" não precedido de letra/dígito, seguido de letras, dígitos ou "_".
_HASHTAG = re.compile(r"(?<!\w)#(\w+)")


@dataclass(frozen=True)
class Achado:
    regra: str
    severidade: str
    mensagem: str
    inicio: int | None = None
    fim: int | None = None
    natureza: str = TECNICA
    justificativa: str = ""
    sugestao: str = ""
    local: str = ""   # onde, numa peça com várias partes (ex.: "cena c2 · fala")


def extrair_hashtags(texto: str) -> list[re.Match[str]]:
    urls = intervalos(URL, texto)
    return [m for m in _HASHTAG.finditer(texto) if not dentro(m.start(), urls)]


def regra_hashtags(texto: str, cliente: Cliente) -> list[Achado]:
    """Quantidade dentro da faixa do cliente, sem proibidas, sem repetidas."""
    achados = []
    tags = extrair_hashtags(texto)
    proibidas = {dobrar(p) for p in cliente.hashtags_proibidas}
    vistas: set[str] = set()
    for m in tags:
        nome = dobrar(m.group(1))
        if nome in proibidas:
            achados.append(Achado("hashtags", BLOQUEANTE,
                                  f"hashtag proibida pelo cliente: {m.group()}", m.start(), m.end()))
        if nome in vistas:
            achados.append(Achado("hashtags", AVISO,
                                  f"hashtag repetida: {m.group()}", m.start(), m.end()))
        vistas.add(nome)
    n = len(tags)
    if not cliente.hashtags_minimo <= n <= cliente.hashtags_maximo:
        achados.append(Achado(
            "hashtags", BLOQUEANTE,
            f"{n} hashtag(s); o cliente exige entre "
            f"{cliente.hashtags_minimo} e {cliente.hashtags_maximo}",
        ))
    return achados


def regra_palavras_proibidas(texto: str, cliente: Cliente) -> list[Achado]:
    """Termo proibido como palavra inteira, sem diferenciar maiúsculas e acentos.

    Um "*" no fim do termo busca por prefixo ("garantid*" pega as flexões).
    """
    dobrado = dobrar(texto)
    achados = []
    for termo in cliente.palavras_proibidas:
        for m in padrao_termo(termo).finditer(dobrado):
            achados.append(Achado(
                "palavra_proibida", BLOQUEANTE,
                f"termo proibido pelo cliente: {texto[m.start():m.end()]!r} (regra: {termo!r})",
                m.start(), m.end(),
            ))
    return achados


def _hoje(hoje: date | None) -> date:
    return hoje or date.today()


def _ids(fatos, hoje: date) -> str:
    return ", ".join(f"{f.id} ({status_efetivo(f, hoje)})" for f in fatos)


def _checar_quantidades(texto: str, qs: list[Quantidade], fatos: tuple[Fato, ...],
                        hoje: date, regra: str) -> list[Achado]:
    """Núcleo comum: quantidade sem fato válido de mesmo valor.

    Quantidades COM fato de mesmo valor seguem para `regra_vinculo_fatos`,
    que confere unidade, contexto, status e fonte.
    """
    spans = frases(texto)
    achados = []
    for q in qs:
        if q.chave is None:
            continue  # vaga: tratada em regra_numero_por_extenso
        v = vincular_quantidade(texto, q, fatos, hoje, spans)
        if v.situacao == "sem_fato":
            achados.append(Achado(regra, BLOQUEANTE,
                                  f"número {q.bruto!r} não corresponde a nenhum fato registrado",
                                  q.inicio, q.fim))
        elif v.situacao == "invalido":
            achados.append(Achado(regra, BLOQUEANTE,
                                  f"número {q.bruto!r} só corresponde a fato(s) sem validade: "
                                  + _ids(v.fatos, hoje), q.inicio, q.fim))
        elif v.situacao == "estrutural":
            achados.append(Achado(regra, AVISO,
                                  f"número {q.bruto!r} parece editorial (contagem de itens do "
                                  "próprio post); revisão humana: confirme a contagem e que não "
                                  "é uma afirmação sobre o cliente", q.inicio, q.fim,
                                  natureza=REVISAO))
    return achados


def regra_numero_sem_fato(texto: str, fatos: tuple[Fato, ...],
                          hoje: date | None = None) -> list[Achado]:
    """Todo número escrito com algarismos precisa corresponder a um fato válido."""
    return _checar_quantidades(texto, quantidades_algarismos(texto), fatos, _hoje(hoje),
                               "numero_sem_fato")


def regra_numero_por_extenso(texto: str, fatos: tuple[Fato, ...],
                             hoje: date | None = None) -> list[Achado]:
    """O mesmo para números por extenso; quantidades vagas pedem revisão humana."""
    qs = quantidades_extenso(texto)
    achados = _checar_quantidades(texto, qs, fatos, _hoje(hoje), "numero_por_extenso")
    for q in qs:
        if q.chave is None:
            achados.append(Achado("quantidade_vaga", AVISO,
                                  f"quantidade vaga ou relativa {q.bruto!r}: não dá para "
                                  "conferir com um fato; revisão humana", q.inicio, q.fim,
                                  natureza=REVISAO))
    return achados


def regra_vinculo_fatos(texto: str, fatos: tuple[Fato, ...], cliente: Cliente,
                        hoje: date | None = None) -> list[Achado]:
    """Para quantidades com fato de mesmo valor: unidade, contexto, status e fonte."""
    hoje = _hoje(hoje)
    spans = frases(texto)
    achados = []
    for q in quantidades(texto):
        if q.chave is None:
            continue
        v = vincular_quantidade(texto, q, fatos, hoje, spans)
        pos = (q.inicio, q.fim)
        if v.situacao == "unidade_divergente":
            achados.append(Achado("vinculo_fato", BLOQUEANTE,
                                  f"{q.bruto!r} usa unidade {q.unidade!r}, mas o(s) fato(s) de "
                                  f"mesmo valor usam outra: {_ids(v.fatos, hoje)}", *pos))
        elif v.situacao == "ambiguo":
            achados.append(Achado("vinculo_fato", AVISO,
                                  f"{q.bruto!r} tem o mesmo valor de {_ids(v.fatos, hoje)}, mas "
                                  "a frase não contém o contexto do fato; revisão humana: "
                                  "confirme se a afirmação é a mesma", *pos,
                                  natureza=REVISAO))
        elif v.situacao == "forte":
            fato = v.fatos[0]
            status = status_efetivo(fato, hoje)
            if fato.fonte is None:
                achados.append(Achado("fato_sem_fonte", BLOQUEANTE,
                                      f"{q.bruto!r} se apoia em {fato.id}, que não tem fonte "
                                      "registrada; sem fonte não há rastreabilidade", *pos))
            elif fato.categoria in cliente.categorias_sensiveis and status != "verificado":
                achados.append(Achado("afirmacao_sensivel", BLOQUEANTE,
                                      f"{q.bruto!r} se apoia em {fato.id} (categoria "
                                      f"{fato.categoria}, {status}); afirmação sensível exige "
                                      "fato verificado", *pos))
            elif status == "fornecido":
                achados.append(Achado("fato_nao_verificado", AVISO,
                                      f"{q.bruto!r} se apoia em {fato.id}, que foi fornecido mas "
                                      "não verificado; o aprovador precisa reconhecer", *pos,
                                      natureza=REVISAO))
    return achados


def regra_afirmacoes_sensiveis(texto: str, fatos: tuple[Fato, ...], cliente: Cliente,
                               hoje: date | None = None) -> list[Achado]:
    """Marcadores sensíveis (saúde, finanças, comparação, resultado) exigem fato verificado.

    A detecção é por lista de termos, uma heurística: marcador forte sem apoio
    bloqueia; marcador fraco sem apoio pede revisão humana.
    """
    hoje = _hoje(hoje)
    spans = frases(texto)
    achados = []
    for m in marcadores(texto, cliente.categorias_sensiveis):
        v = vincular_marcador(texto, m, fatos, hoje, spans)
        regra = "promessa_resultado" if m.categoria == "resultado" else "afirmacao_sensivel"
        termo = texto[m.inicio:m.fim]
        if v.situacao == "apoiado":
            continue
        if v.situacao in ("nao_verificado", "invalido"):
            achados.append(Achado(regra, BLOQUEANTE,
                                  f"{termo!r} ({m.categoria}) se liga a {_ids(v.fatos, hoje)}; "
                                  "afirmação sensível exige fato verificado e válido",
                                  m.inicio, m.fim))
        elif m.forca == "forte":
            achados.append(Achado(regra, BLOQUEANTE,
                                  f"{termo!r} ({m.categoria}) sem fato verificado da mesma "
                                  "categoria na frase", m.inicio, m.fim))
        else:
            achados.append(Achado(regra, AVISO,
                                  f"{termo!r} pode ser afirmação de {m.categoria}; nenhum fato "
                                  "verificado apoia a frase; revisão humana", m.inicio, m.fim,
                                  natureza=REVISAO))
    return achados


def regra_limite_caracteres(texto: str, plataforma: Plataforma) -> list[Achado]:
    """Legenda não vazia e dentro do limite. Limite não verificado só gera aviso."""
    limite = plataforma.legenda_max_caracteres
    if not texto.strip():
        return [Achado("limite_caracteres", BLOQUEANTE, "legenda vazia")]
    if limite.valor is None:
        # Nenhum valor conhecido: nada é inventado, e não há controle de tamanho.
        return [Achado("limite_caracteres", INFO,
                       f"{plataforma.nome} não tem limite de caracteres definido "
                       f"(status '{limite.status}'); o tamanho não foi verificado")]
    achados = []
    if not limite.verificado:
        achados.append(Achado(
            "limite_caracteres", INFO,
            f"limite de {limite.valor} caracteres para {plataforma.nome} está "
            f"com status '{limite.status}': excesso gera só aviso",
        ))
    n = len(texto)
    if n > limite.valor:
        achados.append(Achado(
            "limite_caracteres", BLOQUEANTE if limite.verificado else AVISO,
            f"{n} caracteres; limite de {plataforma.nome}: {limite.valor} "
            f"(excede em {n - limite.valor})",
            limite.valor, n,
        ))
    return achados
