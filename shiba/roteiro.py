"""Roteiro audiovisual em TOML: estrutura e verificações (Incremento 3B).

Modelo:
- `[[cena]]` são SEQUENCIAIS: cobrem a linha do tempo uma depois da outra.
  Sobreposição entre cenas é erro de estrutura; buraco entre cenas é aviso.
- `[[elemento]]` são SIMULTÂNEOS: camadas sobre as cenas (texto na tela,
  legenda, trilha, grafismo, logo, CTA visual, efeito sonoro, locução em off).
  Podem se sobrepor a cenas e entre si à vontade: sobreposição intencional.

Cena sem fala é válida (vídeo só com trilha, motion graphics, B-roll). O que
se pede é que cada cena diga o que se VÊ e de onde vem o SOM (fala, trilha,
ambiente, ou silêncio declarado), por ela mesma ou por um elemento de áudio.

IMPORTANTE: só o TEXTO do roteiro é verificado. O vídeo, a imagem e o áudio
finais não são analisados; uma cena pode estar ótima no papel e diferente
na edição.
"""
from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .config import ErroConfig, validar_id
from .texto import dobrar, padrao_termo

AUDIOS = ("fala", "locucao", "trilha", "trilha_instrumental", "ambiente", "efeitos", "silencio")
TIPOS_ELEMENTO = ("texto_tela", "legenda", "trilha", "grafismo", "logo", "cta_visual",
                  "efeito_sonoro", "locucao")
ELEMENTOS_DE_AUDIO = ("trilha", "efeito_sonoro", "locucao")
ELEMENTOS_DE_TEXTO = ("texto_tela", "legenda", "cta_visual", "locucao")
FORMAS_CTA = ("falada", "texto_tela", "visual", "legenda")

_CHAVES_ROTEIRO = {"titulo", "plataforma", "duracao_alvo_s", "gancho", "mensagem_principal",
                   "termos_mensagem", "cta", "cena", "elemento"}
_CHAVES_CENA = {"id", "inicio_s", "fim_s", "visual", "tipo_visual", "fala", "audio", "texto_tela",
                "nota"}
_CHAVES_ELEMENTO = {"id", "tipo", "inicio_s", "fim_s", "conteudo", "nota"}
_CHAVES_CTA = {"texto", "forma", "cena", "elemento"}
_PALAVRA = re.compile(r"\w+")


@dataclass(frozen=True)
class Cena:
    id: str
    inicio: float
    fim: float
    visual: str
    fala: str = ""
    texto_tela: str = ""
    audio: tuple[str, ...] = ()
    tipo_visual: str = ""

    @property
    def duracao(self) -> float:
        return self.fim - self.inicio


@dataclass(frozen=True)
class Elemento:
    id: str
    tipo: str
    inicio: float
    fim: float
    conteudo: str = ""


@dataclass(frozen=True)
class Cta:
    texto: str
    forma: str
    cena: str = ""
    elemento: str = ""


@dataclass(frozen=True)
class Roteiro:
    plataforma: str
    cenas: tuple[Cena, ...]
    elementos: tuple[Elemento, ...] = ()
    titulo: str = ""
    duracao_alvo: float | None = None
    gancho: str = ""
    mensagem_principal: str = ""
    termos_mensagem: tuple[str, ...] = ()
    cta: Cta | None = None

    @property
    def duracao_total(self) -> float:
        return max((c.fim for c in self.cenas), default=0.0)


def palavras(texto: str) -> int:
    return len(_PALAVRA.findall(texto))


def _desconhecidas(dados: dict, permitidas: set, origem: str) -> None:
    extra = set(dados) - permitidas
    if extra:
        raise ErroConfig(f"{origem}: chave desconhecida: {sorted(extra)[0]}")


def _texto(d: dict, chave: str, origem: str, obrigatorio=False) -> str:
    valor = d.get(chave, "")
    if not isinstance(valor, str):
        raise ErroConfig(f"{origem}: {chave} deve ser texto")
    if obrigatorio and not valor.strip():
        raise ErroConfig(f"{origem}: campo obrigatório ausente ou vazio: {chave}")
    return valor.strip()


def _tempo(d: dict, chave: str, origem: str) -> float:
    valor = d.get(chave)
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ErroConfig(f"{origem}: {chave} deve ser número (segundos)")
    if valor < 0:
        raise ErroConfig(f"{origem}: {chave} não pode ser negativo")
    return float(valor)


def _intervalo(d: dict, origem: str) -> tuple[float, float]:
    inicio, fim = _tempo(d, "inicio_s", origem), _tempo(d, "fim_s", origem)
    if fim <= inicio:
        raise ErroConfig(f"{origem}: fim_s deve ser maior que inicio_s")
    return inicio, fim


