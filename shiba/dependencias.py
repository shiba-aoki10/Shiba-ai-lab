"""Dependências de decisão de uma peça (Incremento 4B, decisão D2).

Uma aprovação vale para um TRIO de hashes; se qualquer um mudar, ela deixa
de contar. Este módulo recalcula o trio a partir dos bytes da peça e da
configuração ATUAL:

1. hash_conteudo: bytes exatos da peça e do arquivo de fatos da peça.
2. hash_config:
   - configuração efetiva do cliente na plataforma (todas as seções, já
     com a herança aplicada) e perfil completo da plataforma;
   - registro COMPLETO (todos os campos) de cada fato que INFLUENCIOU a
     verificação: todo fato ligado a qualquer vínculo de qualquer texto da
     peça (forte, ambíguo, inválido, unidade divergente, apoiado, não
     verificado), inclusive os que NÃO geraram nenhum alerta;
   - bytes do léxico editorial e das listas de validação em uso;
   - versão do motor e dos esquemas de laudo.
3. hash_laudo: a decisão do verificador (achados e exigências, sem data),
   recalculada com a data de hoje: um fato que vence muda o laudo.

Fatos que NÃO se ligaram a nenhum texto não entram no hash_config; se um
deles mudar de modo a afetar a peça (ex.: passar a ter o valor de um número
da legenda), o laudo recalculado muda, e o hash_laudo invalida a aprovação.
"""
from __future__ import annotations

import tomllib
from dataclasses import asdict, dataclass
from datetime import date

from . import __version__
from .afirmacoes import analisar
from .config import DIR_LISTAS_VALIDACAO, Cliente, ErroConfig, Fato, Plataforma
from .hashes import hash_conteudo, hash_laudo, hash_objeto, sha256
from .lexico import DIR_CONHECIMENTO
from .roteiro import interpretar_roteiro, unidades_de_texto
from .verificar import ESQUEMA, verificar
from .verificar_roteiro import ESQUEMA_ROTEIRO, verificar_roteiro

TIPOS = ("legenda", "roteiro")


@dataclass(frozen=True)
class Avaliacao:
    hash_conteudo: str
    hash_config: str
    hash_laudo: str
    laudo: dict
    fatos_influentes: tuple[str, ...]

    @property
    def hashes(self) -> dict:
        return {"hash_conteudo": self.hash_conteudo, "hash_config": self.hash_config,
                "hash_laudo": self.hash_laudo}


def texto_da_legenda(dados: bytes) -> str:
    try:
        texto = dados.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ErroConfig("arquivo da peça não está em UTF-8") from None
    return texto.replace("\r\n", "\n").replace("\r", "\n").strip()


def _roteiro(dados: bytes):
    try:
        return interpretar_roteiro(tomllib.loads(texto_da_legenda(dados)), "roteiro")
    except tomllib.TOMLDecodeError as e:
        raise ErroConfig(f"roteiro inválido: {e}") from None


def _lexicos(cliente: Cliente) -> dict:
    listas = {}
    for nome in cliente.secoes.get("revisao", {}).get("listas_validacao", []):
        listas[nome] = sha256((DIR_LISTAS_VALIDACAO / f"{nome}.toml").read_bytes())
    return {"editorial": sha256((DIR_CONHECIMENTO / "editorial.toml").read_bytes()),
            "listas_validacao": listas}


def fatos_influentes(textos: list[str], fatos: tuple[Fato, ...], cliente: Cliente,
                     hoje: date) -> list[Fato]:
    categorias = tuple(sorted(set(cliente.categorias_sensiveis)
                              | set(cliente.secoes.get("revisao", {})
                                    .get("categorias_validacao_normativa", []))))
    usados: dict[str, Fato] = {}
    for texto in textos:
        for v in analisar(texto, fatos, hoje, categorias):
            for f in v.fatos:
                usados[f.id] = f
    return [usados[i] for i in sorted(usados)]


def avaliar(tipo: str, peca: bytes, fatos_peca: bytes | None, cliente: Cliente,
            fatos: tuple[Fato, ...], plataforma: Plataforma, hoje: date | None = None) -> Avaliacao:
    """Verifica a peça agora e devolve o trio de hashes que amarra decisões."""
    if tipo not in TIPOS:
        raise ErroConfig(f"tipo de peça deve ser um de {TIPOS}")
    hoje = hoje or date.today()
    if tipo == "legenda":
        texto = texto_da_legenda(peca)
        laudo = verificar(texto, cliente, fatos, plataforma, hoje)
        textos = [texto]
    else:
        r = _roteiro(peca)
        if r.plataforma != plataforma.id:
            raise ErroConfig("a plataforma do roteiro não corresponde à da peça")
        laudo = verificar_roteiro(r, cliente, fatos, plataforma, hoje)
        textos = [u[1] for u in unidades_de_texto(r)]
    arquivos = [("peca", peca)] + ([("fatos_peca", fatos_peca)] if fatos_peca is not None else [])
    influentes = fatos_influentes(textos, fatos, cliente, hoje)
    config = {
        "tipo": tipo,
        "cliente": asdict(cliente),
        "plataforma": asdict(plataforma),
        "fatos_influentes": [asdict(f) for f in influentes],
        "lexicos": _lexicos(cliente),
        "versao": {"motor": __version__, "esquemas": [ESQUEMA, ESQUEMA_ROTEIRO]},
    }
    return Avaliacao(hash_conteudo(arquivos), hash_objeto(config), hash_laudo(laudo), laudo,
                     tuple(f.id for f in influentes))
