"""Herança de configuração: padrão → segmento → cliente (e ajustes por plataforma).

Regras de mesclagem, aplicadas camada por camada, da menos para a mais específica:

- Tabela (ex.: [hashtags]): mesclada chave a chave, recursivamente.
- Valor simples (número, texto, booleano): a camada mais específica substitui.
- Lista: SOMADA à herdada, sem repetir itens (comparação sem maiúsculas,
  acentos e "#"). A ordem é: herdados primeiro, depois os da camada.
- `chave__substituir = [...]`: troca a lista herdada inteira ([] esvazia).
- `chave__remover = [...]`: tira itens da lista herdada; depois entram os
  itens de `chave`, se houver. `chave` e `chave__substituir` na mesma camada
  é erro (ambíguo).
- Chave ausente: herda o valor da camada anterior. Não há como "apagar" um
  valor simples (TOML não tem nulo); só sobrescrever.
- Tipo diferente entre camadas (lista × texto, tabela × número) é erro.

Ordem completa para um cliente numa plataforma P:
  padrão, padrão@P, segmento, segmento@P, cliente, cliente@P
(@P = tabela [plataformas.P] da própria camada). Assim o ajuste geral do
cliente vence o ajuste por plataforma do segmento: o cliente decide.
"""
from __future__ import annotations

import copy

from .texto import dobrar

SUBSTITUIR, REMOVER = "__substituir", "__remover"

NUMERO = (int, float)

# Chaves de configuração herdáveis e seus tipos.
ESQUEMA = {
    "hashtags": {"minimo": int, "maximo": int, "proibidas": list},
    "palavras_proibidas": {"termos": list},
    "fatos": {"categorias_sensiveis": list},
    # Incremento 3A: revisor editorial (limiares são [meta proposta, a calibrar]).
    "editorial": {
        "regras_desativadas": list, "termos_extras": list, "termos_ignorados": list,
        "ia_por_paragrafo_aviso": int, "frase_max_palavras": int,
        "paragrafo_max_frases": int, "repeticao_min": int, "palavra_min_letras": int,
        "mente_max_por_frase": int, "caixa_alta_min_palavras": int,
    },
    # Incremento 3B: roteiro audiovisual.
    "roteiro": {
        "palavras_por_segundo": NUMERO, "janela_gancho_s": NUMERO,
        "tolerancia_duracao_pct": NUMERO, "texto_tela_max_palavras": int,
    },
}


def _nome_tipo(tipo) -> str:
    return {list: "lista", int: "int", bool: "bool", str: "texto", NUMERO: "número"}.get(tipo, str(tipo))


def tipo_ok(valor, tipo) -> bool:
    """Confere o tipo; bool nunca vale como número (TOML distingue, Python não)."""
    if isinstance(valor, bool) and tipo is not bool:
        return False
    return isinstance(valor, tipo)
# Chaves que descrevem a própria camada e nunca são herdadas.
META = {
    "padrao": {"id", "nome", "descricao"},
    "segmento": {"id", "nome", "descricao"},
    "cliente": {"id", "nome", "descricao", "ficticio", "segmento"},
    "plataforma": set(),
}


class ErroHeranca(Exception):
    """Camada com chave desconhecida, tipo errado ou operador ambíguo."""


def normalizar_item(item) -> str:
    return dobrar(str(item).strip().lstrip("#"))


def _sem_operador(chave: str) -> tuple[str, str]:
    for op in (SUBSTITUIR, REMOVER):
        if chave.endswith(op):
            return chave[: -len(op)], op
    return chave, ""


