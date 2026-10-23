"""CLI do motor Shiba: casca fina sobre `shiba/api.py`.

  python -m shiba verificar ARQUIVO --cliente ID --plataforma ID [opções]
  python -m shiba roteiro verificar ROTEIRO.toml --cliente ID [opções]
  python -m shiba calendario verificar CALENDARIO.toml --cliente ID [opções]
  python -m shiba config mostrar --cliente ID [--plataforma ID] [--dados [DIR]]
  python -m shiba identidade cadastrar|revogar ...      (Incremento 4)
  python -m shiba peca registrar|verificar|enviar|status|reconhecer|aprovar|rejeitar|
                       validar-normativo|recusar-normativo|liberar ...
  python -m shiba auditoria verificar|exportar-topo ...

Fluxo de aprovação (Incremento 4): estado SEMPRE fora do Git (--estado DIR para
clientes fictícios; o próprio diretório de --dados para reais). Decisões humanas
exigem terminal interativo e a digitação do início do hash; isso é atrito de
PROCESSO, não proteção criptográfica. Agentes de IA não executam decisões
reais; --simulacao (só cliente fictício) marca tudo como simulação.
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

from . import api, fluxo
from .aprovacao import (
    APROVACAO_EDITORIAL,
    RECUSA_NORMATIVA,
    REJEICAO_EDITORIAL,
    VALIDACAO_NORMATIVA,
    ErroAprovacao,
)
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

    k = sub.add_parser("calendario", help="calendário editorial")
    k_sub = k.add_subparsers(dest="acao", required=True)
    kv = k_sub.add_parser("verificar", help="verifica um calendário TOML")
    kv.add_argument("arquivo", type=Path)
    kv.add_argument("--formato", choices=("texto", "json"), default="texto")
    kv.add_argument("--data-referencia", type=_data)
    _opcoes_de_origem(kv)

    c = sub.add_parser("config", help="configuração efetiva de um cliente")
    c_sub = c.add_subparsers(dest="acao", required=True)
    m = c_sub.add_parser("mostrar", help="mostra a configuração após a herança e a origem de cada valor")
    m.add_argument("--plataforma")
    _opcoes_de_origem(m)

    _parser_fluxo(sub)

    d = sub.add_parser("dados", help="diretório de dados reais")
    d_sub = d.add_subparsers(dest="acao", required=True)
    dv = d_sub.add_parser("verificar", help="confere se o diretório de dados é seguro (não lista o conteúdo)")
    dv.add_argument("dir", nargs="?", default="")
    return p


ATOS_CLI = {"aprovar": APROVACAO_EDITORIAL, "rejeitar": REJEICAO_EDITORIAL,
            "validar-normativo": VALIDACAO_NORMATIVA, "recusar-normativo": RECUSA_NORMATIVA}


def _opcoes_de_estado(p: argparse.ArgumentParser, simulacao: bool = False) -> None:
    p.add_argument("--cliente", required=True)
    p.add_argument("--estado", type=Path, help="diretório de estado fora do Git (clientes fictícios)")
    p.add_argument("--dados", nargs="?", const="", default=None, metavar="DIR")
    p.add_argument("--dir-clientes", type=Path, default=None)
    p.add_argument("--dir-plataformas", type=Path, default=DIR_PLATAFORMAS)
    p.add_argument("--data-referencia", type=_data)
    p.add_argument("--formato", choices=("texto", "json"), default="texto")
    if simulacao:
        p.add_argument("--simulacao", action="store_true",
                       help="decisão SIMULADA (só cliente fictício); nunca vale como aprovação real")


def _parser_fluxo(sub) -> None:
    i = sub.add_parser("identidade", help="cadastro controlado de identidades lógicas")
    i_sub = i.add_subparsers(dest="acao", required=True)
    ic = i_sub.add_parser("cadastrar")
    ic.add_argument("--id", required=True)
    ic.add_argument("--papel", action="append", required=True)
    ic.add_argument("--processo", required=True, help="referência do processo de cadastro")
    ic.add_argument("--por", required=True, help="identidade cadastradora (ou 'bootstrap')")
    _opcoes_de_estado(ic, simulacao=True)
    ir = i_sub.add_parser("revogar")
    ir.add_argument("--id", required=True)
    ir.add_argument("--por", required=True)
    ir.add_argument("--motivo", required=True)
    _opcoes_de_estado(ir, simulacao=True)

    pc = sub.add_parser("peca", help="versões, revisão, decisões e liberação")
    p_sub = pc.add_subparsers(dest="acao", required=True)
    pr = p_sub.add_parser("registrar")
    pr.add_argument("arquivo", type=Path)
    pr.add_argument("--peca", required=True)
    pr.add_argument("--tipo", choices=("legenda", "roteiro"), required=True)
    pr.add_argument("--plataforma")
    pr.add_argument("--autor", required=True)
    pr.add_argument("--fatos-peca", type=Path)
    _opcoes_de_estado(pr)
    for nome in ("verificar", "status"):
        x = p_sub.add_parser(nome)
        x.add_argument("--peca", required=True)
        if nome == "status":
            x.add_argument("--arquivo", type=Path, help="arquivo de trabalho a comparar")
        _opcoes_de_estado(x)
    pe = p_sub.add_parser("enviar")
    pe.add_argument("--peca", required=True)
    pe.add_argument("--por", required=True)
    _opcoes_de_estado(pe)
    rc = p_sub.add_parser("reconhecer")
    rc.add_argument("--peca", required=True)
    rc.add_argument("--aviso", required=True)
    rc.add_argument("--identidade", required=True)
    rc.add_argument("--papel", required=True)
    rc.add_argument("--justificativa", required=True)
    _opcoes_de_estado(rc, simulacao=True)
    for nome in ATOS_CLI:
        x = p_sub.add_parser(nome)
        x.add_argument("--peca", required=True)
        x.add_argument("--identidade", required=True)
        x.add_argument("--papel", required=True)
        x.add_argument("--justificativa", default="")
        _opcoes_de_estado(x, simulacao=True)
    pl = p_sub.add_parser("liberar")
    pl.add_argument("--peca", required=True)
    pl.add_argument("--identidade", required=True)
    _opcoes_de_estado(pl, simulacao=True)

    a = sub.add_parser("auditoria", help="registro encadeado")
    a_sub = a.add_subparsers(dest="acao", required=True)
    av = a_sub.add_parser("verificar")
    av.add_argument("--topo", type=Path, help="topo exportado antes, para comparar")
    _opcoes_de_estado(av)
    ae = a_sub.add_parser("exportar-topo")
    ae.add_argument("--destino", type=Path, required=True)
    _opcoes_de_estado(ae)


def _confirmar(esperado: str, mensagem: str) -> None:
    """Atrito de processo para decisões humanas. NÃO é proteção criptográfica."""
    if not sys.stdin.isatty():
        raise ErroAprovacao("decisão humana exige terminal interativo (ou --simulacao com cliente "
                            "fictício)")
    digitado = input(f"{mensagem}: ").strip()
    if digitado != esperado:
        raise ErroAprovacao("confirmação não confere; nada foi registrado")


def _resumo_estado(e: dict) -> str:
    linhas = [f"Peça {e.get('peca')} · versão {e.get('versao', '?')} · estado: {e['estado'].upper()}"]
    if e.get("simulacao"):
        linhas.append("SIMULAÇÃO: sem valor de aprovação real.")
    if "hash_conteudo" in e:
        linhas.append(f"hash do conteúdo: {e['hash_conteudo']}")
    for chave, titulo in (("aprovacoes_editoriais", "aprovação editorial"),
                          ("validacoes_normativas", "validação normativa")):
        for a in e.get(chave, []):
            linhas.append(f"  {titulo}: {a['identidade']} ({a['papel']}, {a['nivel']})")
    for d in e.get("descartadas", []):
        linhas.append(f"  descartada: {d['ato']} de {d['identidade']}: {d['motivo']}")
    for p in e.get("pendencias", []):
        linhas.append(f"  pendente: {p}")
    if e.get("aviso_nivel"):
        linhas.append(e["aviso_nivel"])
    if e.get("arquivo_de_trabalho"):
        linhas.append(f"arquivo de trabalho: {e['arquivo_de_trabalho']}")
    if e.get("motivo"):
        linhas.append(f"motivo: {e['motivo']}")
    if e["estado"] == "aprovado":
        linhas.append("Aprovado = conteúdo TEXTUAL aprovado por pessoas. Não é publicação, nem "
                      "revisão do vídeo final.")
    return "\n".join(linhas)


def _saida(args, dados: dict, texto: str) -> None:
    print(json.dumps(dados, ensure_ascii=False, indent=2) if args.formato == "json" else texto)


def _executar_fluxo(args) -> int:
    amb = fluxo.abrir(args.estado, args.dados, args.dir_clientes, args.dir_plataformas)
    hoje = getattr(args, "data_referencia", None)
    sim = getattr(args, "simulacao", False)
    if args.comando == "identidade":
        if not sim:
            _confirmar(args.id, f"Digite o identificador '{args.id}' para confirmar")
        if args.acao == "cadastrar":
            r = fluxo.cadastrar_identidade(amb, args.cliente, args.id, args.papel, args.processo,
                                           args.por, simulacao=sim)
        else:
            r = fluxo.revogar_identidade(amb, args.cliente, args.id, args.por, args.motivo, simulacao=sim)
        _saida(args, r, f"registrado: {r['evento']} (seq {r['seq']})")
        return 0
    if args.comando == "auditoria":
        if args.acao == "verificar":
            r = fluxo.verificar_auditoria(amb, args.cliente, args.topo)
            _saida(args, r, f"íntegro: seq {r['topo']['seq']}, topo {r['topo']['hash']}\n{r['observacao']}")
        else:
            r = fluxo.exportar_topo_auditoria(amb, args.cliente, args.destino)
            _saida(args, r, f"topo exportado: seq {r['seq']}, {r['hash']}")
        return 0
    acao = args.acao
    if acao == "registrar":
        r = fluxo.registrar_versao(amb, args.cliente, args.peca, args.arquivo, args.tipo, args.autor,
                                   args.plataforma, args.fatos_peca, hoje)
        _saida(args, r, f"versão {r['dados']['versao']} registrada; hash {r['dados']['hash_conteudo']}")
        return 0
    if acao == "verificar":
        r = fluxo.verificar_versao(amb, args.cliente, args.peca, hoje)
        _saida(args, r, _resumo_estado(r["estado"]))
        return 0
    if acao == "status":
        r = fluxo.status(amb, args.cliente, args.peca, hoje, args.arquivo)
        _saida(args, r, _resumo_estado(r))
        return 2 if r["estado"] == "integridade_nao_confirmada" else 0
    if acao == "enviar":
        r = fluxo.enviar_para_revisao(amb, args.cliente, args.peca, args.por, hoje)
        _saida(args, r, _resumo_estado(r))
        return 0
    atual = fluxo.status(amb, args.cliente, args.peca, hoje)
    if atual["estado"] == "integridade_nao_confirmada":
        _saida(args, atual, _resumo_estado(atual))
        return 2
    vistos = {k: atual[k] for k in ("hash_conteudo", "hash_config", "hash_laudo")}
    if not sim:
        print(_resumo_estado(atual))
        _confirmar(atual["hash_conteudo"][:8], "Digite os 8 primeiros caracteres do hash do conteúdo")
    if acao == "reconhecer":
        r = fluxo.reconhecer_aviso(amb, args.cliente, args.peca, args.aviso, args.identidade, args.papel,
                                   args.justificativa, vistos, sim, hoje)
    elif acao == "liberar":
        r = fluxo.liberar(amb, args.cliente, args.peca, args.identidade, sim, hoje)
        _saida(args, r, f"pacote: {r['pacote']}\nCONTEÚDO TEXTUAL APROVADO: não autoriza publicar a "
                        "peça audiovisual sem revisão do vídeo final."
                        + ("\nSIMULAÇÃO: NÃO PUBLICAR." if r["manifesto"]["simulacao"] else ""))
        return 0
    else:
        r = fluxo.decidir(amb, args.cliente, args.peca, ATOS_CLI[acao], args.identidade, args.papel,
                          args.justificativa, vistos, sim, hoje)
    _saida(args, r, _resumo_estado(r))
    return 0


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
    if args.comando in ("identidade", "peca", "auditoria"):
        return _executar_fluxo(args)
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
    if args.comando == "calendario":
        laudo = api.verificar_calendario_arquivo(args.arquivo, args.cliente, o,
                                                 dir_plataformas=args.dir_plataformas,
                                                 hoje=args.data_referencia)
        return _imprimir(laudo, args, formatar_generico)
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
    except (ErroConfig, ErroAprovacao) as e:
        prefixo = "inseguro" if args.comando == "dados" else "erro"
        print(f"{prefixo}: {e}", file=sys.stderr)
        return 2
