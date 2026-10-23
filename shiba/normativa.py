"""Sinalização de temas que exigem validação normativa (Incremento 3D).

O que este módulo FAZ:
- marca, com natureza "validacao_normativa", trechos de categorias que o
  cliente declarou como sujeitas a validação ([revisao]
  categorias_validacao_normativa) e termos das listas de validação
  ([revisao] listas_validacao, em conhecimento/pt-BR/validacao/);
- faz isso MESMO quando a afirmação está apoiada em fato verificado: fato
  verificado resolve a veracidade técnica, não a conformidade normativa.

O que este módulo NÃO FAZ (e nunca deve fazer):
- concluir se uma peça pode ou não ser publicada do ponto de vista normativo;
- citar ou interpretar leis, resoluções ou códigos de ética;
- dispensar a validação porque nenhum termo foi encontrado.

Todo achado é AVISO identificado. A peça não pode ser aprovada para
publicação sem o responsável competente (Incremento 4 exigirá esse papel).
"""
from __future__ import annotations

import tomllib
from datetime import date
from functools import lru_cache

from .afirmacoes import frases, marcadores, quantidades, vincular_quantidade
from .config import DIR_LISTAS_VALIDACAO, Cliente, ErroConfig, Fato
from .regras import AVISO, NORMATIVA, Achado
from .texto import dobrar, padrao_termo

AVISO_PADRAO = ("exige validação pelo responsável competente antes de qualquer aprovação; "
                "o motor não avalia se é permitido")


@lru_cache(maxsize=16)
def carregar_lista(nome: str) -> tuple[tuple[str, str], ...]:
    """(termo, motivo) de conhecimento/pt-BR/validacao/<nome>.toml, validado."""
    caminho = DIR_LISTAS_VALIDACAO / f"{nome}.toml"
    try:
        with caminho.open("rb") as f:
            dados = tomllib.load(f)
    except FileNotFoundError:
        raise ErroConfig(f"lista de validação inexistente: {nome}") from None
    except tomllib.TOMLDecodeError as e:
        raise ErroConfig(f"lista de validação inválida ({nome}): {e}") from None
    temas = []
    for i, t in enumerate(dados.get("tema", []), 1):
        if not isinstance(t, dict) or not all(isinstance(t.get(c), str) and t[c].strip()
                                              for c in ("termo", "motivo")):
            raise ErroConfig(f"lista {nome} tema #{i}: termo e motivo são obrigatórios")
        temas.append((t["termo"].strip(), t["motivo"].strip()))
    return tuple(temas)


def regra_validacao_normativa(texto: str, fatos: tuple[Fato, ...], cliente: Cliente,
                              hoje: date | None = None) -> list[Achado]:
    revisao = cliente.secoes.get("revisao", {})
    categorias = tuple(revisao.get("categorias_validacao_normativa", []))
    listas = revisao.get("listas_validacao", [])
    if not categorias and not listas:
        return []
    hoje = hoje or date.today()
    achados: dict[tuple[int, int], Achado] = {}

    def marcar(ini: int, fim: int, mensagem: str) -> None:
        achados.setdefault((ini, fim), Achado("validacao_normativa", AVISO, mensagem, ini, fim,
                                              natureza=NORMATIVA,
                                              sugestao="Encaminhe ao responsável competente do "
                                                       "cliente e registre a validação."))

    for m in marcadores(texto, categorias):
        marcar(m.inicio, m.fim, f"{texto[m.inicio:m.fim]!r}: afirmação de {m.categoria}; {AVISO_PADRAO}")
    spans = frases(texto)
    for q in quantidades(texto):
        if q.chave is None:
            continue
        v = vincular_quantidade(texto, q, fatos, hoje, spans)
        sensiveis = [f for f in v.fatos if f.categoria in categorias]
        if v.situacao in ("forte", "ambiguo") and sensiveis:
            marcar(q.inicio, q.fim, f"{q.bruto!r} se apoia em fato de {sensiveis[0].categoria} "
                                    f"({sensiveis[0].id}); fato verificado não substitui a "
                                    f"validação normativa; {AVISO_PADRAO}")
    dob = dobrar(texto)
    for nome in listas:
        for termo, motivo in carregar_lista(nome):
            for m in padrao_termo(termo).finditer(dob):
                fim = m.end()
                while fim < len(dob) and (dob[fim].isalnum() or dob[fim] == "_"):
                    fim += 1
                marcar(m.start(), fim, f"{texto[m.start():fim]!r}: {motivo} Tema que {AVISO_PADRAO}")
    return sorted(achados.values(), key=lambda a: a.inicio)


def normas_registradas(cliente: Cliente) -> list[dict]:
    """Referências cadastradas pelo cliente, para quem valida. Sem interpretação."""
    return [dict(r) for r in cliente.secoes.get("normas", {}).get("referencias", [])]
