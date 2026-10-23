"""Serialização canônica e hashes que amarram decisões a conteúdo e configuração.

Canônico = JSON com chaves ordenadas, sem espaços, UTF-8, datas em ISO 8601,
tuplas como listas. O mesmo objeto sempre gera os mesmos bytes, em qualquer
máquina.

Dependências de decisão (o que entra em cada hash; ver INCREMENTO-4.md):
- hash_conteudo: bytes EXATOS de cada arquivo da peça (texto e fatos da peça);
- hash_config: configuração efetiva do cliente na plataforma, perfil da
  plataforma, registro COMPLETO de cada fato que influenciou a verificação
  (todo fato ligado a qualquer vínculo, com ou sem alerta), bytes dos léxicos
  em uso e versões do motor e dos esquemas;
- hash_laudo: resultado da verificação (achados relevantes e exigências),
  SEM a data, recalculado a cada avaliação.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import date


def _padrao(obj):
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, (set, frozenset)):
        return sorted(obj)
    if is_dataclass(obj):
        return asdict(obj)
    raise TypeError(f"tipo não serializável: {type(obj).__name__}")


def canonico(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                      default=_padrao).encode("utf-8")


def sha256(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def hash_objeto(obj) -> str:
    return sha256(canonico(obj))


def hash_conteudo(arquivos: list[tuple[str, bytes]]) -> str:
    """Hash dos bytes exatos. `arquivos` = [(papel do arquivo, bytes)], ex.: ("peca", b"...")."""
    return hash_objeto(sorted((rotulo, sha256(b)) for rotulo, b in arquivos))


CAMPOS_ACHADO = ("regra", "severidade", "natureza", "local", "trecho", "mensagem")


def resumo_do_laudo(laudo: dict) -> dict:
    """Parte do laudo que expressa a DECISÃO, sem data (que muda todo dia)."""
    return {
        "esquema": laudo.get("esquema"),
        "resultado": laudo.get("resultado"),
        "exigencias": laudo.get("exigencias_aprovacao", []),
        "achados": [{c: a.get(c, "") for c in CAMPOS_ACHADO} for a in laudo.get("achados", [])],
    }


def hash_laudo(laudo: dict) -> str:
    return hash_objeto(resumo_do_laudo(laudo))


def id_do_achado(achado: dict) -> str:
    """Identificador estável de um achado (para reconhecer avisos)."""
    return hash_objeto({c: achado.get(c, "") for c in CAMPOS_ACHADO})[:12]
