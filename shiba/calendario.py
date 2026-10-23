"""Calendário editorial em TOML: estrutura e verificações (Incremento 3C).

O calendário é PLANEJAMENTO: durante as fases iniciais (ideia, planejado,
em produção) uma peça não precisa ter arquivo. A exigência de arquivo depende
do status ([calendario] status_exigem_arquivo).

Status de aprovação (aprovado, agendado, publicado) exigem o papel de quem
aprovou e, quando o cliente ou a peça exige validação normativa, o papel de
quem validou. Isso é um REGISTRO DECLARATIVO, não autenticação: a aprovação
com identidade verificada é o Incremento 4. Nenhuma peça que exija
validação normativa pode constar como aprovada só porque passou nas
verificações técnicas.

Responsáveis são identificadores de papel (ex.: "resp-01"), nunca nomes.
Arquivos citados só têm a EXISTÊNCIA conferida; o conteúdo não é lido aqui.
"""
from __future__ import annotations

import re
import tomllib
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .config import Cliente, ErroConfig
from .regras import AVISO, BLOQUEANTE, INFO, NATUREZAS, NORMATIVA, REVISAO, Achado
from .verificar import _achado_para_dict, exigencias_aprovacao, ordenar, status_maximo, resumo_de

STATUS = ("ideia", "planejado", "em_producao", "em_revisao", "pronto", "aprovado", "agendado",
          "publicado", "cancelado")
STATUS_APROVACAO = ("aprovado", "agendado", "publicado")
STATUS_ENCERRADOS = ("publicado", "cancelado")
ESQUEMA_CALENDARIO = "shiba.calendario/0.1"

_CHAVES = {"titulo", "inicio", "fim", "peca"}
_CHAVES_PECA = {"id", "data", "hora", "plataforma", "formato", "responsavel", "status", "arquivo",
                "pilar", "gancho_formula", "aprovado_por", "validado_por",
                "exige_validacao_normativa", "titulo", "nota"}
_HORA = re.compile(r"([01]\d|2[0-3]):[0-5]\d")
_PAPEL = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")


@dataclass(frozen=True)
class Peca:
    id: str
    data: date
    plataforma: str
    responsavel: str
    status: str
    hora: str = ""
    formato: str = ""
    arquivo: str = ""
    pilar: str = ""
    gancho_formula: str = ""
    aprovado_por: str = ""
    validado_por: str = ""
    exige_validacao_normativa: bool = False


@dataclass(frozen=True)
class Calendario:
    inicio: date
    fim: date
    pecas: tuple[Peca, ...]
    titulo: str = ""


def _data(valor, origem: str, campo: str) -> date:
    if isinstance(valor, date) and not hasattr(valor, "hour"):
        return valor
    if isinstance(valor, str):
        try:
            return date.fromisoformat(valor)
        except ValueError:
            pass
    raise ErroConfig(f"{origem}: {campo} deve ser uma data AAAA-MM-DD")


def _texto(d: dict, campo: str, origem: str) -> str:
    valor = d.get(campo, "")
    if not isinstance(valor, str):
        raise ErroConfig(f"{origem}: {campo} deve ser texto")
    return valor.strip()


def interpretar_calendario(dados: dict, origem: str = "calendario") -> Calendario:
    """Valida tipos e campos conhecidos. Problemas de conteúdo viram achados."""
    extra = set(dados) - _CHAVES
    if extra:
        raise ErroConfig(f"{origem}: chave desconhecida: {sorted(extra)[0]}")
    for campo in ("inicio", "fim"):
        if campo not in dados:
            raise ErroConfig(f"{origem}: campo obrigatório ausente: {campo}")
    inicio, fim = _data(dados["inicio"], origem, "inicio"), _data(dados["fim"], origem, "fim")
    if fim < inicio:
        raise ErroConfig(f"{origem}: fim anterior ao inicio")
    brutas = dados.get("peca", [])
    if not isinstance(brutas, list):
        raise ErroConfig(f"{origem}: use [[peca]] para cada peça")
    pecas = []
    for n, p in enumerate(brutas, 1):
        local = f"{origem} peça #{n}"
        if not isinstance(p, dict):
            raise ErroConfig(f"{local}: formato inválido")
        extra = set(p) - _CHAVES_PECA
        if extra:
            raise ErroConfig(f"{local}: chave desconhecida: {sorted(extra)[0]}")
        if "data" not in p:
            raise ErroConfig(f"{local}: campo obrigatório ausente: data")
        exige = p.get("exige_validacao_normativa", False)
        if not isinstance(exige, bool):
            raise ErroConfig(f"{local}: exige_validacao_normativa deve ser true ou false")
        pecas.append(Peca(
            id=_texto(p, "id", local), data=_data(p["data"], local, "data"),
            plataforma=_texto(p, "plataforma", local), responsavel=_texto(p, "responsavel", local),
            status=_texto(p, "status", local), hora=_texto(p, "hora", local),
            formato=_texto(p, "formato", local), arquivo=_texto(p, "arquivo", local),
            pilar=_texto(p, "pilar", local), gancho_formula=_texto(p, "gancho_formula", local),
            aprovado_por=_texto(p, "aprovado_por", local), validado_por=_texto(p, "validado_por", local),
            exige_validacao_normativa=exige,
        ))
    return Calendario(inicio, fim, tuple(pecas), _texto(dados, "titulo", origem))