def interpretar_roteiro(dados: dict, origem: str = "roteiro") -> Roteiro:
    """Valida a ESTRUTURA (campos, tipos, ids). Os problemas editoriais e de
    coerência ficam para `verificar_roteiro`, que gera achados em vez de erro."""
    _desconhecidas(dados, _CHAVES_ROTEIRO, origem)
    plataforma = validar_id(_texto(dados, "plataforma", origem, True), "plataforma")
    ids: set[str] = set()

    def novo_id(d, local):
        i = validar_id(_texto(d, "id", local, True), "id")
        if i in ids:
            raise ErroConfig(f"{local}: id repetido: {i}")
        ids.add(i)
        return i

    cenas = []
    brutas = dados.get("cena", [])
    if not isinstance(brutas, list):
        raise ErroConfig(f"{origem}: use [[cena]] para cada cena")
    for n, c in enumerate(brutas, 1):
        local = f"{origem} cena #{n}"
        if not isinstance(c, dict):
            raise ErroConfig(f"{local}: formato inválido")
        _desconhecidas(c, _CHAVES_CENA, local)
        inicio, fim = _intervalo(c, local)
        audio = c.get("audio", [])
        if isinstance(audio, str):
            audio = [audio]
        if not isinstance(audio, list) or any(a not in AUDIOS for a in audio):
            raise ErroConfig(f"{local}: audio deve ser lista com valores de {AUDIOS}")
        cenas.append(Cena(novo_id(c, local), inicio, fim, _texto(c, "visual", local),
                          _texto(c, "fala", local), _texto(c, "texto_tela", local),
                          tuple(audio), _texto(c, "tipo_visual", local)))
    elementos = []
    brutos = dados.get("elemento", [])
    if not isinstance(brutos, list):
        raise ErroConfig(f"{origem}: use [[elemento]] para cada elemento")
    for n, e in enumerate(brutos, 1):
        local = f"{origem} elemento #{n}"
        if not isinstance(e, dict):
            raise ErroConfig(f"{local}: formato inválido")
        _desconhecidas(e, _CHAVES_ELEMENTO, local)
        tipo = _texto(e, "tipo", local, True)
        if tipo not in TIPOS_ELEMENTO:
            raise ErroConfig(f"{local}: tipo deve ser um de {TIPOS_ELEMENTO}")
        inicio, fim = _intervalo(e, local)
        elementos.append(Elemento(novo_id(e, local), tipo, inicio, fim, _texto(e, "conteudo", local)))
    cta = None
    if "cta" in dados:
        bruto = dados["cta"]
        if not isinstance(bruto, dict):
            raise ErroConfig(f"{origem}: [cta] deve ser uma tabela")
        _desconhecidas(bruto, _CHAVES_CTA, f"{origem} [cta]")
        forma = _texto(bruto, "forma", f"{origem} [cta]", True)
        if forma not in FORMAS_CTA:
            raise ErroConfig(f"{origem} [cta]: forma deve ser uma de {FORMAS_CTA}")
        cta = Cta(_texto(bruto, "texto", f"{origem} [cta]", True), forma,
                  _texto(bruto, "cena", f"{origem} [cta]"), _texto(bruto, "elemento", f"{origem} [cta]"))
    termos = dados.get("termos_mensagem", [])
    if not isinstance(termos, list) or not all(isinstance(t, str) and t.strip() for t in termos):
        raise ErroConfig(f"{origem}: termos_mensagem deve ser lista de textos não vazios")
    alvo = dados.get("duracao_alvo_s")
    if alvo is not None:
        alvo = _tempo(dados, "duracao_alvo_s", origem)
        if alvo == 0:
            raise ErroConfig(f"{origem}: duracao_alvo_s deve ser positiva")
    return Roteiro(plataforma, tuple(cenas), tuple(elementos), _texto(dados, "titulo", origem),
                   alvo, _texto(dados, "gancho", origem), _texto(dados, "mensagem_principal", origem),
                   tuple(t.strip() for t in termos), cta)


def carregar_roteiro(caminho: Path, rotulo: str | None = None) -> Roteiro:
    nome = rotulo or str(caminho)
    try:
        with Path(caminho).open("rb") as f:
            dados = tomllib.load(f)
    except FileNotFoundError:
        raise ErroConfig(f"roteiro não encontrado: {nome}") from None
    except tomllib.TOMLDecodeError as e:
        raise ErroConfig(f"TOML inválido em {nome}: {e}") from None
    except OSError as e:
        raise ErroConfig(f"não foi possível ler {nome}: {e.strerror}") from None
    return interpretar_roteiro(dados, Path(caminho).name if rotulo is None else rotulo)


def unidades_de_texto(r: Roteiro) -> list[tuple[str, str, float, float]]:
    """Todo texto falado ou exibido: (local, texto, início, fim)."""
    unidades = []
    for c in r.cenas:
        if c.fala:
            unidades.append((f"cena {c.id} · fala", c.fala, c.inicio, c.fim))
        if c.texto_tela:
            unidades.append((f"cena {c.id} · texto na tela", c.texto_tela, c.inicio, c.fim))
    for e in r.elementos:
        if e.conteudo and e.tipo in ELEMENTOS_DE_TEXTO:
            unidades.append((f"elemento {e.id} · {e.tipo}", e.conteudo, e.inicio, e.fim))
    return unidades


def contem(texto: str, termo: str) -> bool:
    return bool(padrao_termo(termo).search(dobrar(texto)))
