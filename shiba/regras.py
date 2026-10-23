"""As quatro regras do Incremento 0. Cada regra é uma função pura que devolve achados."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .config import Cliente, Fato, Plataforma
from .numeros import extrair_numeros
from .texto import URL, dentro, dobrar, intervalos

BLOQUEANTE, AVISO, INFO = "bloqueante", "aviso", "info"
SEVERIDADES = (BLOQUEANTE, AVISO, INFO)

# Hashtag: "#" não precedido de letra/dígito, seguido de letras, dígitos ou "_".
_HASHTAG = re.compile(r"(?<!\w)#(\w+)")
STATUS_FATO_VALIDO = ("fornecido", "verificado")


@dataclass(frozen=True)
class Achado:
    regra: str
    severidade: str
    mensagem: str
    inicio: int | None = None
    fim: int | None = None


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


def _padrao_termo(termo: str) -> re.Pattern[str]:
    partes = [re.escape(p) for p in dobrar(termo).split()]
    return re.compile(r"(?<!\w)" + r"\s+".join(partes) + r"(?!\w)")


def regra_palavras_proibidas(texto: str, cliente: Cliente) -> list[Achado]:
    """Termo proibido como palavra inteira, sem diferenciar maiúsculas e acentos."""
    dobrado = dobrar(texto)
    achados = []
    for termo in cliente.palavras_proibidas:
        for m in _padrao_termo(termo).finditer(dobrado):
            achados.append(Achado(
                "palavra_proibida", BLOQUEANTE,
                f"termo proibido pelo cliente: {texto[m.start():m.end()]!r} (regra: {termo!r})",
                m.start(), m.end(),
            ))
    return achados


def regra_numero_sem_fato(texto: str, fatos: tuple[Fato, ...]) -> list[Achado]:
    """Todo número escrito com algarismos precisa corresponder a um fato válido."""
    validos: dict[tuple[str, str], list[str]] = {}
    invalidos: dict[tuple[str, str], list[str]] = {}
    for fato in fatos:
        destino = validos if fato.status in STATUS_FATO_VALIDO else invalidos
        for valor in fato.valores:
            for numero in extrair_numeros(valor):
                destino.setdefault(numero.chave, []).append(f"{fato.id} ({fato.status})")
    achados = []
    for numero in extrair_numeros(texto):
        if numero.chave in validos:
            continue
        if numero.chave in invalidos:
            msg = (f"número {numero.bruto!r} só corresponde a fato(s) sem validade: "
                   + ", ".join(invalidos[numero.chave]))
        else:
            msg = f"número {numero.bruto!r} não corresponde a nenhum fato registrado"
        achados.append(Achado("numero_sem_fato", BLOQUEANTE, msg, numero.inicio, numero.fim))
    return achados


def regra_limite_caracteres(texto: str, plataforma: Plataforma) -> list[Achado]:
    """Legenda não vazia e dentro do limite. Limite não verificado só gera aviso."""
    limite = plataforma.legenda_max_caracteres
    if not texto.strip():
        return [Achado("limite_caracteres", BLOQUEANTE, "legenda vazia")]
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
