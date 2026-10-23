"""Seções de configuração do Incremento 3 e validação dos seus valores.

Sem importações do motor: é usado por config.py (carga) e pelos módulos de
regras (nomes válidos), sem criar dependência circular.
"""
from __future__ import annotations

import re

# Seções herdáveis que o Cliente expõe em `cliente.secoes`.
SECOES = ("editorial", "roteiro", "calendario", "equipe", "revisao", "normas")

# Regras editoriais que podem ser desligadas em [editorial] regras_desativadas.
REGRAS_EDITORIAIS = (
    "ia", "cliche", "muleta", "termos_cliente", "frase_longa", "paragrafo_longo",
    "repeticao_palavra", "repeticao_inicio", "adverbios_mente", "pontuacao", "caixa_alta",
)

# Nível de garantia de uma decisão: declarativa (sem prova de identidade) <
# autenticada (assinatura criptográfica; Incremento 4D, ainda não disponível).
NIVEIS = ("declarativa", "autenticada")
CAMPOS_NORMA = {"titulo", "fonte", "status", "consultado_em", "verificado_por", "nota"}
_PAPEL = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")


class ErroSecao(Exception):
    pass


def _lista_textos(valor, nome: str, origem: str) -> list[str]:
    if not all(isinstance(v, str) and v.strip() for v in valor):
        raise ErroSecao(f"{origem}: {nome} deve conter só textos não vazios")
    return valor


def validar_secoes(efetiva: dict, origem: str) -> None:
    """Valida valores (não só tipos) das seções do Incremento 3."""
    editorial = efetiva.get("editorial", {})
    for nome in _lista_textos(editorial.get("regras_desativadas", []), "regras_desativadas", origem):
        if nome not in REGRAS_EDITORIAIS:
            raise ErroSecao(f"{origem} [editorial]: regra desconhecida em regras_desativadas: {nome}")
    for chave in ("termos_extras", "termos_ignorados"):
        _lista_textos(editorial.get(chave, []), chave, origem)
    for chave, valor in editorial.items():
        if isinstance(valor, int) and valor <= 0:
            raise ErroSecao(f"{origem} [editorial]: {chave} deve ser positivo")
    for chave, valor in efetiva.get("roteiro", {}).items():
        if not isinstance(valor, bool) and isinstance(valor, (int, float)) and valor <= 0:
            raise ErroSecao(f"{origem} [roteiro]: {chave} deve ser positivo")
    equipe = efetiva.get("equipe", {})
    for chave in ("papeis", "aprovadores", "validadores_normativos", "autores", "cadastradores"):
        for papel in _lista_textos(equipe.get(chave, []), chave, origem):
            if not _PAPEL.fullmatch(papel):
                raise ErroSecao(f"{origem} [equipe]: {chave} aceita só identificadores de papel "
                                "(a-z, 0-9, hífen), nunca nomes de pessoas")
    revisao = efetiva.get("revisao", {})
    for chave in ("categorias_validacao_normativa", "listas_validacao"):
        _lista_textos(revisao.get(chave, []), chave, origem)
    for chave in ("aprovacoes_sugeridas", "aprovacoes_minimas"):
        if revisao.get(chave, 1) < 1:
            raise ErroSecao(f"{origem} [revisao]: {chave} deve ser positivo")
    if revisao.get("nivel_minimo", "declarativa") not in NIVEIS:
        raise ErroSecao(f"{origem} [revisao]: nivel_minimo deve ser um de {NIVEIS}")
    for n, ref in enumerate(efetiva.get("normas", {}).get("referencias", []), 1):
        local = f"{origem} [normas] referência #{n}"
        if not isinstance(ref, dict) or set(ref) - CAMPOS_NORMA:
            raise ErroSecao(f"{local}: use tabelas com os campos {sorted(CAMPOS_NORMA)}")
        for campo in ("titulo", "status"):
            if not isinstance(ref.get(campo), str) or not ref[campo].strip():
                raise ErroSecao(f"{local}: campo obrigatório ausente ou vazio: {campo}")
        if ref["status"] not in ("a_verificar", "verificado"):
            raise ErroSecao(f"{local}: status deve ser 'a_verificar' ou 'verificado'")
        if ref["status"] == "verificado" and not all(
                str(ref.get(c, "")).strip() for c in ("fonte", "consultado_em", "verificado_por")):
            raise ErroSecao(f"{local}: 'verificado' exige fonte, consultado_em e verificado_por")
    papeis = set(equipe.get("papeis", []))
    for chave in ("aprovadores", "validadores_normativos", "autores", "cadastradores"):
        fora = [p for p in equipe.get(chave, []) if p not in papeis]
        if fora:
            raise ErroSecao(f"{origem} [equipe]: {chave} cita papel fora de papeis: {fora[0]}")
