"""CLI do motor Shiba.

  python -m shiba verificar ARQUIVO --cliente ID --plataforma ID [opções]
  python -m shiba config mostrar --cliente ID [--plataforma ID] [--dados [DIR]]
  python -m shiba dados verificar [DIR]

Opções de `verificar`:
  --fatos-peca ARQ        fatos específicos desta peça (mesmo formato de fatos.toml)
  --data-referencia DATA  data usada para validade dos fatos (padrão: hoje)
  --fontes ARQ            grava o fontes.md (recusa sobrescrever sem --sobrescrever)
  --dados [DIR]           usa clientes REAIS de DIR (ou de $SHIBA_DADOS). Sem esta
                          opção, só os clientes fictícios de modelos/clientes/.

Com --dados, o diretório de dados, a legenda, os fatos da peça e o fontes.md
precisam estar FORA de qualquer repositório Git (ver shiba/dados.py).

Códigos de saída: 0 = passou / seguro, 1 = bloqueado, 2 = erro ou uso inseguro.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from .config import (
    DIR_CLIENTES,
    DIR_PLATAFORMAS,
    ErroConfig,
    carregar_cliente,
    carregar_fatos,
    carregar_fatos_arquivo,
    carregar_plataforma,
    configuracao_efetiva,
    juntar_fatos,
    plataformas_disponiveis,
)
from .dados import garantir_fora_do_git, permissoes_abertas, preparar_dir_dados, resolver_dir_dados
from .fontes import gerar_fontes_md
from .verificar import formatar_texto, verificar

TAMANHO_MAXIMO_ARQUIVO = 64 * 1024  # bytes; legenda é texto curto
# Rótulo usado nas mensagens no lugar do caminho real dos dados.
ROTULO_DADOS = "<dados>/clientes"


def ler_legenda(caminho: Path) -> str:
    """Lê o arquivo inteiro como a legenda (UTF-8), normalizando quebras de linha."""
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


def _data(valor: str) -> date:
    try:
        return date.fromisoformat(valor)
    except ValueError:
        raise argparse.ArgumentTypeError("use o formato AAAA-MM-DD") from None


def _opcoes_de_origem(p: argparse.ArgumentParser) -> None:
    p.add_argument("--cliente", required=True)
    p.add_argument("--dir-clientes", type=Path, default=None,
                   help="diretório de clientes fictícios (padrão: modelos/clientes)")
    p.add_argument("--dir-plataformas", type=Path, default=DIR_PLATAFORMAS)
    p.add_argument("--dados", nargs="?", const="", default=None, metavar="DIR",
                   help="usar dados reais de DIR ou de $SHIBA_DADOS")


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="shiba", description="Motor editorial Shiba (protótipo).")
    sub = p.add_subparsers(dest="comando", required=True)

    v = sub.add_parser("verificar", help="verifica uma legenda")
    v.add_argument("arquivo", type=Path)
    v.add_argument("--plataforma", required=True)
    v.add_argument("--formato", choices=("texto", "json"), default="texto")
    v.add_argument("--fatos-peca", type=Path)
    v.add_argument("--data-referencia", type=_data)
    v.add_argument("--fontes", type=Path)
    v.add_argument("--sobrescrever", action="store_true")
    _opcoes_de_origem(v)

    c = sub.add_parser("config", help="configuração efetiva de um cliente")
    c_sub = c.add_subparsers(dest="acao", required=True)
    m = c_sub.add_parser("mostrar", help="mostra a configuração após a herança e a origem de cada valor")
    m.add_argument("--plataforma")
    _opcoes_de_origem(m)

    d = sub.add_parser("dados", help="diretório de dados reais")
    d_sub = d.add_subparsers(dest="acao", required=True)
    dv = d_sub.add_parser("verificar", help="confere se o diretório de dados é seguro (não lista o conteúdo)")
    dv.add_argument("dir", nargs="?", default="")
    return p


def _origem_clientes(args) -> tuple[Path, dict]:
    """Diretório de clientes e opções de carga, conforme modelos fictícios ou dados reais."""
    if args.dados is None:
        return (args.dir_clientes or DIR_CLIENTES), {}
    if args.dir_clientes is not None:
        raise ErroConfig("use --dados OU --dir-clientes, não os dois")
    raiz = preparar_dir_dados(resolver_dir_dados(args.dados))
    return raiz / "clientes", {"exigir_ficticio": False, "rotulo": ROTULO_DADOS}


def _verificar(args) -> int:
    try:
        dir_clientes, opcoes = _origem_clientes(args)
        if args.dados is not None:
            # Tudo o que contém ou recebe conteúdo real fica fora do Git.
            garantir_fora_do_git(args.arquivo, "o arquivo da legenda")
            if args.fatos_peca:
                garantir_fora_do_git(args.fatos_peca, "o arquivo de fatos da peça")
            if args.fontes:
                garantir_fora_do_git(args.fontes, "o destino do fontes.md")
        validas = plataformas_disponiveis(args.dir_plataformas)
        plataforma = carregar_plataforma(args.plataforma, args.dir_plataformas)
        cliente = carregar_cliente(args.cliente, dir_clientes, plataforma=args.plataforma,
                                   plataformas_validas=validas, **opcoes)
        fatos = carregar_fatos(args.cliente, dir_clientes, rotulo=opcoes.get("rotulo"))
        if args.fatos_peca:
            fatos = juntar_fatos(fatos, carregar_fatos_arquivo(args.fatos_peca))
        texto = ler_legenda(args.arquivo)
        if args.fontes and args.fontes.exists() and not args.sobrescrever:
            raise ErroConfig(f"{args.fontes} já existe; use --sobrescrever para substituir")
    except ErroConfig as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2
    laudo = verificar(texto, cliente, fatos, plataforma, args.data_referencia)
    if args.fontes:
        try:
            args.fontes.write_text(gerar_fontes_md(laudo, texto, fatos, str(args.arquivo)),
                                   encoding="utf-8")
        except OSError as e:
            print(f"erro: não foi possível gravar {args.fontes}: {e.strerror}", file=sys.stderr)
            return 2
    if args.formato == "json":
        print(json.dumps(laudo, ensure_ascii=False, indent=2))
    else:
        print(formatar_texto(laudo, str(args.arquivo)))
    return 1 if laudo["resultado"] == "bloqueado" else 0


def _config_mostrar(args) -> int:
    try:
        dir_clientes, opcoes = _origem_clientes(args)
        validas = plataformas_disponiveis(args.dir_plataformas)
        if args.plataforma is not None and args.plataforma not in validas:
            raise ErroConfig(f"plataforma sem perfil: {args.plataforma!r}")
        # Carrega o cliente completo para aplicar TODAS as validações.
        carregar_cliente(args.cliente, dir_clientes, plataforma=args.plataforma,
                         plataformas_validas=validas, **opcoes)
        perfil, efetiva, origens = configuracao_efetiva(
            args.cliente, dir_clientes, plataforma=args.plataforma,
            rotulo=opcoes.get("rotulo"), plataformas_validas=validas)
    except ErroConfig as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2
    camadas = ["padrao"] + ([f"segmento:{perfil['segmento']}"] if "segmento" in perfil else []) \
        + ["cliente"]
    if args.plataforma:
        camadas = [c for nome in camadas for c in (nome, f"{nome}@{args.plataforma}")]
    print(json.dumps({"cliente": args.cliente, "plataforma": args.plataforma,
                      "ordem_das_camadas": camadas, "configuracao": efetiva,
                      "origens": origens}, ensure_ascii=False, indent=2))
    return 0


def _dados_verificar(args) -> int:
    try:
        raiz = preparar_dir_dados(resolver_dir_dados(args.dir))
    except ErroConfig as e:
        print(f"inseguro: {e}", file=sys.stderr)
        return 2
    print("seguro: o diretório de dados está fora de qualquer repositório Git e do código.")
    if permissoes_abertas(raiz):
        print("aviso: outros usuários do sistema podem acessar o diretório "
              "(sugestão: chmod 700).")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.comando == "verificar":
        return _verificar(args)
    if args.comando == "config":
        return _config_mostrar(args)
    return _dados_verificar(args)