def carregar_calendario(caminho: Path, rotulo: str | None = None) -> Calendario:
    nome = rotulo or str(caminho)
    try:
        with Path(caminho).open("rb") as f:
            dados = tomllib.load(f)
    except FileNotFoundError:
        raise ErroConfig(f"calendário não encontrado: {nome}") from None
    except tomllib.TOMLDecodeError as e:
        raise ErroConfig(f"TOML inválido em {nome}: {e}") from None
    except OSError as e:
        raise ErroConfig(f"não foi possível ler {nome}: {e.strerror}") from None
    return interpretar_calendario(dados, rotulo or Path(caminho).name)


def caminho_do_arquivo(base: Path | None, arquivo: str) -> Path | None:
    if not arquivo:
        return None
    p = Path(arquivo).expanduser()
    return p if p.is_absolute() or base is None else base / p


def _a(regra, severidade, mensagem, peca: str = "", natureza: str = "tecnica", sugestao="") -> Achado:
    return Achado(f"calendario_{regra}", severidade, mensagem, natureza=natureza,
                  local=f"peça {peca}" if peca else "", sugestao=sugestao)


def verificar_calendario(cal: Calendario, cliente: Cliente, plataformas_validas: set[str],
                         hoje: date | None = None, base_arquivos: Path | None = None) -> dict:
    hoje = hoje or date.today()
    cfg = cliente.secoes.get("calendario", {})
    equipe = cliente.secoes.get("equipe", {})
    exige_cliente = cliente.secoes.get("revisao", {}).get("exige_validacao_normativa", False)
    papeis = set(equipe.get("papeis", []))
    aprovadores = set(equipe.get("aprovadores", []))
    validadores = set(equipe.get("validadores_normativos", []))
    exigem_arquivo = set(cfg.get("status_exigem_arquivo", []))
    achados: list[Achado] = []
    if not papeis:
        achados.append(_a("equipe", AVISO, "equipe do cliente sem papéis configurados; "
                                           "responsáveis não puderam ser conferidos"))
    ids = Counter(p.id for p in cal.pecas)
    for pid, n in ids.items():
        if not pid:
            achados.append(_a("peca_incompleta", BLOQUEANTE, "peça sem id"))
        elif n > 1:
            achados.append(_a("id_repetido", BLOQUEANTE, f"id usado {n} vezes", pid))
    for p in cal.pecas:
        pid = p.id or "?"
        if p.status not in STATUS:
            # Continua: os demais problemas da peça também precisam aparecer.
            achados.append(_a("status", BLOQUEANTE, f"status desconhecido: {p.status or '(vazio)'}",
                              pid, sugestao=f"Use um de: {', '.join(STATUS)}."))
        elif p.status == "cancelado":
            continue
        if not cal.inicio <= p.data <= cal.fim:
            achados.append(_a("data", AVISO, f"data {p.data.isoformat()} fora do período do calendário", pid))
        if p.data < hoje and p.status not in STATUS_ENCERRADOS:
            achados.append(_a("data", AVISO, f"a data já passou e a peça está como '{p.status}'", pid))
        if p.status == "publicado" and p.data > hoje:
            achados.append(_a("data", AVISO, "marcada como publicada com data futura", pid))
        if p.hora and not _HORA.fullmatch(p.hora):
            achados.append(_a("data", BLOQUEANTE, "hora deve estar no formato HH:MM", pid))
        if not p.plataforma:
            achados.append(_a("peca_incompleta", BLOQUEANTE, "peça sem plataforma", pid))
        elif p.plataforma not in plataformas_validas:
            achados.append(_a("plataforma", BLOQUEANTE, f"plataforma sem perfil: {p.plataforma}", pid))
        if not p.responsavel:
            achados.append(_a("responsavel", BLOQUEANTE, "peça sem responsável", pid))
        elif not _PAPEL.fullmatch(p.responsavel):
            achados.append(_a("responsavel", BLOQUEANTE,
                              "responsável deve ser um identificador de papel (a-z, 0-9, hífen), "
                              "nunca um nome de pessoa", pid))
        elif papeis and p.responsavel not in papeis:
            achados.append(_a("responsavel", BLOQUEANTE, f"papel não pertence à equipe: {p.responsavel}", pid))
        alvo = caminho_do_arquivo(base_arquivos, p.arquivo)
        if p.status in exigem_arquivo and alvo is None:
            achados.append(_a("peca_incompleta", BLOQUEANTE,
                              f"status '{p.status}' exige o arquivo da peça", pid))
        elif alvo is not None and not alvo.is_file():
            achados.append(_a("arquivo", BLOQUEANTE if p.status in exigem_arquivo else AVISO,
                              "arquivo indicado não encontrado", pid))
        if p.status in STATUS_APROVACAO:
            if not p.aprovado_por:
                achados.append(_a("aprovacao", BLOQUEANTE,
                                  f"status '{p.status}' sem registro de quem aprovou (aprovado_por)", pid))
            elif aprovadores and p.aprovado_por not in aprovadores:
                achados.append(_a("aprovacao", BLOQUEANTE,
                                  f"aprovado_por não é um papel aprovador: {p.aprovado_por}", pid))
            if exige_cliente or p.exige_validacao_normativa:
                if not p.validado_por:
                    achados.append(_a("validacao_normativa", BLOQUEANTE,
                                      f"peça exige validação normativa: status '{p.status}' não pode "
                                      "ser usado sem o registro do responsável competente "
                                      "(validado_por). Passar nas verificações técnicas não basta.",
                                      pid, NORMATIVA))
                elif p.validado_por not in validadores:
                    achados.append(_a("validacao_normativa", BLOQUEANTE,
                                      f"validado_por não é um papel validador normativo: {p.validado_por}",
                                      pid, NORMATIVA))
        elif exige_cliente or p.exige_validacao_normativa:
            achados.append(_a("validacao_normativa", INFO,
                              "peça exigirá validação normativa antes de qualquer aprovação", pid,
                              NORMATIVA))
    ativas = [p for p in cal.pecas if p.status in STATUS and p.status != "cancelado"]
    horarios = Counter((p.plataforma, p.data, p.hora) for p in ativas if p.hora)
    for (plataforma, dia, hora), n in horarios.items():
        if n > 1:
            achados.append(_a("conflito", AVISO, f"{n} peças em {plataforma} no mesmo horário "
                                                 f"({dia.isoformat()} {hora})"))
    maximo = cfg.get("max_pecas_por_responsavel_dia")
    if maximo:
        carga = Counter((p.responsavel, p.data) for p in ativas if p.responsavel)
        for (resp, dia), n in carga.items():
            if n > maximo:
                achados.append(_a("carga", AVISO, f"{resp} com {n} peças em {dia.isoformat()} "
                                                  f"(referência configurada: até {maximo})"))
    pilares = cfg.get("pilares", [])
    if pilares:
        usados = {p.pilar for p in ativas}
        for p in ativas:
            if p.pilar and p.pilar not in pilares:
                achados.append(_a("pilar", AVISO, f"pilar fora da lista do cliente: {p.pilar}", p.id,
                                  REVISAO))
        for pilar in pilares:
            if pilar not in usados:
                achados.append(_a("pilar", INFO, f"nenhuma peça no pilar '{pilar}' no período",
                                  natureza=REVISAO))
    por_dia = sorted((p for p in ativas if p.gancho_formula), key=lambda p: p.data)
    for ant, prox in zip(por_dia, por_dia[1:]):
        if ant.gancho_formula == prox.gancho_formula and (prox.data - ant.data).days == 1:
            achados.append(_a("variedade", INFO, f"mesma fórmula de gancho em dias seguidos: "
                                                 f"{prox.gancho_formula}", prox.id, REVISAO))
    achados = ordenar(achados)
    dicts = [_achado_para_dict("", a) for a in achados]
    resumo = resumo_de(achados)
    return {
        "esquema": ESQUEMA_CALENDARIO,
        "cliente": cliente.id,
        "periodo": {"inicio": cal.inicio.isoformat(), "fim": cal.fim.isoformat()},
        "data_referencia": hoje.isoformat(),
        "resultado": "bloqueado" if resumo[BLOQUEANTE] else "passou",
        "requer_revisao_humana": resumo[AVISO] > 0,
        "requer_validacao_normativa": any(a.natureza == NORMATIVA for a in achados),
        "resumo": resumo,
        "por_natureza": {n: sum(a.natureza == n for a in achados) for n in NATUREZAS},
        "metricas": {
            "pecas": len(cal.pecas),
            "por_status": dict(sorted(Counter(p.status for p in cal.pecas).items())),
            "por_plataforma": dict(sorted(Counter(p.plataforma for p in cal.pecas).items())),
        },
        "exigencias_aprovacao": exigencias_aprovacao(dicts),
        "status_maximo": status_maximo(exigencias_aprovacao(dicts)),
        "limites_da_verificacao": [
            "O calendário é verificado como planejamento. Arquivos citados só têm a existência "
            "conferida; o conteúdo das peças não foi analisado aqui (use verificar/roteiro).",
            "aprovado_por e validado_por são registros declarativos, não autenticação "
            "(Incremento 4).",
        ],
        "achados": dicts,
    }
