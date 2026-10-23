"""Carga e validação dos arquivos TOML de plataforma, cliente e fatos."""
from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from .unidades import normalizar as normalizar_unidade

RAIZ = Path(__file__).resolve().parent.parent
DIR_PLATAFORMAS = RAIZ / "plataformas"
DIR_CLIENTES = RAIZ / "modelos" / "clientes"

# Impede "../" e caminhos absolutos no id usado para montar caminhos.
_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")

STATUS_LIMITE = ("a_verificar", "verificado", "expirado")
STATUS_FATO = ("fornecido", "verificado", "expirado", "contestado")
CATEGORIAS = ("institucional", "produto", "preco", "saude", "financeiro", "comparativo",
              "resultado")
CATEGORIAS_SENSIVEIS_PADRAO = ("saude", "financeiro", "comparativo", "resultado")
CAMPOS_FONTE = ("tipo", "referencia", "informado_por", "informado_em")
CAMPOS_VERIFICACAO = ("fonte", "metodo", "verificado_por", "verificado_em")


class ErroConfig(Exception):
    """Arquivo de configuração ausente, malformado ou inválido."""


@dataclass(frozen=True)
class Limite:
    valor: int
    status: str
    fonte: str
    consultado_em: str

    @property
    def verificado(self) -> bool:
        return self.status == "verificado"


@dataclass(frozen=True)
class Plataforma:
    id: str
    nome: str
    legenda_max_caracteres: Limite


@dataclass(frozen=True)
class Cliente:
    id: str
    nome: str
    ficticio: bool
    hashtags_minimo: int
    hashtags_maximo: int
    hashtags_proibidas: tuple[str, ...]
    palavras_proibidas: tuple[str, ...]
    categorias_sensiveis: tuple[str, ...] = CATEGORIAS_SENSIVEIS_PADRAO


@dataclass(frozen=True)
class Fato:
    id: str
    texto: str
    valores: tuple[str, ...]
    status: str
    categoria: str = "institucional"
    contexto: tuple[str, ...] = ()      # termos que identificam o assunto do fato
    unidade: str = ""                   # unidade canônica (ver unidades.py), se houver
    valido_ate: date | None = None
    fonte: tuple[tuple[str, str], ...] | None = None        # pares (campo, valor)
    verificacao: tuple[tuple[str, str], ...] | None = None  # pares (campo, valor)
    origem: str = ""                    # arquivo de onde o fato veio


def validar_id(valor: str, tipo: str) -> str:
    if not isinstance(valor, str) or not _ID.fullmatch(valor):
        raise ErroConfig(f"{tipo} inválido: {valor!r} (use a-z, 0-9 e hífen)")
    return valor


