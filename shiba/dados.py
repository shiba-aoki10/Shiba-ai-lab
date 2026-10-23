"""Isolamento de dados reais: fora de qualquer repositório Git e fora do código.

Dados reais de clientes vivem num diretório próprio (`--dados DIR` ou a
variável SHIBA_DADOS). Antes de ler ou gravar qualquer coisa ligada a eles, o
motor confere que o caminho NÃO está:
- dentro de um repositório Git (procura `.git`, pasta ou arquivo, em todas as
  pastas acima, e também repositórios "nus"), tanto no caminho como escrito
  quanto no caminho real (links simbólicos resolvidos);
- dentro do diretório do código do Shiba, mesmo que ele não tenha `.git`;
- sob GIT_DIR/GIT_WORK_TREE definidos no ambiente (que fazem o Git tratar
  pastas arbitrárias como repositório).

A checagem é conservadora: se não der para ler uma pasta, recusa.
As mensagens de erro usam rótulos ("diretório de dados"), não o conteúdo.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path

from .config import RAIZ, ErroConfig

VARIAVEL = "SHIBA_DADOS"


class ErroIsolamento(ErroConfig):
    """Uso inseguro de dados reais (dentro do Git, do código, ou indeterminado)."""


def _parece_repo_nu(pasta: Path) -> bool:
    return (pasta / "HEAD").is_file() and (pasta / "objects").is_dir() and (pasta / "refs").is_dir()


def _formas(caminho: Path) -> list[Path]:
    """O caminho como escrito (normalizado, sem '..') e o caminho real (links resolvidos)."""
    lexico = Path(os.path.abspath(caminho))
    real = Path(os.path.realpath(caminho))
    return [lexico] if lexico == real else [lexico, real]


def repositorio_que_contem(caminho: Path) -> Path | None:
    """Pasta do repositório Git que contém `caminho`, ou None.

    Levanta ErroIsolamento se alguma pasta não puder ser inspecionada.
    """
    for forma in _formas(caminho):
        for pasta in (forma, *forma.parents):
            # Sem permissão de acesso, `lexists` diria "não existe" sem ter olhado.
            if pasta.is_dir() and not os.access(pasta, os.X_OK):
                raise ErroIsolamento(
                    "não foi possível inspecionar uma pasta do caminho; "
                    "por segurança, o uso foi recusado")
            if os.path.lexists(pasta / ".git") or _parece_repo_nu(pasta):
                return pasta
    return None


def garantir_fora_do_git(caminho: Path, rotulo: str, *, raiz_codigo: Path = RAIZ,
                         ambiente: dict | None = None) -> None:
    """Recusa `caminho` se ele estiver num repositório Git ou no código do Shiba."""
    ambiente = os.environ if ambiente is None else ambiente
    for variavel in ("GIT_DIR", "GIT_WORK_TREE"):
        if ambiente.get(variavel):
            raise ErroIsolamento(
                f"{variavel} está definida no ambiente; com ela o Git pode tratar "
                f"qualquer pasta como repositório. Remova-a para usar {rotulo}")
    if repositorio_que_contem(caminho) is not None:
        raise ErroIsolamento(
            f"{rotulo} está dentro de um repositório Git (nesta pasta ou numa pasta "
            "acima). Dados reais precisam ficar fora de qualquer repositório")
    raiz = Path(os.path.realpath(raiz_codigo))
    for forma in _formas(caminho) + [Path(os.path.realpath(caminho))]:
        if forma == raiz or raiz in forma.parents:
            raise ErroIsolamento(f"{rotulo} está dentro do diretório do código do Shiba")


def resolver_dir_dados(valor: str | None, ambiente: dict | None = None) -> Path:
    """Diretório de dados a partir de `--dados DIR` ou da variável SHIBA_DADOS."""
    ambiente = os.environ if ambiente is None else ambiente
    bruto = valor or ambiente.get(VARIAVEL, "")
    if not bruto.strip():
        raise ErroIsolamento(f"informe o diretório em --dados ou defina {VARIAVEL}")
    return Path(bruto).expanduser()


def preparar_dir_dados(caminho: Path, *, raiz_codigo: Path = RAIZ,
                       ambiente: dict | None = None) -> Path:
    """Valida o diretório de dados reais e devolve o caminho real."""
    if not caminho.is_dir():
        raise ErroIsolamento("o diretório de dados não existe ou não é uma pasta")
    garantir_fora_do_git(caminho, "o diretório de dados", raiz_codigo=raiz_codigo, ambiente=ambiente)
    return Path(os.path.realpath(caminho))


def permissoes_abertas(caminho: Path) -> bool:
    """Verdadeiro se outros usuários do sistema podem ler ou entrar na pasta (POSIX)."""
    if os.name != "posix":
        return False
    return bool(caminho.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO))
