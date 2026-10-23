"""Carga e validação dos arquivos TOML de plataforma, cliente e fatos."""
from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from .heranca import META, ErroHeranca, resolver, validar_camada
from .secoes import SECOES, ErroSecao, validar_secoes
from .unidades import normalizar as normalizar_unidade

RAIZ = Path(__file__).resolve().parent.parent
DIR_PLATAFORMAS = RAIZ / "plataformas"
# Modelos versionados: padrão, segmentos genéricos e clientes FICTÍCIOS.
DIR_MODELOS = RAIZ / "modelos"
DIR_CLIENTES = DIR_MODELOS / "clientes"
PADRAO_PLATAFORMA = "_padrao.toml"
DIR_LISTAS_VALIDACAO = RAIZ / "conhecimento" / "pt-BR" / "validacao"

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
    valor: int | None  # None: nenhum valor conhecido (nada é inventado)
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
    texto_principal: str = "legenda"                  # legenda | descricao
    limites: tuple[tuple[str, Limite], ...] = ()      # todos os limites, por nome


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
    # Seções herdadas do Incremento 3 (editorial, roteiro, calendário, equipe,
    # revisão, normas), já validadas. Somente leitura por convenção.
    secoes: dict = field(default_factory=dict, compare=False)


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


def _ler_toml(caminho: Path, rotulo: str | None = None) -> dict:
    """Lê TOML. `rotulo` substitui o caminho nas mensagens (dados reais).

    A mensagem de erro do tomllib traz linha e coluna, nunca o conteúdo da linha.
    """
    nome = rotulo or caminho
    try:
        with caminho.open("rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        raise ErroConfig(f"arquivo não encontrado: {nome}") from None
    except tomllib.TOMLDecodeError as e:
        raise ErroConfig(f"TOML inválido em {nome}: {e}") from None
    except OSError as e:
        raise ErroConfig(f"não foi possível ler {nome}: {e.strerror}") from None


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


CAMPOS_LIMITE = {"valor", "status", "fonte", "consultado_em", "verificado_por",
                 "referencia_preliminar", "nota"}
CHAVES_PLATAFORMA = {"id", "nome", "descricao", "texto_principal", "limites"}


def _limite(dados: dict, origem: str) -> Limite:
    desconhecidas = set(dados) - CAMPOS_LIMITE
    if desconhecidas:
        raise ErroConfig(f"{origem}: chave desconhecida: {sorted(desconhecidas)[0]}")
    valor = None
    if "valor" in dados:
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
    if status == "verificado" and valor is None:
        raise ErroConfig(f"{origem}: limite 'verificado' exige valor")
    return Limite(valor, status, str(fonte), str(consultado_em))


def _mesclar_tabelas(base: dict, cima: dict) -> dict:
    """Mescla simples para perfis de plataforma: tabelas recursivas, resto substitui."""
    saida = dict(base)
    for chave, valor in cima.items():
        if isinstance(valor, dict) and isinstance(saida.get(chave), dict):
            saida[chave] = _mesclar_tabelas(saida[chave], valor)
        else:
            saida[chave] = valor
    return saida


def carregar_plataforma(plataforma_id: str, diretorio: Path = DIR_PLATAFORMAS) -> Plataforma:
    """Perfil da plataforma herdando de `_padrao.toml` do mesmo diretório, se existir."""
    validar_id(plataforma_id, "plataforma")
    caminho = Path(diretorio) / f"{plataforma_id}.toml"
    dados = _ler_toml(caminho)
    origem = caminho.name
    if _campo(dados, "id", str, origem) != plataforma_id:
        raise ErroConfig(f"{origem}: id não corresponde ao nome do arquivo")
    caminho_padrao = Path(diretorio) / PADRAO_PLATAFORMA
    padrao = _ler_toml(caminho_padrao) if caminho_padrao.is_file() else {}
    for camada, nome in ((padrao, PADRAO_PLATAFORMA), (dados, origem)):
        desconhecidas = set(camada) - CHAVES_PLATAFORMA
        if desconhecidas:
            raise ErroConfig(f"{nome}: chave desconhecida: {sorted(desconhecidas)[0]}")
    if "id" in padrao or "nome" in padrao:
        raise ErroConfig(f"{PADRAO_PLATAFORMA}: o padrão não pode definir id nem nome")
    dados = _mesclar_tabelas(padrao, dados)
    limites = _campo(dados, "limites", dict, origem)
    convertidos = []
    for nome_limite, bruto in limites.items():
        if not isinstance(bruto, dict):
            raise ErroConfig(f"{origem} [limites.{nome_limite}]: deve ser uma tabela")
        convertidos.append((nome_limite, _limite(bruto, f"{origem} [limites.{nome_limite}]")))
    por_nome = dict(convertidos)
    if "legenda_max_caracteres" not in por_nome:
        raise ErroConfig(f"{origem}: campo obrigatório ausente: legenda_max_caracteres")
    texto_principal = dados.get("texto_principal", "legenda")
    if texto_principal not in ("legenda", "descricao"):
        raise ErroConfig(f"{origem}: texto_principal deve ser 'legenda' ou 'descricao'")
    return Plataforma(
        id=plataforma_id,
        nome=_campo(dados, "nome", str, origem),
        legenda_max_caracteres=por_nome["legenda_max_caracteres"],
        texto_principal=texto_principal,
        limites=tuple(convertidos),
    )


def _camada(caminho: Path, origem: str, tipo: str, rotulo: str | None = None,
            opcional: bool = False) -> dict:
    if opcional and not caminho.is_file():
        return {}
    dados = _ler_toml(caminho, rotulo)
    try:
        validar_camada(dados, origem, tipo)
    except ErroHeranca as e:
        raise ErroConfig(str(e)) from None
    return dados


def plataformas_disponiveis(diretorio: Path = DIR_PLATAFORMAS) -> set[str]:
    return {p.stem for p in Path(diretorio).glob("*.toml") if not p.name.startswith("_")}


def configuracao_efetiva(cliente_id: str, diretorio: Path = DIR_CLIENTES, *,
                         plataforma: str | None = None, dir_modelos: Path = DIR_MODELOS,
                         rotulo: str | None = None,
                         plataformas_validas: set[str] | None = None) -> tuple[dict, dict, dict]:
    """Mescla padrão → segmento → cliente (cada um com seu ajuste @plataforma).

    Devolve (perfil do cliente como escrito, configuração efetiva, origens).
    `rotulo` troca o diretório nas mensagens (ex.: "$SHIBA_DADOS/clientes").
    O padrão e os segmentos vêm SEMPRE dos modelos versionados (`dir_modelos`):
    são genéricos e não contêm dados de clientes.
    """
    validar_id(cliente_id, "cliente")
    if plataforma is not None:
        validar_id(plataforma, "plataforma")
    origem = f"{rotulo}/{cliente_id}/perfil.toml" if rotulo else f"{cliente_id}/perfil.toml"
    perfil = _camada(Path(diretorio) / cliente_id / "perfil.toml", origem, "cliente",
                     origem if rotulo else None)
    camadas = [("padrao", _camada(Path(dir_modelos) / "padrao.toml", "padrao.toml", "padrao",
                                  opcional=True))]
    if "segmento" in perfil:
        segmento = validar_id(_campo(perfil, "segmento", str, origem), "segmento")
        camadas.append((f"segmento:{segmento}",
                        _camada(Path(dir_modelos) / "segmentos" / f"{segmento}.toml",
                                f"segmentos/{segmento}.toml", "segmento")))
    camadas.append(("cliente", perfil))
    if plataformas_validas is not None:
        # Um ajuste para plataforma inexistente ("tiktk") seria ignorado em silêncio.
        for nome, dados in camadas:
            for pid in dados.get("plataformas", {}):
                if pid not in plataformas_validas:
                    raise ErroConfig(f"{nome}: [plataformas.{pid}] não corresponde a nenhum "
                                     "perfil de plataforma")
    sem_meta = []
    for nome, dados in camadas:
        tipo = "segmento" if nome.startswith("segmento:") else nome
        sem_meta.append((nome, {k: v for k, v in dados.items() if k not in META[tipo]}))
    try:
        efetiva, origens = resolver(sem_meta, plataforma)
    except ErroHeranca as e:
        raise ErroConfig(str(e)) from None
    return perfil, efetiva, origens


def carregar_cliente(cliente_id: str, diretorio: Path = DIR_CLIENTES, *,
                     plataforma: str | None = None, dir_modelos: Path = DIR_MODELOS,
                     exigir_ficticio: bool = True, rotulo: str | None = None,
                     plataformas_validas: set[str] | None = None) -> Cliente:
    """Cliente com a configuração efetiva (herança aplicada).

    `exigir_ficticio=True` (modelos versionados) recusa qualquer perfil sem
    `ficticio = true`. Dados reais só entram com `exigir_ficticio=False`,
    a partir de um diretório validado por `dados.preparar_dir_dados`.
    """
    perfil, dados, _ = configuracao_efetiva(cliente_id, diretorio, plataforma=plataforma,
                                            dir_modelos=dir_modelos, rotulo=rotulo,
                                            plataformas_validas=plataformas_validas)
    origem = f"{rotulo}/{cliente_id}/perfil.toml" if rotulo else f"{cliente_id}/perfil.toml"
    if _campo(perfil, "id", str, origem) != cliente_id:
        raise ErroConfig(f"{origem}: id não corresponde ao diretório")
    ficticio = _campo(perfil, "ficticio", bool, origem)
    try:
        validar_secoes(dados, origem)
    except ErroSecao as e:
        raise ErroConfig(str(e)) from None
    revisao = dados.get("revisao", {})
    for cat in revisao.get("categorias_validacao_normativa", []):
        if cat not in CATEGORIAS:
            raise ErroConfig(f"{origem} [revisao]: categoria desconhecida: {cat}")
    disponiveis = {p.stem for p in DIR_LISTAS_VALIDACAO.glob("*.toml")}
    for lista in revisao.get("listas_validacao", []):
        if lista not in disponiveis:
            raise ErroConfig(f"{origem} [revisao]: lista de validação inexistente: {lista}")
    if exigir_ficticio and ficticio is not True:
        raise ErroConfig(f"{origem}: os modelos versionados aceitam apenas clientes com "
                         "ficticio = true")
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
        nome=_campo(perfil, "nome", str, origem),
        ficticio=ficticio,
        hashtags_minimo=minimo,
        hashtags_maximo=maximo,
        hashtags_proibidas=tuple(p.lstrip("#") for p in proibidas),
        palavras_proibidas=_lista_de_textos(palavras, "termos", f"{origem} [palavras_proibidas]"),
        categorias_sensiveis=tuple(sensiveis),
        secoes={nome: dados.get(nome, {}) for nome in SECOES},
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
    dados = _ler_toml(caminho, origem)
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


def carregar_fatos(cliente_id: str, diretorio: Path = DIR_CLIENTES, *,
                   rotulo: str | None = None) -> tuple[Fato, ...]:
    validar_id(cliente_id, "cliente")
    origem = f"{rotulo}/{cliente_id}/fatos.toml" if rotulo else f"{cliente_id}/fatos.toml"
    return carregar_fatos_arquivo(Path(diretorio) / cliente_id / "fatos.toml", origem)


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
