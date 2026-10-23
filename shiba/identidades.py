"""Identidades lógicas e cadastro controlado (Incremento 4B).

Três conceitos que NÃO se confundem:
- papel ("resp-02"): o que alguém PODE fazer, definido em [equipe];
- identidade lógica ("id-ana-01" ou opaca, como "id-7f3a"): QUEM fez,
  segundo o cadastro;
- nível de garantia: "declarativa" (ninguém provou nada) ou "autenticada"
  (assinatura criptográfica, Incremento 4D).

Uma identidade lógica representa uma pessoa ou um responsável segundo o
PROCESSO DE CADASTRO do cliente (ex.: termo assinado e arquivado fora do
sistema). O motor registra QUEM cadastrou, QUANDO e SOB QUAL processo, mas
NÃO verifica identidade civil. Mesmo uma assinatura criptográfica (4D) só
prova a posse de uma chave, não quem é a pessoa: o vínculo pessoa ↔
identidade ↔ chave é responsabilidade do processo de cadastro.

As identidades vivem como EVENTOS no registro encadeado do cliente (fora do
Git), não num arquivo editável à parte. Nomes de pessoas não são exigidos e
não devem ser usados como identificador.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_ID = re.compile(r"[a-z0-9][a-z0-9-]{2,62}")
BOOTSTRAP = "bootstrap"


class ErroIdentidade(Exception):
    pass


@dataclass(frozen=True)
class Identidade:
    id: str
    papeis: tuple[str, ...]
    ativa: bool
    processo: str
    cadastrada_por: str
    simulacao: bool
    seq: int


def identidades(entradas: list[dict]) -> dict[str, Identidade]:
    """Estado atual das identidades a partir dos eventos (cadastro e revogação)."""
    atuais: dict[str, Identidade] = {}
    for e in entradas:
        d = e["dados"]
        if e["evento"] == "identidade_cadastrada":
            atuais[d["identidade"]] = Identidade(d["identidade"], tuple(d["papeis"]), True,
                                                 d["processo"], d["cadastrada_por"],
                                                 bool(d.get("simulacao")), e["seq"])
        elif e["evento"] == "identidade_revogada" and d["identidade"] in atuais:
            antiga = atuais[d["identidade"]]
            atuais[d["identidade"]] = Identidade(antiga.id, antiga.papeis, False, antiga.processo,
                                                 antiga.cadastrada_por, antiga.simulacao, e["seq"])
    return atuais


def validar_cadastro(ids: dict[str, Identidade], identidade: str, papeis: list[str], processo: str,
                     cadastrada_por: str, papeis_equipe: set[str], cadastradores: set[str]) -> None:
    """Regras do cadastro controlado. Levanta ErroIdentidade com o motivo."""
    if not _ID.fullmatch(identidade or ""):
        raise ErroIdentidade("identidade deve ser um identificador (a-z, 0-9, hífen; 3 a 63 "
                             "caracteres), nunca um nome de pessoa")
    if identidade == BOOTSTRAP:
        raise ErroIdentidade("'bootstrap' é reservado")
    if identidade in ids:
        raise ErroIdentidade("identidade já cadastrada (revogada também não pode ser reaproveitada)")
    if not papeis or any(p not in papeis_equipe for p in papeis):
        raise ErroIdentidade("papéis devem existir em [equipe] papeis do cliente")
    if not (processo or "").strip():
        raise ErroIdentidade("informe a referência do processo de cadastro (ex.: termo arquivado "
                             "fora do sistema); o motor não verifica identidade civil")
    if not cadastradores:
        raise ErroIdentidade("o cliente não definiu [equipe] cadastradores")
    ativas = [i for i in ids.values() if i.ativa]
    if cadastrada_por == BOOTSTRAP:
        if ativas:
            raise ErroIdentidade("'bootstrap' só vale para a primeira identidade do cliente")
        if not set(papeis) & cadastradores:
            raise ErroIdentidade("a primeira identidade precisa ter um papel cadastrador")
        return
    quem = ids.get(cadastrada_por)
    if quem is None or not quem.ativa or not set(quem.papeis) & cadastradores:
        raise ErroIdentidade("cadastrada_por precisa ser uma identidade ativa com papel cadastrador")
    if cadastrada_por == identidade:
        raise ErroIdentidade("uma identidade não cadastra a si mesma")
