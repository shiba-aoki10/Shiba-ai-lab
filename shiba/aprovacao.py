"""Aprovação humana por papéis e cálculo do estado de uma peça (Incremento 4B).

ESTADOS (sempre CALCULADOS; nunca gravados nem editáveis):
  rascunho                        versão registrada, com bloqueante ou ainda não verificada
                                  com a configuração atual
  verificado                      verificada sem bloqueante, ainda não enviada para revisão
  aguardando_revisao              enviada; falta quórum editorial ou reconhecer avisos
  aguardando_validacao_normativa  revisão completa; falta o responsável competente
  aprovado                        todas as decisões humanas exigidas, válidas para o
                                  conteúdo, a configuração e o laudo ATUAIS
  rejeitado                       rejeição editorial ou recusa normativa da versão atual

Três atos DIFERENTES:
  aprovação editorial   revisores (papel em [equipe] aprovadores)
  validação normativa   responsável competente (papel em validadores_normativos)
  liberação manual      monta o pacote textual; NÃO é aprovação nem publicação

Uma decisão só conta se: for da versão atual (toda nova versão zera as
anteriores, mesmo com bytes iguais a uma versão antiga); os três hashes forem
os atuais; a identidade estiver ativa e tiver o papel; o nível de garantia
atingir o mínimo; e as regras de independência valerem (por IDENTIDADE).
"Passou nos testes" nunca leva a "aprovado": só decisões humanas válidas.
"""
from __future__ import annotations

from dataclasses import dataclass

from .auditoria import ErroIntegridade
from .dependencias import Avaliacao
from .hashes import id_do_achado
from .identidades import Identidade, identidades

ESTADOS = ("rascunho", "verificado", "aguardando_revisao", "aguardando_validacao_normativa",
           "aprovado", "rejeitado")
APROVACAO_EDITORIAL, REJEICAO_EDITORIAL = "aprovacao_editorial", "rejeicao_editorial"
VALIDACAO_NORMATIVA, RECUSA_NORMATIVA = "validacao_normativa", "recusa_normativa"
ATOS = (APROVACAO_EDITORIAL, REJEICAO_EDITORIAL, VALIDACAO_NORMATIVA, RECUSA_NORMATIVA)
NIVEIS = ("declarativa", "autenticada")
AVISO_DECLARATIVA = ("Aprovação DECLARATIVA: registra quem afirmou decidir, mas não prova "
                     "identidade (nem civil, nem criptográfica).")


class ErroAprovacao(Exception):
    pass


@dataclass(frozen=True)
class Politica:
    aprovacoes_minimas: int
    revisao_independente: bool
    validacao_normativa_independente: bool
    nivel_minimo: str
    exige_validacao_normativa: bool
    aprovadores: frozenset
    validadores: frozenset
    autores: frozenset
    papeis: frozenset
    cadastradores: frozenset


def politica_de(cliente) -> Politica:
    rev, eq = cliente.secoes.get("revisao", {}), cliente.secoes.get("equipe", {})
    return Politica(
        aprovacoes_minimas=rev.get("aprovacoes_minimas", rev.get("aprovacoes_sugeridas", 1)),
        revisao_independente=rev.get("revisao_independente", True),
        validacao_normativa_independente=rev.get("validacao_normativa_independente", True),
        nivel_minimo=rev.get("nivel_minimo", "declarativa"),
        exige_validacao_normativa=rev.get("exige_validacao_normativa", False),
        aprovadores=frozenset(eq.get("aprovadores", [])),
        validadores=frozenset(eq.get("validadores_normativos", [])),
        autores=frozenset(eq.get("autores", []) or eq.get("papeis", [])),
        papeis=frozenset(eq.get("papeis", [])),
        cadastradores=frozenset(eq.get("cadastradores", [])),
    )


def papeis_do_ato(ato: str, politica: Politica) -> frozenset:
    return politica.aprovadores if ato in (APROVACAO_EDITORIAL, REJEICAO_EDITORIAL) else politica.validadores


def _da_peca(e: dict, peca: str) -> bool:
    return e["dados"].get("peca") == peca


def versao_atual(entradas: list[dict], peca: str) -> dict | None:
    versoes = [e for e in entradas if e["evento"] == "versao_registrada" and _da_peca(e, peca)]
    return versoes[-1]["dados"] if versoes else None