def validar_camada(dados: dict, origem: str, tipo: str) -> None:
    """Recusa chaves desconhecidas: um erro de digitação não pode desligar uma regra."""
    permitidas = set(ESQUEMA) | META[tipo] | ({"plataformas"} if tipo != "plataforma" else set())
    for chave, valor in dados.items():
        if chave not in permitidas:
            raise ErroHeranca(f"{origem}: chave desconhecida: {chave}")
        if chave == "plataformas":
            if not isinstance(valor, dict):
                raise ErroHeranca(f"{origem}: [plataformas] deve ser uma tabela")
            for pid, sub in valor.items():
                if not isinstance(sub, dict):
                    raise ErroHeranca(f"{origem}: [plataformas.{pid}] deve ser uma tabela")
                validar_camada(sub, f"{origem} [plataformas.{pid}]", "plataforma")
        elif chave in ESQUEMA:
            if not isinstance(valor, dict):
                raise ErroHeranca(f"{origem}: [{chave}] deve ser uma tabela")
            for sub, v in valor.items():
                nome, op = _sem_operador(sub)
                tipo_esperado = ESQUEMA[chave].get(nome)
                if tipo_esperado is None:
                    raise ErroHeranca(f"{origem} [{chave}]: chave desconhecida: {sub}")
                if op and tipo_esperado is not list:
                    raise ErroHeranca(f"{origem} [{chave}]: {op} só vale para listas")
                if op and not isinstance(v, list):
                    raise ErroHeranca(f"{origem} [{chave}]: {sub} deve ser uma lista")
                if not op and not tipo_ok(v, tipo_esperado):
                    # O nome do campo, nunca o valor (pode ser dado real).
                    raise ErroHeranca(f"{origem} [{chave}]: campo {sub} deve ser "
                                      f"{_nome_tipo(tipo_esperado)}")
            if any(f"{n}{SUBSTITUIR}" in valor and n in valor for n in ESQUEMA[chave]):
                raise ErroHeranca(f"{origem} [{chave}]: use a lista OU {SUBSTITUIR}, não os dois")


def _somar(base: list, novos: list) -> list:
    vistos = {normalizar_item(x) for x in base}
    saida = list(base)
    for x in novos:
        n = normalizar_item(x)
        if n not in vistos:
            vistos.add(n)
            saida.append(x)
    return saida


def mesclar(base: dict, camada: dict, nome: str, origens: dict, caminho: tuple = ()) -> dict:
    """Aplica `camada` sobre `base` (sem alterar nenhuma das duas)."""
    saida = copy.deepcopy(base)
    # Operadores primeiro (substituir/remover), depois os valores da camada.
    ordenadas = sorted(camada.items(), key=lambda kv: _sem_operador(kv[0])[1] == "")
    for chave, valor in ordenadas:
        alvo, op = _sem_operador(chave)
        ponto = ".".join(caminho + (alvo,))
        atual = saida.get(alvo)
        if op == SUBSTITUIR:
            saida[alvo] = list(valor)
            origens[ponto] = {normalizar_item(x): nome for x in valor}
        elif op == REMOVER:
            tirar = {normalizar_item(x) for x in valor}
            saida[alvo] = [x for x in (atual or []) if normalizar_item(x) not in tirar]
            itens = origens.get(ponto, {})
            origens[ponto] = {k: v for k, v in itens.items() if k not in tirar}
        elif isinstance(valor, dict):
            if atual is not None and not isinstance(atual, dict):
                raise ErroHeranca(f"{nome}: {ponto} é tabela aqui e valor simples antes")
            saida[alvo] = mesclar(atual or {}, valor, nome, origens, caminho + (alvo,))
        elif isinstance(valor, list):
            if atual is not None and not isinstance(atual, list):
                raise ErroHeranca(f"{nome}: {ponto} é lista aqui e outro tipo antes")
            saida[alvo] = _somar(atual or [], valor)
            itens = origens.setdefault(ponto, {})
            if not isinstance(itens, dict):
                itens = origens[ponto] = {}
            for x in valor:
                itens.setdefault(normalizar_item(x), nome)
        else:
            if isinstance(atual, (dict, list)):
                raise ErroHeranca(f"{nome}: {ponto} é valor simples aqui e tabela/lista antes")
            saida[alvo] = valor
            origens[ponto] = nome
    return saida


def resolver(camadas: list[tuple[str, dict]], plataforma: str | None) -> tuple[dict, dict]:
    """Mescla as camadas na ordem dada, cada uma seguida do seu ajuste @plataforma.

    `camadas` = [(nome, dados_sem_meta), ...] já validadas. Devolve a
    configuração efetiva e, para cada chave, a camada de onde veio.
    """
    efetiva: dict = {}
    origens: dict = {}
    for nome, dados in camadas:
        geral = {k: v for k, v in dados.items() if k != "plataformas"}
        efetiva = mesclar(efetiva, geral, nome, origens)
        ajuste = dados.get("plataformas", {}).get(plataforma) if plataforma else None
        if ajuste:
            efetiva = mesclar(efetiva, ajuste, f"{nome}@{plataforma}", origens)
    return efetiva, origens
