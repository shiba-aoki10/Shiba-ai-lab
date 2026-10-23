"""API do motor Shiba: ponto único de entrada, independente de interface.

A CLI (`shiba/cli.py`) é só uma casca sobre estas funções. Qualquer outra
interface futura (Claude, agentes locais, aplicativo, iPhone via serviço
local) deve chamar ESTAS funções, que:
- recebem caminhos e identificadores, nunca objetos de interface;
- devolvem dicionários serializáveis em JSON (laudos);
- levantam `ErroConfig` (ou `ErroIsolamento`) com mensagem segura, sem
  conteúdo de dados reais;
- não imprimem nada, não gravam logs e não publicam nada.

Aprovação não existe aqui: nenhuma função devolve "aprovado". Os laudos
dizem o que falta (`exigencias_aprovacao`) e sempre exigem uma pessoa.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .config import (
    DIR_CLIENTES,
    DIR_PLATAFORMAS,
    Cliente,
    ErroConfig,
    Fato,
    Plataforma,
    carregar_cliente,
    carregar_fatos,
    carregar_fatos_arquivo,
    carregar_plataforma,
    configuracao_efetiva,
    juntar_fatos,
    plataformas_disponiveis,
)
from .dados import garantir_fora_do_git, permissoes_abertas, preparar_dir_dados, resolver_dir_dados
from .calendario import caminho_do_arquivo, carregar_calendario, verificar_calendario
from .fontes import gerar_fontes_md
from .roteiro import carregar_roteiro
from .verificar import verificar
from .verificar_roteiro import verificar_roteiro

TAMANHO_MAXIMO_ARQUIVO = 64 * 1024  # bytes; legenda é texto curto
ROTULO_DADOS = "<dados>/clientes"   # aparece nas mensagens no lugar do caminho real


@dataclass(frozen=True)
class Origem:
    """De onde vêm os clientes: modelos fictícios versionados ou dados reais isolados."""
    dir_clientes: Path
    real: bool = False

    @property
    def opcoes(self) -> dict:
        return {"exigir_ficticio": False, "rotulo": ROTULO_DADOS} if self.real else {}

    @property
    def rotulo(self) -> str | None:
        return ROTULO_DADOS if self.real else None


@dataclass(frozen=True)
class Contexto:
    cliente: Cliente
    fatos: tuple[Fato, ...]
    plataforma: Plataforma


def origem(dados: str | None = None, dir_clientes: Path | None = None,
           ambiente: dict | None = None) -> Origem:
    """`dados=None`: só modelos fictícios. `dados=""`: usa SHIBA_DADOS. Senão, o diretório."""
    if dados is None:
        return Origem(Path(dir_clientes) if dir_clientes else DIR_CLIENTES)
    if dir_clientes is not None:
        raise ErroConfig("use --dados OU --dir-clientes, não os dois")
    raiz = preparar_dir_dados(resolver_dir_dados(dados, ambiente))
    return Origem(raiz / "clientes", real=True)


def proteger(o: Origem, caminho: Path | None, rotulo: str) -> None:
    """Com dados reais, tudo o que contém ou recebe conteúdo real fica fora do Git."""
    if o.real and caminho is not None:
        garantir_fora_do_git(Path(caminho), rotulo)


def contexto(cliente_id: str, plataforma_id: str, o: Origem, *,
             dir_plataformas: Path = DIR_PLATAFORMAS, fatos_peca: Path | None = None) -> Contexto:
    validas = plataformas_disponiveis(dir_plataformas)
    plataforma = carregar_plataforma(plataforma_id, dir_plataformas)
    cliente = carregar_cliente(cliente_id, o.dir_clientes, plataforma=plataforma_id,
                               plataformas_validas=validas, **o.opcoes)
    fatos = carregar_fatos(cliente_id, o.dir_clientes, rotulo=o.rotulo)
    if fatos_peca:
        fatos = juntar_fatos(fatos, carregar_fatos_arquivo(Path(fatos_peca)))
    return Contexto(cliente, fatos, plataforma)


def ler_texto(caminho: Path) -> str:
    """Lê o arquivo inteiro (UTF-8, até 64 KiB), normalizando quebras de linha."""
    caminho = Path(caminho)
    try:
        if caminho.stat().st_size > TAMANHO_MAXIMO_ARQUIVO:
            raise ErroConfig(f"arquivo maior que {TAMANHO_MAXIMO_ARQUIVO} bytes: {caminho}")
        bruto = caminho.read_bytes()
    except OSError as e:
        raise ErroConfig(f"não foi possível ler {caminho}: {e.strerror}") from None
    try:
        texto = bruto.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ErroConfig(f"arquivo não está em UTF-8: {caminho}") from None
    return texto.replace("\r\n", "\n").replace("\r", "\n").strip()


def verificar_legenda(caminho: Path, cliente_id: str, plataforma_id: str, o: Origem, *,
                      dir_plataformas: Path = DIR_PLATAFORMAS, fatos_peca: Path | None = None,
                      hoje: date | None = None, fontes: Path | None = None,
                      sobrescrever: bool = False) -> dict:
    """Laudo de uma legenda; grava o fontes.md se `fontes` for informado."""
    proteger(o, caminho, "o arquivo da legenda")
    proteger(o, fatos_peca, "o arquivo de fatos da peça")
    proteger(o, fontes, "o destino do fontes.md")
    ctx = contexto(cliente_id, plataforma_id, o, dir_plataformas=dir_plataformas,
                   fatos_peca=fatos_peca)
    texto = ler_texto(caminho)
    if fontes and Path(fontes).exists() and not sobrescrever:
        raise ErroConfig(f"{fontes} já existe; use --sobrescrever para substituir")
    laudo = verificar(texto, ctx.cliente, ctx.fatos, ctx.plataforma, hoje)
    if fontes:
        try:
            Path(fontes).write_text(gerar_fontes_md(laudo, texto, ctx.fatos, str(caminho)),
                                    encoding="utf-8")
        except OSError as e:
            raise ErroConfig(f"não foi possível gravar {fontes}: {e.strerror}") from None
    return laudo


def verificar_roteiro_arquivo(caminho: Path, cliente_id: str, o: Origem, *,
                              dir_plataformas: Path = DIR_PLATAFORMAS,
                              fatos_peca: Path | None = None, hoje: date | None = None) -> dict:
    """Laudo de um roteiro TOML. A plataforma vem do próprio roteiro."""
    proteger(o, caminho, "o arquivo do roteiro")
    proteger(o, fatos_peca, "o arquivo de fatos da peça")
    roteiro = carregar_roteiro(Path(caminho), "roteiro" if o.real else None)
    ctx = contexto(cliente_id, roteiro.plataforma, o, dir_plataformas=dir_plataformas,
                   fatos_peca=fatos_peca)
    return verificar_roteiro(roteiro, ctx.cliente, ctx.fatos, ctx.plataforma, hoje)


def verificar_calendario_arquivo(caminho: Path, cliente_id: str, o: Origem, *,
                                 dir_plataformas: Path = DIR_PLATAFORMAS,
                                 hoje: date | None = None) -> dict:
    """Laudo de um calendário TOML. Arquivos citados são relativos à pasta do calendário."""
    caminho = Path(caminho)
    proteger(o, caminho, "o arquivo do calendário")
    cal = carregar_calendario(caminho, "calendario" if o.real else None)
    base = caminho.parent
    for p in cal.pecas:
        proteger(o, caminho_do_arquivo(base, p.arquivo), "um arquivo citado no calendário")
    validas = plataformas_disponiveis(dir_plataformas)
    cliente = carregar_cliente(cliente_id, o.dir_clientes, plataformas_validas=validas, **o.opcoes)
    return verificar_calendario(cal, cliente, validas, hoje, base)


def configuracao(cliente_id: str, plataforma_id: str | None, o: Origem, *,
                 dir_plataformas: Path = DIR_PLATAFORMAS) -> dict:
    """Configuração efetiva após a herança, com a origem de cada valor."""
    validas = plataformas_disponiveis(dir_plataformas)
    if plataforma_id is not None and plataforma_id not in validas:
        raise ErroConfig(f"plataforma sem perfil: {plataforma_id!r}")
    # Carrega o cliente completo para aplicar TODAS as validações.
    carregar_cliente(cliente_id, o.dir_clientes, plataforma=plataforma_id,
                     plataformas_validas=validas, **o.opcoes)
    perfil, efetiva, origens = configuracao_efetiva(
        cliente_id, o.dir_clientes, plataforma=plataforma_id, rotulo=o.rotulo,
        plataformas_validas=validas)
    camadas = ["padrao"] + ([f"segmento:{perfil['segmento']}"] if "segmento" in perfil else []) \
        + ["cliente"]
    if plataforma_id:
        camadas = [c for nome in camadas for c in (nome, f"{nome}@{plataforma_id}")]
    return {"cliente": cliente_id, "plataforma": plataforma_id, "ordem_das_camadas": camadas,
            "configuracao": efetiva, "origens": origens}


def checar_dados(diretorio: str = "", ambiente: dict | None = None) -> dict:
    """Confere o diretório de dados SEM listar o conteúdo."""
    raiz = preparar_dir_dados(resolver_dir_dados(diretorio, ambiente))
    return {"seguro": True, "permissoes_abertas": permissoes_abertas(raiz)}