def _motivo_invalido(d: dict, aval: Avaliacao, versao: int, ids: dict[str, Identidade],
                     politica: Politica, papeis_validos: frozenset, aceitar_simulacao: bool) -> str:
    """Por que uma decisão NÃO conta (vazio = conta)."""
    if d.get("versao") != versao:
        return "decisão de outra versão (toda nova versão invalida as anteriores)"
    if (d.get("hash_conteudo"), d.get("hash_config"), d.get("hash_laudo")) != \
            (aval.hash_conteudo, aval.hash_config, aval.hash_laudo):
        return "conteúdo, configuração ou laudo mudaram depois da decisão"
    if d.get("simulacao") and not aceitar_simulacao:
        return "decisão simulada não vale para cliente real"
    ident = ids.get(d.get("identidade"))
    if ident is None or not ident.ativa:
        return "identidade inexistente ou revogada"
    if d.get("papel") not in ident.papeis or d.get("papel") not in papeis_validos:
        return "a identidade não tem o papel exigido para este ato"
    if d.get("papel") not in politica.papeis:
        return "papel não pertence mais à equipe do cliente"
    if NIVEIS.index(d.get("nivel", "declarativa")) < NIVEIS.index(politica.nivel_minimo):
        return (f"nível {d.get('nivel', 'declarativa')} abaixo do mínimo {politica.nivel_minimo} "
                "(assinatura autenticada ainda não disponível: Incremento 4D)")
    return ""


def avisos_do_laudo(laudo: dict) -> list[str]:
    return sorted({id_do_achado(a) for a in laudo.get("achados", []) if a["severidade"] == "aviso"})


def calcular_estado(entradas: list[dict], peca: str, aval: Avaliacao, politica: Politica,
                    aceitar_simulacao: bool) -> dict:
    """Estado da versão atual de `peca`, derivado de eventos válidos e de `aval` (agora)."""
    v = versao_atual(entradas, peca)
    if v is None:
        raise ErroAprovacao("peça não registrada")
    if v["hash_conteudo"] != aval.hash_conteudo:
        raise ErroIntegridade("a cópia guardada da versão não confere com o registro")
    if v.get("simulacao") and not aceitar_simulacao:
        raise ErroIntegridade("versão simulada no histórico de um cliente real")
    versao, autor = v["versao"], v["autor"]
    ids = identidades(entradas)
    atuais = (aval.hash_conteudo, aval.hash_config, aval.hash_laudo)
    do_atual = [e for e in entradas if _da_peca(e, peca) and e["dados"].get("versao") == versao]

    def com_hashes_atuais(e):
        d = e["dados"]
        return (d.get("hash_conteudo"), d.get("hash_config"), d.get("hash_laudo")) == atuais

    resultado = {"peca": peca, "versao": versao, "autor": autor, **aval.hashes,
                 "aprovacoes_editoriais": [], "validacoes_normativas": [], "descartadas": [],
                 "pendencias": [], "simulacao": False, "nivel_garantia": None}

    def fim(estado, *pendencias):
        resultado["estado"] = estado
        resultado["pendencias"] += list(pendencias)
        contadas = resultado["aprovacoes_editoriais"] + resultado["validacoes_normativas"]
        if contadas:
            resultado["nivel_garantia"] = min((c["nivel"] for c in contadas), key=NIVEIS.index)
            resultado["simulacao"] = any(c["simulacao"] for c in contadas)
        if resultado["nivel_garantia"] == "declarativa":
            resultado["aviso_nivel"] = AVISO_DECLARATIVA
        return resultado

    if aval.laudo.get("resultado") == "bloqueado":
        return fim("rascunho", "corrigir os bloqueantes e registrar nova versão")
    if not any(e["evento"] == "verificacao" and com_hashes_atuais(e) for e in do_atual):
        return fim("rascunho", "verificar a versão atual (nunca verificada, ou a configuração, "
                               "os fatos ou o laudo mudaram desde a última verificação)")
    if not any(e["evento"] == "enviada" and com_hashes_atuais(e) for e in do_atual):
        return fim("verificado", "enviar para revisão")

    decisoes = [e["dados"] for e in do_atual if e["evento"] == "decisao"]
    contadas_editorial: dict[str, dict] = {}
    rejeicoes = []
    for d in decisoes:
        motivo = _motivo_invalido(d, aval, versao, ids, politica, papeis_do_ato(d["ato"], politica),
                                  aceitar_simulacao)
        ident = d.get("identidade")
        if not motivo and politica.revisao_independente and ident == autor:
            motivo = "o autor não decide sobre a própria peça (revisão independente)"
        if not motivo and d["ato"] == APROVACAO_EDITORIAL and ident in contadas_editorial:
            motivo = "identidade já aprovou esta versão (aprovação duplicada)"
        if motivo:
            resultado["descartadas"].append({"ato": d["ato"], "identidade": ident, "motivo": motivo})
            continue
        registro = {"identidade": ident, "papel": d["papel"], "nivel": d.get("nivel", "declarativa"),
                    "simulacao": bool(d.get("simulacao"))}
        if d["ato"] in (REJEICAO_EDITORIAL, RECUSA_NORMATIVA):
            rejeicoes.append(dict(registro, ato=d["ato"], justificativa=d.get("justificativa", "")))
        elif d["ato"] == APROVACAO_EDITORIAL:
            contadas_editorial[ident] = registro
    if rejeicoes:
        resultado["rejeicoes"] = rejeicoes
        return fim("rejeitado", "registrar nova versão para reiniciar o fluxo")

    resultado["aprovacoes_editoriais"] = list(contadas_editorial.values())
    reconhecidos = set()
    for e in do_atual:
        if e["evento"] != "aviso_reconhecido" or not com_hashes_atuais(e):
            continue
        d = e["dados"]
        motivo = _motivo_invalido(d, aval, versao, ids, politica, politica.aprovadores, aceitar_simulacao)
        if not motivo and not (politica.revisao_independente and d.get("identidade") == autor):
            reconhecidos.add(d["aviso"])
    faltando = [a for a in avisos_do_laudo(aval.laudo) if a not in reconhecidos]
    pend = []
    if len(contadas_editorial) < politica.aprovacoes_minimas:
        pend.append(f"aprovação editorial: {len(contadas_editorial)} de "
                    f"{politica.aprovacoes_minimas} identidade(s) distinta(s)")
    if faltando:
        pend.append(f"reconhecer {len(faltando)} aviso(s): {', '.join(faltando)}")
    if pend:
        return fim("aguardando_revisao", *pend)

    if politica.exige_validacao_normativa or aval.laudo.get("requer_validacao_normativa"):
        revisores = set(contadas_editorial)
        for d in decisoes:
            if d["ato"] != VALIDACAO_NORMATIVA:
                continue
            motivo = _motivo_invalido(d, aval, versao, ids, politica, politica.validadores,
                                      aceitar_simulacao)
            ident = d.get("identidade")
            if not motivo and politica.validacao_normativa_independente and \
                    (ident == autor or ident in revisores):
                motivo = "validação normativa independente: o validador não pode ser o autor nem um revisor"
            if motivo:
                resultado["descartadas"].append({"ato": d["ato"], "identidade": ident, "motivo": motivo})
                continue
            resultado["validacoes_normativas"].append({
                "identidade": ident, "papel": d["papel"], "nivel": d.get("nivel", "declarativa"),
                "simulacao": bool(d.get("simulacao"))})
        if not resultado["validacoes_normativas"]:
            return fim("aguardando_validacao_normativa",
                       "validação normativa pelo responsável competente (identidade independente)")
    return fim("aprovado")


