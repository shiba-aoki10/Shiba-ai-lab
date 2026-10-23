"""CLI do motor Shiba: casca fina sobre `shiba/api.py`.

  python -m shiba verificar ARQUIVO --cliente ID --plataforma ID [opções]
  python -m shiba roteiro verificar ROTEIRO.toml --cliente ID [opções]
  python -m shiba config mostrar --cliente ID [--plataforma ID] [--dados [DIR]]
  python -m shiba dados verificar [DIR]

Opções comuns:
  --fatos-peca ARQ        fatos específicos desta peça (mesmo formato de fatos.toml)
  --data-referencia DATA  data usada para validade dos fatos (padrão: hoje)
  --dados [DIR]           usa clientes REAIS de DIR (ou de $SHIBA_DADOS). Sem esta
                          opção, só os clientes fictícios de modelos/clientes/.
  --formato texto|json
Só em `verificar`: --fontes ARQ [--sobrescrever].

Com --dados, o diretório de dados e todo arquivo de entrada ou saída
precisam estar FORA de qualquer repositório Git (ver shiba/dados.py).

Códigos de saída: 0 = passou / seguro, 1 = bloqueado, 2 = erro ou uso inseguro.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from . import api
from .api import ler_texto as ler_legenda  # noqa: F401  (compatibilidade)
from .config import DIR_PLATAFORMAS, ErroConfig
from .verificar import formatar_texto


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


def _opcoes_de_peca(p: argparse.ArgumentParser) -> None:
    p.add_argument("--formato", choices=("texto", "json"), default="texto")
    p.add_argument("--fatos-peca", type=Path)
    p.add_argument("--data-referencia", type=_data)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="shiba", description="Motor editorial Shiba (protótipo).")
    sub = p.add_subparsers(dest="comando", required=True)

    v = sub.add_parser("verificar", help="verifica uma legenda")
    v.add_argument("arquivo", type=Path)
    v.add_argument("--plataforma", required=True)
    v.add_argument("--fontes", type=Path)
    v.add_argument("--sobrescrever", action="store_true")
    _opcoes_de_peca(v)
    _opcoes_de_origem(v)

    r = sub.add_parser("roteiro", help="roteiro audiovisual")
    r_sub = r.add_subparsers(dest="acao", required=True)
    rv = r_sub.add_parser("verificar", help="verifica um roteiro TOML")
    rv.add_argument("arquivo", type=Path)
    _opcoes_de_peca(rv)
    _opcoes_de_origem(rv)

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


def formatar_generico(laudo: dict, arquivo: str = "") -> str:
    """Texto legível para laudos de roteiro e calendário."""
    r = laudo["resumo"]
    linhas = [f"{laudo['esquema']} · cliente {laudo['cliente']}"
              + (f" · {laudo['plataforma']}" if laudo.get("plataforma") else "")
              + (f" · {arquivo}" if arquivo else ""),
              f"Resultado: {laudo['resultado'].upper()} "
              f"({r['bloqueante']} bloqueante(s), {r['aviso']} aviso(s), {r['info']} info)",
              "Métricas: " + ", ".join(f"{k}={v}" for k, v in laudo.get("metricas", {}).items())]
    if laudo.get("requer_validacao_normativa"):
        linhas.append("Validação normativa obrigatória: NÃO pode ser aprovado para publicação "
                      "sem o responsável competente.")
    for a in laudo["achados"]:
        marca = "" if a.get("natureza", "tecnica") == "tecnica" else f" <{a['natureza']}>"
        onde = f" [{a['local']}]" if a.get("local") else ""
        linhas.append(f"[{a['severidade'].upper()}]{marca} {a['regra']}{onde}: {a['mensagem']}")
        if "trecho" in a:
            linhas.append(f"    trecho: {a['trecho']}")
        if a.get("sugestao"):
            linhas.append(f"    sugestão: {a['sugestao']}")
    linhas.append("Antes de aprovar: " + ", ".join(laudo["exigencias_aprovacao"]) + ".")
    linhas += [f"Limite: {t}" for t in laudo["limites_da_verificacao"][:1]]
    linhas.append("Passar na verificação NÃO é aprovação humana.")
    return "\n".join(linhas)


def _imprimir(laudo: dict, args, formatador) -> int:
    if args.formato == "json":
        print(json.dumps(laudo, ensure_ascii=False, indent=2))
    else:
        print(formatador(laudo, str(args.arquivo)))
    return 1 if laudo["resultado"] == "bloqueado" else 0


def _executar(args) -> int:
    if args.comando == "dados":
        resultado = api.checar_dados(args.dir)
        print("seguro: o diretório de dados está fora de qualquer repositório Git e do código.")
        if resultado["permissoes_abertas"]:
            print("aviso: outros usuários do sistema podem acessar o diretório "
                  "(sugestão: chmod 700).")
        return 0
    o = api.origem(args.dados, args.dir_clientes)
    if args.comando == "config":
        print(json.dumps(api.configuracao(args.cliente, args.plataforma, o,
                                          dir_plataformas=args.dir_plataformas),
                         ensure_ascii=False, indent=2))
        return 0
    if args.comando == "roteiro":
        laudo = api.verificar_roteiro_arquivo(args.arquivo, args.cliente, o,
                                              dir_plataformas=args.dir_plataformas,
                                              fatos_peca=args.fatos_peca, hoje=args.data_referencia)
        return _imprimir(laudo, args, formatar_generico)
    laudo = api.verificar_legenda(args.arquivo, args.cliente, args.plataforma, o,
                                  dir_plataformas=args.dir_plataformas, fatos_peca=args.fatos_peca,
                                  hoje=args.data_referencia, fontes=args.fontes,
                                  sobrescrever=args.sobrescrever)
    return _imprimir(laudo, args, formatar_texto)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return _executar(args)
    except ErroConfig as e:
        prefixo = "inseguro" if args.comando == "dados" else "erro"
        print(f"{prefixo}: {e}", file=sys.stderr)
        return 2