def _ler_toml(caminho: Path) -> dict:
    try:
        with caminho.open("rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        raise ErroConfig(f"arquivo não encontrado: {caminho}") from None
    except tomllib.TOMLDecodeError as e:
        raise ErroConfig(f"TOML inválido em {caminho}: {e}") from None


def _campo(dados: dict, nome: str, tipo: type, origem: str):
    if nome not in dados:
        raise ErroConfig(f"{origem}: campo obrigatório ausente: {nome}")
    valor = dados[nome]
    # bool é subclasse de int; não aceitar true/false onde se espera número.
    if not isinstance(valor, tipo) or (tipo is int and isinstance(valor, bool)):
        raise ErroConfig(f"{origem}: campo {nome} deve ser {tipo.__name__}")
    return valor


def _lista_de_textos(dados: dict, nome: str, origem: str) -> tuple[str, ...]:
    valores = dados.get(nome, [])
    if not isinstance(valores, list) or not all(
        isinstance(v, str) and v.strip() for v in valores
    ):
        raise ErroConfig(f"{origem}: {nome} deve ser uma lista de textos não vazios")
    return tuple(v.strip() for v in valores)


def _limite(dados: dict, origem: str) -> Limite:
    valor = _campo(dados, "valor", int, origem)
    if valor <= 0:
        raise ErroConfig(f"{origem}: valor deve ser positivo")
    status = _campo(dados, "status", str, origem)
    if status not in STATUS_LIMITE:
        raise ErroConfig(f"{origem}: status deve ser um de {STATUS_LIMITE}")
    fonte = dados.get("fonte", "")
    consultado_em = dados.get("consultado_em", "")
    if status == "verificado" and not (str(fonte).strip() and str(consultado_em).strip()):
        raise ErroConfig(f"{origem}: limite 'verificado' exige fonte e consultado_em")
    return Limite(valor, status, str(fonte), str(consultado_em))


def carregar_plataforma(plataforma_id: str, diretorio: Path = DIR_PLATAFORMAS) -> Plataforma:
    validar_id(plataforma_id, "plataforma")
    caminho = Path(diretorio) / f"{plataforma_id}.toml"
    dados = _ler_toml(caminho)
    origem = caminho.name
    if _campo(dados, "id", str, origem) != plataforma_id:
        raise ErroConfig(f"{origem}: id não corresponde ao nome do arquivo")
    limites = _campo(dados, "limites", dict, origem)
    legenda = _campo(limites, "legenda_max_caracteres", dict, origem)
    return Plataforma(
        id=plataforma_id,
        nome=_campo(dados, "nome", str, origem),
        legenda_max_caracteres=_limite(legenda, f"{origem} [limites.legenda_max_caracteres]"),
    )


def carregar_cliente(cliente_id: str, diretorio: Path = DIR_CLIENTES) -> Cliente:
    validar_id(cliente_id, "cliente")
    caminho = Path(diretorio) / cliente_id / "perfil.toml"
    dados = _ler_toml(caminho)
    origem = f"{cliente_id}/perfil.toml"
    if _campo(dados, "id", str, origem) != cliente_id:
        raise ErroConfig(f"{origem}: id não corresponde ao diretório")
    # Incremento 0: só clientes fictícios (nenhum dado real).
    if _campo(dados, "ficticio", bool, origem) is not True:
        raise ErroConfig(f"{origem}: o protótipo aceita apenas clientes com ficticio = true")
    hashtags = _campo(dados, "hashtags", dict, origem)
    minimo = _campo(hashtags, "minimo", int, f"{origem} [hashtags]")
    maximo = _campo(hashtags, "maximo", int, f"{origem} [hashtags]")
    if not 0 <= minimo <= maximo:
        raise ErroConfig(f"{origem} [hashtags]: exige 0 <= minimo <= maximo")
    proibidas = _lista_de_textos(hashtags, "proibidas", f"{origem} [hashtags]")
    palavras = _campo(dados, "palavras_proibidas", dict, origem)
    secao_fatos = dados.get("fatos", {})
    if not isinstance(secao_fatos, dict):
        raise ErroConfig(f"{origem}: [fatos] deve ser uma tabela")
    sensiveis = _lista_de_textos(secao_fatos, "categorias_sensiveis", f"{origem} [fatos]") \
        if "categorias_sensiveis" in secao_fatos else CATEGORIAS_SENSIVEIS_PADRAO
    for cat in sensiveis:
        if cat not in CATEGORIAS:
            raise ErroConfig(f"{origem} [fatos]: categoria desconhecida {cat!r}")
    return Cliente(
        id=cliente_id,
        nome=_campo(dados, "nome", str, origem),
        ficticio=True,
        hashtags_minimo=minimo,
        hashtags_maximo=maximo,
        hashtags_proibidas=tuple(p.lstrip("#") for p in proibidas),
        palavras_proibidas=_lista_de_textos(palavras, "termos", f"{origem} [palavras_proibidas]"),
        categorias_sensiveis=tuple(sensiveis),
    )


def _data(valor, origem: str, nome: str) -> date:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        try:
            return date.fromisoformat(valor)
        except ValueError:
            pass
    raise ErroConfig(f"{origem}: {nome} deve ser uma data AAAA-MM-DD")


def _registro(bruto, campos: tuple[str, ...], origem: str) -> tuple[tuple[str, str], ...]:
    """Tabela de fonte ou verificação: todos os campos obrigatórios e não vazios."""
    if not isinstance(bruto, dict):
        raise ErroConfig(f"{origem}: deve ser uma tabela")
    pares = []
    for campo in campos:
        valor = bruto.get(campo)
        if isinstance(valor, (date, datetime)):
            valor = valor.isoformat()
        if not isinstance(valor, str) or not valor.strip():
            raise ErroConfig(f"{origem}: campo obrigatório ausente ou vazio: {campo}")
        pares.append((campo, valor.strip()))
    return tuple(pares)


def _fato(bruto: dict, local: str, origem: str) -> Fato:
    fato_id = _campo(bruto, "id", str, local)
    status = _campo(bruto, "status", str, local)
    if status not in STATUS_FATO:
        raise ErroConfig(f"{local}: status deve ser um de {STATUS_FATO}")
    categoria = bruto.get("categoria", "institucional")
    if categoria not in CATEGORIAS:
        raise ErroConfig(f"{local}: categoria deve ser uma de {CATEGORIAS}")
    unidade = bruto.get("unidade", "")
    if not isinstance(unidade, str):
        raise ErroConfig(f"{local}: unidade deve ser texto")
    # Fonte é opcional na carga para não quebrar registros antigos, mas um fato
    # sem fonte nunca libera uma afirmação (regra fato_sem_fonte).
    fonte = _registro(bruto["fonte"], CAMPOS_FONTE, f"{local} [fonte]") if "fonte" in bruto else None
    verificacao = None
    if "verificacao" in bruto:
        if status == "fornecido":
            raise ErroConfig(f"{local}: fato 'fornecido' não pode ter [verificacao]")
        verificacao = _registro(bruto["verificacao"], CAMPOS_VERIFICACAO, f"{local} [verificacao]")
    if status == "verificado" and (fonte is None or verificacao is None):
        raise ErroConfig(f"{local}: fato 'verificado' exige [fato.fonte] e [fato.verificacao]")
    return Fato(
        id=fato_id,
        texto=_campo(bruto, "texto", str, local),
        valores=_lista_de_textos(bruto, "valores", local),
        status=status,
        categoria=categoria,
        contexto=_lista_de_textos(bruto, "contexto", local),
        unidade=normalizar_unidade(unidade) if unidade.strip() else "",
        valido_ate=_data(bruto["valido_ate"], local, "valido_ate") if "valido_ate" in bruto else None,
        fonte=fonte,
        verificacao=verificacao,
        origem=origem,
    )


def carregar_fatos_arquivo(caminho: Path, origem: str | None = None) -> tuple[Fato, ...]:
    """Carrega [[fato]] de um arquivo TOML (registro do cliente ou fatos da peça)."""
    caminho = Path(caminho)
    origem = origem or caminho.name
    dados = _ler_toml(caminho)
    brutos = dados.get("fato", [])
    if not isinstance(brutos, list):
        raise ErroConfig(f"{origem}: use [[fato]] para cada fato")
    fatos, vistos = [], set()
    for i, bruto in enumerate(brutos, 1):
        local = f"{origem} fato #{i}"
        if not isinstance(bruto, dict):
            raise ErroConfig(f"{local}: formato inválido")
        fato = _fato(bruto, local, origem)
        if fato.id in vistos:
            raise ErroConfig(f"{local}: id duplicado {fato.id}")
        vistos.add(fato.id)
        fatos.append(fato)
    return tuple(fatos)


def carregar_fatos(cliente_id: str, diretorio: Path = DIR_CLIENTES) -> tuple[Fato, ...]:
    validar_id(cliente_id, "cliente")
    return carregar_fatos_arquivo(Path(diretorio) / cliente_id / "fatos.toml",
                                  f"{cliente_id}/fatos.toml")


def juntar_fatos(*grupos: tuple[Fato, ...]) -> tuple[Fato, ...]:
    """Une registros (cliente + peça). Id repetido entre arquivos é erro."""
    vistos: dict[str, str] = {}
    saida = []
    for grupo in grupos:
        for fato in grupo:
            if fato.id in vistos:
                raise ErroConfig(f"id de fato repetido: {fato.id} ({vistos[fato.id]} e {fato.origem})")
            vistos[fato.id] = fato.origem
            saida.append(fato)
    return tuple(saida)