def validar_pedido(entradas: list[dict], peca: str, ato: str, identidade: str, papel: str,
                   hashes_vistos: dict, aval: Avaliacao, politica: Politica,
                   aceitar_simulacao: bool) -> None:
    """Confere um pedido de decisão ANTES de registrá-lo. Levanta ErroAprovacao com o motivo.

    O cálculo de estado confere tudo de novo: esta etapa só evita registrar
    decisões que já nasceriam inválidas.
    """
    if ato not in ATOS:
        raise ErroAprovacao(f"ato deve ser um de {ATOS}")
    if hashes_vistos != aval.hashes:
        raise ErroAprovacao("a versão, a configuração ou o laudo mudaram desde que foram exibidos; "
                            "confira de novo antes de decidir")
    estado = calcular_estado(entradas, peca, aval, politica, aceitar_simulacao)
    v = versao_atual(entradas, peca)
    if ato in (APROVACAO_EDITORIAL, REJEICAO_EDITORIAL) and estado["estado"] != "aguardando_revisao":
        if not (ato == REJEICAO_EDITORIAL and estado["estado"] == "aguardando_validacao_normativa"):
            raise ErroAprovacao(f"a peça está em '{estado['estado']}', não em revisão")
    if ato in (VALIDACAO_NORMATIVA, RECUSA_NORMATIVA) and estado["estado"] != "aguardando_validacao_normativa":
        raise ErroAprovacao(f"a peça está em '{estado['estado']}', não aguardando validação normativa")
    pedido = {"versao": v["versao"], **aval.hashes, "identidade": identidade, "papel": papel,
              "nivel": "declarativa", "simulacao": aceitar_simulacao}
    motivo = _motivo_invalido(pedido, aval, v["versao"], identidades(entradas), politica,
                              papeis_do_ato(ato, politica), True)
    if motivo:
        raise ErroAprovacao(motivo)
    if politica.revisao_independente and identidade == v["autor"]:
        raise ErroAprovacao("o autor não decide sobre a própria peça (revisão independente)")
    ja = {c["identidade"] for c in estado["aprovacoes_editoriais"]}
    if ato == APROVACAO_EDITORIAL and identidade in ja:
        raise ErroAprovacao("identidade já aprovou esta versão (aprovação duplicada)")
    if ato in (VALIDACAO_NORMATIVA, RECUSA_NORMATIVA) and politica.validacao_normativa_independente \
            and identidade in ja:
        raise ErroAprovacao("validação normativa independente: um revisor desta versão não pode validá-la")
