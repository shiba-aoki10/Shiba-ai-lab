"""CLI: python -m shiba verificar ARQUIVO --cliente ID --plataforma ID [opções]

Opções do Incremento 1:
  --fatos-peca ARQ        fatos específicos desta peça (mesmo formato de fatos.toml)
  --data-referencia DATA  data usada para validade dos fatos (padrão: hoje)
  --fontes ARQ            grava o fontes.md (recusa sobrescrever sem --sobrescrever)

Códigos de saída: 0 = passou, 1 = bloqueado, 2 = erro de uso ou configuração.
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
    juntar_fatos,
)
from .fontes import gerar_fontes_md
from .verificar import formatar_texto, verificar

TAMANHO_MAXIMO_ARQUIVO = 64 * 1024  # bytes; legenda é texto curto


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


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="shiba", description="Motor editorial Shiba (protótipo).")
    sub = p.add_subparsers(dest="comando", required=True)
    v = sub.add_parser("verificar", help="verifica uma legenda")
    v.add_argument("arquivo", type=Path)
    v.add_argument("--cliente", required=True)
    v.add_argument("--plataforma", required=True)
    v.add_argument("--formato", choices=("texto", "json"), default="texto")
    v.add_argument("--dir-clientes", type=Path, default=DIR_CLIENTES)
    v.add_argument("--dir-plataformas", type=Path, default=DIR_PLATAFORMAS)
    v.add_argument("--fatos-peca", type=Path)
    v.add_argument("--data-referencia", type=_data)
    v.add_argument("--fontes", type=Path)
    v.add_argument("--sobrescrever", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        cliente = carregar_cliente(args.cliente, args.dir_clientes)
        fatos = carregar_fatos(args.cliente, args.dir_clientes)
        if args.fatos_peca:
            fatos = juntar_fatos(fatos, carregar_fatos_arquivo(args.fatos_peca))
        plataforma = carregar_plataforma(args.plataforma, args.dir_plataformas)
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
