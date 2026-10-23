"""Afirmações de uma legenda e seus vínculos com fatos registrados.

Uma afirmação é uma quantidade (com algarismos ou por extenso) ou um marcador
sensível ("garantido", "cura", "líder") dentro de uma frase. O vínculo com um
fato é decidido por valor, unidade e contexto (termos do fato na mesma frase).

IMPORTANTE: tudo aqui é heurística determinística. Um vínculo "forte" significa
só que valor, unidade e contexto coincidem; NÃO prova que a afirmação é
verdadeira nem que se refere àquele fato. Por isso o laudo sempre exige revisão
humana, e casos ambíguos viram aviso explícito.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .config import CATEGORIAS_SENSIVEIS_PADRAO, Fato
from .extenso import ESCALAS, extrair_extenso
from .numeros import extrair_numeros, zonas_ignoradas
from .texto import dobrar, padrao_termo
from .unidades import SINONIMOS

STATUS_VALIDOS = ("fornecido", "verificado")

# Substantivos que indicam número editorial: "3 dicas", "5 erros que...".
ESTRUTURAIS_DEPOIS = {
    "dica", "dicas", "erro", "erros", "passo", "passos", "motivo", "motivos",
    "forma", "formas", "maneira", "maneiras", "segredo", "segredos", "coisa", "coisas",
    "ideia", "ideias", "truque", "truques", "pergunta", "perguntas", "licao", "licoes",
    "mito", "mitos", "sinal", "sinais", "habito", "habitos", "regra", "regras",
    "opcao", "opcoes", "exemplo", "exemplos", "etapa", "etapas", "topico", "topicos",
    "item", "itens", "parte", "partes", "curiosidade", "curiosidades", "razao", "razoes",
    "receita", "receitas", "slide", "slides",
}
# Palavras que, ANTES do número, indicam numeração editorial: "parte 2", "top 5".
ESTRUTURAIS_ANTES = {
    "parte", "passo", "etapa", "episodio", "ep", "top", "slide", "item", "capitulo",
    "temporada", "dica", "licao", "aula", "modulo",
}

# (categoria, força, termos). Força "forte" bloqueia sem fato verificado;
# "fraco" só pede revisão humana, porque a palavra tem outros usos comuns.
MARCADORES = (
    ("resultado", "forte", ("garant*", "comprovad*", "sem risco")),
    ("resultado", "fraco", ("aumenta*", "triplica*", "multiplica*", "transforma*", "resultado*")),
    ("saude", "forte", ("cura", "curam", "curar", "emagrec*")),
    ("saude", "fraco", ("previn*", "imunidade", "saudave*", "tratamento*", "trata",
                        "alivia*", "combate*", "detox", "desintox*", "anvisa")),
    ("financeiro", "fraco", ("lucro*", "rendimento*", "retorno financeiro", "investiment*",
                             "juros", "renda extra", "ganhe dinheiro")),
    ("comparativo", "forte", ("lider*", "numero 1", "melhor do brasil", "melhor do mundo",
                              "melhor da cidade", "melhor do bairro", "maior do brasil",
                              "maior da cidade", "maior do bairro")),
    ("comparativo", "fraco", ("melhor", "melhores", "maior", "maiores", "mais barat*",
                              "unico", "unica", "que a concorrencia", "que os concorrentes")),
)
_PADROES_MARCADORES = tuple(
    (cat, forca, termo, padrao_termo(termo)) for cat, forca, termos in MARCADORES for termo in termos
)

_FRONTEIRA = re.compile(r"(?<=[.!?…])\s+|\n+")
_PROXIMA = re.compile(r"[ \t ]*(\w+)")
_ANTERIOR = re.compile(r"(\w+)[ \t ]*$")
_ESCALA_APOS = re.compile(r"[ \t ]+(mil|milhao|milhoes|bilhao|bilhoes)(?!\w)")
_REAIS_ANTES = re.compile(r"R\$[ \t ]*$")


@dataclass(frozen=True)
class Quantidade:
    bruto: str
    inicio: int
    fim: int
    chave: tuple[str, str] | None  # None: quantidade vaga ("o dobro", "dezenas")
    origem: str                     # algarismo | extenso
    unidade: str | None
    estrutural: bool


@dataclass(frozen=True)
class Marcador:
    categoria: str
    forca: str
    termo: str
    inicio: int
    fim: int


@dataclass(frozen=True)
class Vinculo:
    """Resultado do vínculo de UMA quantidade ou marcador.

    situacao:
      forte              valor + unidade + contexto coincidem com fato válido
      ambiguo            valor coincide, mas o contexto não confirma (revisão humana)
      unidade_divergente valor coincide, unidade diferente
      invalido           só coincide com fato expirado ou contestado
      sem_fato           nada coincide
      estrutural         número editorial sem fato ("3 dicas")
      vago               quantidade vaga ou relativa ("o dobro")
      apoiado            marcador sensível com fato verificado da mesma categoria
      nao_verificado     marcador sensível com fato da categoria, mas não verificado
    """
    elemento: str
    tipo: str          # algarismo | extenso | marcador
    inicio: int
    fim: int
    frase: tuple[int, int]
    situacao: str
    fatos: tuple[Fato, ...] = ()
    categoria: str = ""
    forca: str = ""


# ---- frases e fatos -------------------------------------------------------

def frases(texto: str) -> list[tuple[int, int]]:
    """Divide o texto em frases (fim em . ! ? … seguidos de espaço, ou quebra de linha)."""
    spans, ini = [], 0
    for m in _FRONTEIRA.finditer(texto):
        if m.start() > ini:
            spans.append((ini, m.start()))
        ini = m.end()
    if ini < len(texto):
        spans.append((ini, len(texto)))
    return spans


def frase_de(spans: list[tuple[int, int]], pos: int) -> tuple[int, int]:
    for ini, fim in spans:
        if ini <= pos < fim:
            return (ini, fim)
    return (pos, pos)


def status_efetivo(fato: Fato, hoje: date) -> str:
    """Status considerando a validade: fato vencido conta como expirado."""
    if fato.status in STATUS_VALIDOS and fato.valido_ate and fato.valido_ate < hoje:
        return "expirado"
    return fato.status


def contexto_casa(fato: Fato, frase_dobrada: str) -> bool:
    return any(padrao_termo(t).search(frase_dobrada) for t in fato.contexto)


def chaves_do_fato(fato: Fato) -> set[tuple[str, str]]:
    chaves = set()
    for valor in fato.valores:
        for q in quantidades(valor):
            if q.chave is not None:
                chaves.add(q.chave)
    return chaves


# ---- quantidades ----------------------------------------------------------

def _unidade(texto: str, dob: str, inicio: int, fim: int) -> str | None:
    if _REAIS_ANTES.search(texto, max(0, inicio - 4), inicio):
        return "brl"
    m = _PROXIMA.match(dob, fim)
    return SINONIMOS.get(m.group(1)) if m else None


def _estrutural(dob: str, inicio: int, fim: int) -> bool:
    m = _PROXIMA.match(dob, fim)
    if m and m.group(1) in ESTRUTURAIS_DEPOIS:
        return True
    m = _ANTERIOR.search(dob, max(0, inicio - 40), inicio)
    return bool(m and m.group(1) in ESTRUTURAIS_ANTES)


def _canonico(valor: Decimal) -> str:
    return format(valor.normalize(), "f")


def quantidades_algarismos(texto: str) -> list[Quantidade]:
    """Números com algarismos; "2 mil" e "1,5 milhão" viram um valor só."""
    dob = dobrar(texto)
    saida = []
    for n in extrair_numeros(texto):
        fim, chave = n.fim, n.chave
        m = _ESCALA_APOS.match(dob, fim)
        if m and chave[0] == "valor":
            chave = ("valor", _canonico(Decimal(chave[1]) * ESCALAS[m.group(1)]))
            fim = m.end()
        saida.append(Quantidade(texto[n.inicio:fim], n.inicio, fim, chave, "algarismo",
                                _unidade(texto, dob, n.inicio, fim),
                                _estrutural(dob, n.inicio, fim)))
    return saida


def quantidades_extenso(texto: str) -> list[Quantidade]:
    """Números por extenso e quantidades vagas, fora das zonas ignoradas."""
    dob = dobrar(texto)
    ocupadas = [(q.inicio, q.fim) for q in quantidades_algarismos(texto)]
    saida = []
    for e in extrair_extenso(texto, zonas_ignoradas(texto) + ocupadas):
        if e.valor is None:
            chave = None
        else:
            chave = ("percentual" if e.percentual else "valor", _canonico(Decimal(e.valor)))
        saida.append(Quantidade(texto[e.inicio:e.fim], e.inicio, e.fim, chave, "extenso",
                                _unidade(texto, dob, e.inicio, e.fim),
                                _estrutural(dob, e.inicio, e.fim)))
    return saida


def quantidades(texto: str) -> list[Quantidade]:
    return sorted(quantidades_algarismos(texto) + quantidades_extenso(texto),
                  key=lambda q: q.inicio)


# ---- vínculos -------------------------------------------------------------

def vincular_quantidade(texto: str, q: Quantidade, fatos: tuple[Fato, ...], hoje: date,
                        spans: list[tuple[int, int]] | None = None) -> Vinculo:
    frase = frase_de(spans if spans is not None else frases(texto), q.inicio)

    def vinculo(situacao: str, candidatos=()) -> Vinculo:
        return Vinculo(q.bruto, q.origem, q.inicio, q.fim, frase, situacao, tuple(candidatos))

    if q.chave is None:
        return vinculo("vago")
    mesmo_valor = [f for f in fatos if q.chave in chaves_do_fato(f)]
    if not mesmo_valor:
        return vinculo("estrutural" if q.estrutural else "sem_fato")
    validos = [f for f in mesmo_valor if status_efetivo(f, hoje) in STATUS_VALIDOS]
    if not validos:
        return vinculo("invalido", mesmo_valor)
    compativeis = [f for f in validos
                   if not (q.unidade and f.unidade and q.unidade != f.unidade)]
    if not compativeis:
        return vinculo("unidade_divergente", validos)
    frase_dob = dobrar(texto[frase[0]:frase[1]])
    fortes = [f for f in compativeis if f.contexto and contexto_casa(f, frase_dob)]
    if fortes:
        # Fato verificado primeiro: é o apoio mais forte disponível.
        fortes.sort(key=lambda f: status_efetivo(f, hoje) != "verificado")
        return vinculo("forte", fortes)
    return vinculo("ambiguo", compativeis)


def marcadores(texto: str, categorias: tuple[str, ...] = CATEGORIAS_SENSIVEIS_PADRAO
               ) -> list[Marcador]:
    """Marcadores sensíveis; um marcador fraco dentro de um forte é descartado."""
    dob = dobrar(texto)
    ignorar = zonas_ignoradas(texto)
    achados = []
    for cat, forca, termo, padrao in _PADROES_MARCADORES:
        if cat not in categorias:
            continue
        for m in padrao.finditer(dob):
            if not any(ini <= m.start() < fim for ini, fim in ignorar):
                fim = m.end()
                while fim < len(dob) and (dob[fim].isalnum() or dob[fim] == "_"):
                    fim += 1  # termo por prefixo: mostra a palavra inteira
                achados.append(Marcador(cat, forca, termo, m.start(), fim))
    fortes = [a for a in achados if a.forca == "forte"]
    return sorted(
        (a for a in achados
         if a.forca == "forte" or not any(f.inicio <= a.inicio < f.fim for f in fortes)),
        key=lambda a: a.inicio,
    )


def vincular_marcador(texto: str, m: Marcador, fatos: tuple[Fato, ...], hoje: date,
                      spans: list[tuple[int, int]] | None = None) -> Vinculo:
    """Um marcador sensível só é apoiado por fato VERIFICADO que:
    - é da mesma categoria do marcador;
    - afirma a mesma coisa: o texto do fato contém o termo do marcador
      (um fato "80% avaliaram as aulas como boas" não apoia "resultado garantido");
    - está ligado à frase pelo contexto ou por uma quantidade com vínculo forte.
    """
    spans = spans if spans is not None else frases(texto)
    frase = frase_de(spans, m.inicio)
    frase_dob = dobrar(texto[frase[0]:frase[1]])
    padrao = padrao_termo(m.termo)
    da_categoria = [f for f in fatos
                    if f.categoria == m.categoria and padrao.search(dobrar(f.texto))]
    ligados = {f.id: f for f in da_categoria if f.contexto and contexto_casa(f, frase_dob)}
    for q in quantidades(texto):
        if frase[0] <= q.inicio < frase[1]:
            v = vincular_quantidade(texto, q, tuple(da_categoria), hoje, spans)
            if v.situacao == "forte":
                ligados.update((f.id, f) for f in v.fatos)
    candidatos = list(ligados.values())
    elemento = texto[m.inicio:m.fim]

    def vinculo(situacao: str, fs=()) -> Vinculo:
        return Vinculo(elemento, "marcador", m.inicio, m.fim, frase, situacao, tuple(fs),
                       m.categoria, m.forca)

    verificados = [f for f in candidatos if status_efetivo(f, hoje) == "verificado"]
    if verificados:
        return vinculo("apoiado", verificados)
    if any(status_efetivo(f, hoje) == "fornecido" for f in candidatos):
        return vinculo("nao_verificado", candidatos)
    if candidatos:
        return vinculo("invalido", candidatos)
    return vinculo("sem_fato")


def analisar(texto: str, fatos: tuple[Fato, ...], hoje: date,
             categorias: tuple[str, ...] = CATEGORIAS_SENSIVEIS_PADRAO) -> list[Vinculo]:
    """Todos os vínculos da legenda, em ordem de posição."""
    spans = frases(texto)
    vinculos = [vincular_quantidade(texto, q, fatos, hoje, spans) for q in quantidades(texto)]
    vinculos += [vincular_marcador(texto, m, fatos, hoje, spans)
                 for m in marcadores(texto, categorias)]
    return sorted(vinculos, key=lambda v: v.inicio)
