"""API do fluxo de aprovação e liberação (Incremento 4C).

Funções independentes de interface, chamadas pela CLI e, no futuro, por
qualquer outra interface. Todas:
- usam um DIRETÓRIO DE ESTADO fora de qualquer repositório Git (também para
  clientes fictícios), onde ficam cópias das versões, o registro encadeado e
  os pacotes liberados;
- fazem leitura e escrita do registro SOB TRAVA, para não haver corrida entre
  verificação, decisão e liberação;
- falham fechado quando a integridade não pode ser confirmada.

Decisões HUMANAS (cadastrar ou revogar identidade, reconhecer aviso,
aprovar, rejeitar, validar ou recusar normativamente, liberar) passam por
`_exigir_pessoa`:
- `simulacao=True` só é aceito para cliente FICTÍCIO; os eventos ficam
  marcados e o pacote sai como SIMULAÇÃO. É assim que testes e
  demonstrações (inclusive feitos por IA) exercitam o fluxo;
- sem simulação, a decisão é RECUSADA quando o ambiente indica um agente de
  IA (CLAUDECODE, CLAUDE_CODE_ENTRYPOINT, AI_AGENT).
Isso é uma barreira de PROCESSO, não criptográfica: quem controla o ambiente
consegue contorná-la (removendo as variáveis ou chamando funções internas).
A confirmação no terminal (digitar o início do hash) também não é proteção
criptográfica. Prova de quem decidiu só virá com assinatura (Incremento 4D),
e mesmo ela prova posse de chave, não identidade civil.
"""
from __future__ import annotations

import json
import os
import secrets
import shutil
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from .api import Origem, contexto, origem, proteger
from .aprovacao import (
    APROVACAO_EDITORIAL,
    ATOS,
    ErroAprovacao,
    avisos_do_laudo,
    calcular_estado,
    papeis_do_ato,
    politica_de,
    validar_pedido,
    versao_atual,
)
from .auditoria import ErroIntegridade, Registro, conferir_topo, exportar_topo, trava
from .config import DIR_PLATAFORMAS, ErroConfig, carregar_cliente, plataformas_disponiveis
from .dados import garantir_fora_do_git
from .dependencias import TIPOS, Avaliacao, avaliar, texto_da_legenda
from .fontes import gerar_fontes_md
from .hashes import canonico, sha256
from .identidades import ErroIdentidade, identidades, validar_cadastro

MARCADORES_DE_AGENTE = ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "AI_AGENT")
ESQUEMA_LIBERACAO = "shiba.liberacao/0.1"
_EXTENSOES = {"legenda": "md", "roteiro": "toml"}


@dataclass(frozen=True)
class Ambiente:
    estado: Path
    origem: Origem
    dir_plataformas: Path = DIR_PLATAFORMAS


def abrir(estado: Path | None = None, dados: str | None = None, dir_clientes: Path | None = None,
          dir_plataformas: Path = DIR_PLATAFORMAS) -> Ambiente:
    """Prepara o ambiente. O diretório de estado SEMPRE fica fora do Git (D4)."""
    o = origem(dados, dir_clientes)
    if o.real:
        if estado is not None:
            raise ErroConfig("com --dados, o estado é o próprio diretório de dados; não use --estado")
        estado = o.dir_clientes.parent
    if estado is None:
        raise ErroConfig("informe --estado DIR (fora de qualquer repositório Git)")
    estado = Path(estado)
    if not estado.is_dir():
        raise ErroConfig("o diretório de estado não existe ou não é uma pasta")
    garantir_fora_do_git(estado, "o diretório de estado")
    return Ambiente(Path(os.path.realpath(estado)), o, dir_plataformas)


def _cliente(amb: Ambiente, cliente_id: str, plataforma: str | None = None):
    return carregar_cliente(cliente_id, amb.origem.dir_clientes, plataforma=plataforma,
                            plataformas_validas=plataformas_disponiveis(amb.dir_plataformas),
                            **amb.origem.opcoes)


def _aceita_simulacao(amb: Ambiente, cliente) -> bool:
    return not amb.origem.real and cliente.ficticio


def _exigir_pessoa(amb: Ambiente, cliente, simulacao: bool, ambiente: dict | None = None) -> None:
    if simulacao:
        if not _aceita_simulacao(amb, cliente):
            raise ErroAprovacao("simulação só é aceita para cliente fictício")
        return
    env = os.environ if ambiente is None else ambiente
    if any(env.get(v) for v in MARCADORES_DE_AGENTE):
        raise ErroAprovacao("decisões humanas não podem ser executadas por um agente de IA em nome "
                            "de uma pessoa (barreira de processo, não criptográfica); use "
                            "--simulacao com cliente fictício para testes e demonstrações")


def _pasta_versao(amb: Ambiente, cliente_id: str, peca: str, versao: int) -> Path:
    return amb.estado / "pecas" / cliente_id / peca / f"v{versao}"


def _validar_peca(peca: str) -> str:
    from .config import validar_id
    return validar_id(peca, "peça")


def _avaliar_atual(amb: Ambiente, cliente_id: str, entradas: list[dict], peca: str,
                   hoje: date | None) -> tuple[dict, Avaliacao, object]:
    """Lê a cópia guardada da versão atual, confere seus bytes e reavalia AGORA."""
    v = versao_atual(entradas, peca)
    if v is None:
        raise ErroAprovacao("peça não registrada")
    pasta = _pasta_versao(amb, cliente_id, peca, v["versao"])
    arquivos = {}
    for rotulo, esperado in v["arquivos"].items():
        nome = f"peca.{_EXTENSOES[v['tipo']]}" if rotulo == "peca" else "fatos_peca.toml"
        try:
            dados = (pasta / nome).read_bytes()
        except OSError:
            raise ErroIntegridade("cópia da versão ausente ou ilegível") from None
        if sha256(dados) != esperado:
            raise ErroIntegridade("cópia da versão alterada depois do registro")
        arquivos[rotulo] = dados
    ctx = contexto(cliente_id, v["plataforma"], amb.origem, dir_plataformas=amb.dir_plataformas,
                   fatos_peca=(pasta / "fatos_peca.toml") if "fatos_peca" in arquivos else None)
    aval = avaliar(v["tipo"], arquivos["peca"], arquivos.get("fatos_peca"), ctx.cliente, ctx.fatos,
                   ctx.plataforma, hoje)
    return v, aval, (ctx, arquivos)


def _estado(amb, cliente, entradas, peca, aval):
    return calcular_estado(entradas, peca, aval, politica_de(cliente), _aceita_simulacao(amb, cliente))


# ---- identidades ----------------------------------------------------------

def cadastrar_identidade(amb: Ambiente, cliente_id: str, identidade: str, papeis: list[str],
                         processo: str, cadastrada_por: str, simulacao: bool = False,
                         ambiente: dict | None = None) -> dict:
    cliente = _cliente(amb, cliente_id)
    _exigir_pessoa(amb, cliente, simulacao, ambiente)
    pol = politica_de(cliente)
    reg = Registro(amb.estado, cliente_id)
    with trava(reg.trava):
        try:
            validar_cadastro(identidades(reg.ler()), identidade, list(papeis), processo,
                             cadastrada_por, set(pol.papeis), set(pol.cadastradores))
        except ErroIdentidade as e:
            raise ErroAprovacao(str(e)) from None
        return reg.anexar_sem_trava("identidade_cadastrada", {
            "identidade": identidade, "papeis": list(papeis), "processo": processo.strip(),
            "cadastrada_por": cadastrada_por, "simulacao": simulacao})


def revogar_identidade(amb: Ambiente, cliente_id: str, identidade: str, revogada_por: str,
                       motivo: str, simulacao: bool = False, ambiente: dict | None = None) -> dict:
    cliente = _cliente(amb, cliente_id)
    _exigir_pessoa(amb, cliente, simulacao, ambiente)
    pol = politica_de(cliente)
    reg = Registro(amb.estado, cliente_id)
    with trava(reg.trava):
        ids = identidades(reg.ler())
        alvo, quem = ids.get(identidade), ids.get(revogada_por)
        if alvo is None or not alvo.ativa:
            raise ErroAprovacao("identidade inexistente ou já revogada")
        if quem is None or not quem.ativa or not set(quem.papeis) & pol.cadastradores:
            raise ErroAprovacao("revogada_por precisa ser uma identidade ativa com papel cadastrador")
        if not motivo.strip():
            raise ErroAprovacao("informe o motivo da revogação")
        return reg.anexar_sem_trava("identidade_revogada", {
            "identidade": identidade, "revogada_por": revogada_por, "motivo": motivo.strip(),
            "simulacao": simulacao})


# ---- versões, verificação e envio (atos do autor, não decisões) ------------

def registrar_versao(amb: Ambiente, cliente_id: str, peca: str, arquivo: Path, tipo: str,
                     autor: str, plataforma: str | None = None, fatos_peca: Path | None = None,
                     hoje: date | None = None) -> dict:
    """Guarda uma cópia imutável dos bytes e registra a nova versão (zera aprovações)."""
    _validar_peca(peca)
    if tipo not in TIPOS:
        raise ErroConfig(f"tipo deve ser um de {TIPOS}")
    proteger(amb.origem, arquivo, "o arquivo da peça")
    proteger(amb.origem, fatos_peca, "o arquivo de fatos da peça")
    try:
        bytes_peca = Path(arquivo).read_bytes()
        bytes_fatos = Path(fatos_peca).read_bytes() if fatos_peca else None
    except OSError as e:
        raise ErroConfig(f"não foi possível ler a peça: {e.strerror}") from None
    if tipo == "roteiro":
        import tomllib
        try:
            plataforma = tomllib.loads(texto_da_legenda(bytes_peca)).get("plataforma")
        except tomllib.TOMLDecodeError as e:
            raise ErroConfig(f"roteiro inválido: {e}") from None
    if not plataforma:
        raise ErroConfig("informe a plataforma da peça")
    ctx = contexto(cliente_id, plataforma, amb.origem, dir_plataformas=amb.dir_plataformas,
                   fatos_peca=fatos_peca)
    aval = avaliar(tipo, bytes_peca, bytes_fatos, ctx.cliente, ctx.fatos, ctx.plataforma, hoje)
    pol = politica_de(ctx.cliente)
    reg = Registro(amb.estado, cliente_id)
    with trava(reg.trava):
        entradas = reg.ler()
        ident = identidades(entradas).get(autor)
        if ident is None or not ident.ativa or not set(ident.papeis) & pol.autores:
            raise ErroAprovacao("autor precisa ser uma identidade ativa com papel de autor")
        anterior = versao_atual(entradas, peca)
        versao = 1 if anterior is None else anterior["versao"] + 1
        pasta = _pasta_versao(amb, cliente_id, peca, versao)
        pasta.mkdir(parents=True, exist_ok=False)
        (pasta / f"peca.{_EXTENSOES[tipo]}").write_bytes(bytes_peca)
        arquivos = {"peca": sha256(bytes_peca)}
        if bytes_fatos is not None:
            (pasta / "fatos_peca.toml").write_bytes(bytes_fatos)
            arquivos["fatos_peca"] = sha256(bytes_fatos)
        return reg.anexar_sem_trava("versao_registrada", {
            "peca": peca, "versao": versao, "tipo": tipo, "plataforma": plataforma, "autor": autor,
            "hash_conteudo": aval.hash_conteudo, "arquivos": arquivos,
            "simulacao": _aceita_simulacao(amb, ctx.cliente) and ctx.cliente.ficticio})


def verificar_versao(amb: Ambiente, cliente_id: str, peca: str, hoje: date | None = None) -> dict:
    cliente = _cliente(amb, cliente_id)
    reg = Registro(amb.estado, cliente_id)
    with trava(reg.trava):
        entradas = reg.ler()
        v, aval, _ = _avaliar_atual(amb, cliente_id, entradas, peca, hoje)
        reg.anexar_sem_trava("verificacao", {
            "peca": peca, "versao": v["versao"], **aval.hashes, "resultado": aval.laudo["resultado"],
            "exigencias": aval.laudo["exigencias_aprovacao"], "fatos_influentes": list(aval.fatos_influentes),
            "data_referencia": (hoje or date.today()).isoformat()})
        return {"laudo": aval.laudo, "estado": _estado(amb, cliente, reg.ler(), peca, aval)}


def enviar_para_revisao(amb: Ambiente, cliente_id: str, peca: str, identidade: str,
                        hoje: date | None = None) -> dict:
    cliente = _cliente(amb, cliente_id)
    reg = Registro(amb.estado, cliente_id)
    with trava(reg.trava):
        entradas = reg.ler()
        v, aval, _ = _avaliar_atual(amb, cliente_id, entradas, peca, hoje)
        estado = _estado(amb, cliente, entradas, peca, aval)
        if estado["estado"] != "verificado":
            raise ErroAprovacao(f"a peça está em '{estado['estado']}'; só uma peça verificada é enviada")
        ident = identidades(entradas).get(identidade)
        if ident is None or not ident.ativa or not set(ident.papeis) & politica_de(cliente).autores:
            raise ErroAprovacao("quem envia precisa ser uma identidade ativa com papel de autor")
        reg.anexar_sem_trava("enviada", {"peca": peca, "versao": v["versao"], **aval.hashes,
                                         "identidade": identidade})
        return _estado(amb, cliente, reg.ler(), peca, aval)


# ---- decisões humanas -------------------------------------------------------

def reconhecer_aviso(amb: Ambiente, cliente_id: str, peca: str, aviso: str, identidade: str,
                     papel: str, justificativa: str, hashes_vistos: dict, simulacao: bool = False,
                     hoje: date | None = None, ambiente: dict | None = None) -> dict:
    cliente = _cliente(amb, cliente_id)
    _exigir_pessoa(amb, cliente, simulacao, ambiente)
    pol = politica_de(cliente)
    reg = Registro(amb.estado, cliente_id)
    with trava(reg.trava):
        entradas = reg.ler()
        v, aval, _ = _avaliar_atual(amb, cliente_id, entradas, peca, hoje)
        if hashes_vistos != aval.hashes:
            raise ErroAprovacao("a versão, a configuração ou o laudo mudaram desde que foram exibidos")
        if aviso not in avisos_do_laudo(aval.laudo):
            raise ErroAprovacao("aviso inexistente no laudo atual")
        ident = identidades(entradas).get(identidade)
        if ident is None or not ident.ativa or papel not in ident.papeis or papel not in pol.aprovadores:
            raise ErroAprovacao("só um revisor ativo, com o papel, reconhece avisos")
        if pol.revisao_independente and identidade == v["autor"]:
            raise ErroAprovacao("o autor não reconhece avisos da própria peça (revisão independente)")
        if not justificativa.strip():
            raise ErroAprovacao("informe a justificativa do reconhecimento")
        reg.anexar_sem_trava("aviso_reconhecido", {
            "peca": peca, "versao": v["versao"], **aval.hashes, "aviso": aviso, "identidade": identidade,
            "papel": papel, "nivel": "declarativa", "justificativa": justificativa.strip(),
            "simulacao": simulacao})
        return _estado(amb, cliente, reg.ler(), peca, aval)


def decidir(amb: Ambiente, cliente_id: str, peca: str, ato: str, identidade: str, papel: str,
            justificativa: str, hashes_vistos: dict, simulacao: bool = False,
            hoje: date | None = None, ambiente: dict | None = None) -> dict:
    """Aprovação ou rejeição editorial; validação ou recusa normativa."""
    if ato not in ATOS:
        raise ErroAprovacao(f"ato deve ser um de {ATOS}")
    cliente = _cliente(amb, cliente_id)
    _exigir_pessoa(amb, cliente, simulacao, ambiente)
    if ato != APROVACAO_EDITORIAL and ato.startswith(("rejeicao", "recusa")) and not justificativa.strip():
        raise ErroAprovacao("rejeição e recusa exigem justificativa")
    reg = Registro(amb.estado, cliente_id)
    with trava(reg.trava):
        entradas = reg.ler()
        v, aval, _ = _avaliar_atual(amb, cliente_id, entradas, peca, hoje)
        try:
            validar_pedido(entradas, peca, ato, identidade, papel, hashes_vistos, aval,
                           politica_de(cliente), _aceita_simulacao(amb, cliente))
        except ErroAprovacao as e:
            reg.anexar_sem_trava("tentativa_recusada", {"peca": peca, "versao": v["versao"], "ato": ato,
                                                        "identidade": identidade, "motivo": str(e)})
            raise
        reg.anexar_sem_trava("decisao", {
            "peca": peca, "versao": v["versao"], **aval.hashes, "ato": ato, "identidade": identidade,
            "papel": papel, "nivel": "declarativa", "justificativa": justificativa.strip(),
            "simulacao": simulacao})
        return _estado(amb, cliente, reg.ler(), peca, aval)


# ---- consulta ---------------------------------------------------------------

def status(amb: Ambiente, cliente_id: str, peca: str, hoje: date | None = None,
           arquivo: Path | None = None) -> dict:
    """Estado derivado. Falha fechada: integridade não confirmada nunca é 'aprovado'."""
    cliente = _cliente(amb, cliente_id)
    reg = Registro(amb.estado, cliente_id)
    try:
        with trava(reg.trava):
            entradas = reg.ler()
            v, aval, (_, arquivos) = _avaliar_atual(amb, cliente_id, entradas, peca, hoje)
            estado = _estado(amb, cliente, entradas, peca, aval)
    except ErroIntegridade as e:
        return {"peca": peca, "estado": "integridade_nao_confirmada", "motivo": str(e),
                "pendencias": ["investigar o histórico e as cópias antes de qualquer decisão"]}
    estado["tipo"] = v["tipo"]
    estado["plataforma"] = v["plataforma"]
    estado["avisos"] = avisos_do_laudo(aval.laudo)
    estado["laudo"] = {k: aval.laudo[k] for k in ("resultado", "resumo", "por_natureza",
                                                  "requer_validacao_normativa", "status_maximo")}
    if arquivo is not None:
        proteger(amb.origem, arquivo, "o arquivo de trabalho")
        try:
            igual = sha256(Path(arquivo).read_bytes()) == sha256(arquivos["peca"])
        except OSError:
            igual = False
        estado["arquivo_de_trabalho"] = ("igual à versão registrada" if igual else
                                         "DIFERENTE da versão registrada: registre uma nova versão; "
                                         "o estado acima NÃO vale para ele")
    return estado


# ---- liberação manual -------------------------------------------------------

def _leia_antes(manifesto: dict) -> str:
    sim = manifesto["simulacao"]
    ed = manifesto["aprovacao_editorial"]
    vn = manifesto["validacao_normativa"]
    linhas = [
        "# CONTEÚDO TEXTUAL APROVADO: NÃO É AUTORIZAÇÃO PARA PUBLICAR A PEÇA AUDIOVISUAL",
        "",
    ]
    if sim:
        linhas += ["> **SIMULAÇÃO: NÃO PUBLICAR.** Pacote gerado com cliente fictício e decisões "
                   "simuladas, só para teste ou demonstração.", ""]
    linhas += [
        f"- Peça: `{manifesto['peca']}` versão {manifesto['versao']} ({manifesto['tipo']}, "
        f"{manifesto['plataforma']}), cliente `{manifesto['cliente']}`.",
        f"- Hash do conteúdo: `{manifesto['hash_conteudo']}`",
        "",
        "## O que este pacote é",
        "",
        "O TEXTO da peça (legenda ou roteiro), na versão exata acima, com as decisões humanas "
        "registradas. A publicação é MANUAL e deve ser feita por uma pessoa responsável.",
        "",
        "## O que este pacote NÃO é",
        "",
        "- Não é revisão do vídeo, da imagem ou do áudio finais: nada disso foi verificado.",
        "- Não autoriza publicar uma peça audiovisual que ainda não foi revisada.",
        "- Não é assinatura digital, certificado digital nem assinatura eletrônica qualificada.",
        "",
        "## Três atos distintos",
        "",
        "| Ato | Quem | Observação |",
        "|---|---|---|",
    ]
    for a in ed:
        linhas.append(f"| Aprovação editorial | `{a['identidade']}` ({a['papel']}) | nível {a['nivel']} |")
    if vn == "nao_exigida":
        linhas.append("| Validação normativa | — | não exigida para esta peça |")
    else:
        for a in vn:
            linhas.append(f"| Validação normativa | `{a['identidade']}` ({a['papel']}) | nível {a['nivel']} |")
    lib = manifesto["liberacao_manual"]
    linhas += [
        f"| Liberação manual | `{lib['identidade']}` | {lib['momento']}; liberar NÃO é aprovar nem publicar |",
        "",
        f"**Nível de garantia: {manifesto['nivel_garantia']}.** Aprovação declarativa registra quem "
        "afirmou decidir, mas não prova identidade.",
        "",
        f"Topo do registro de auditoria: seq {manifesto['topo_auditoria']['seq']}, "
        f"`{manifesto['topo_auditoria']['hash']}`.",
    ]
    return "\n".join(linhas) + "\n"


def liberar(amb: Ambiente, cliente_id: str, peca: str, identidade: str, simulacao: bool = False,
            hoje: date | None = None, ambiente: dict | None = None) -> dict:
    """Monta o pacote textual de uma peça APROVADA, a partir de um snapshot consistente.

    Tudo acontece sob a trava do registro: lê histórico e cópia, reavalia,
    exige 'aprovado', grava o pacote numa pasta temporária, RELÊ e REAVALIA
    tudo, confere que nada mudou e só então publica a pasta (rename) e
    registra a liberação. Qualquer divergência aborta sem deixar pacote.
    """
    cliente = _cliente(amb, cliente_id)
    _exigir_pessoa(amb, cliente, simulacao, ambiente)
    pol = politica_de(cliente)
    reg = Registro(amb.estado, cliente_id)
    with trava(reg.trava):
        entradas = reg.ler()
        v, aval, (ctx, arquivos) = _avaliar_atual(amb, cliente_id, entradas, peca, hoje)
        estado = _estado(amb, cliente, entradas, peca, aval)
        if estado["estado"] != "aprovado":
            raise ErroAprovacao(f"só peça aprovada é liberada; estado atual: {estado['estado']}")
        if estado["simulacao"] and not simulacao:
            raise ErroAprovacao("a peça foi aprovada em simulação; a liberação também precisa ser simulada")
        ident = identidades(entradas).get(identidade)
        if ident is None or not ident.ativa or not set(ident.papeis) & (pol.aprovadores | pol.validadores):
            raise ErroAprovacao("quem libera precisa ser identidade ativa com papel de revisor ou validador")
        momento = datetime.now(timezone.utc).isoformat(timespec="seconds")
        normativa_exigida = pol.exige_validacao_normativa or aval.laudo.get("requer_validacao_normativa")
        manifesto = {
            "esquema": ESQUEMA_LIBERACAO, "escopo": "conteudo_textual",
            "publicacao_audiovisual_autorizada": False, "publicacao_automatica": False,
            "cliente": cliente_id, "peca": peca, "versao": v["versao"], "tipo": v["tipo"],
            "plataforma": v["plataforma"], **aval.hashes,
            "aprovacao_editorial": estado["aprovacoes_editoriais"],
            "validacao_normativa": estado["validacoes_normativas"] if normativa_exigida else "nao_exigida",
            "liberacao_manual": {"identidade": identidade, "momento": momento},
            "nivel_garantia": estado["nivel_garantia"], "simulacao": bool(simulacao or estado["simulacao"]),
            "topo_auditoria": {"seq": len(entradas), "hash": entradas[-1]["hash"]},
            "limites": "Só o texto foi verificado e aprovado. Vídeo, imagem e áudio finais não.",
        }
        base = amb.estado / "liberadas" / cliente_id
        final = base / f"{peca}-v{v['versao']}"
        if final.exists():
            raise ErroAprovacao("esta versão já foi liberada")
        base.mkdir(parents=True, exist_ok=True)
        tmp = base / f".tmp-{peca}-v{v['versao']}-{secrets.token_hex(4)}"
        tmp.mkdir()
        try:
            (tmp / f"conteudo.{_EXTENSOES[v['tipo']]}").write_bytes(arquivos["peca"])
            (tmp / "laudo.json").write_bytes(canonico(aval.laudo))
            (tmp / "manifesto.json").write_text(json.dumps(manifesto, ensure_ascii=False, indent=2),
                                                encoding="utf-8")
            (tmp / "LEIA-ANTES.md").write_text(_leia_antes(manifesto), encoding="utf-8")
            if v["tipo"] == "legenda":
                (tmp / "fontes.md").write_text(
                    gerar_fontes_md(aval.laudo, texto_da_legenda(arquivos["peca"]), ctx.fatos,
                                    f"{peca} v{v['versao']}"), encoding="utf-8")
            # Segunda leitura: nada pode ter mudado entre a avaliação e a gravação.
            entradas2 = reg.ler()
            _, aval2, (_, arquivos2) = _avaliar_atual(amb, cliente_id, entradas2, peca, hoje)
            if entradas2 != entradas or aval2.hashes != aval.hashes or arquivos2 != arquivos:
                raise ErroIntegridade("conteúdo, configuração ou histórico mudaram durante a liberação")
            if sha256((tmp / f"conteudo.{_EXTENSOES[v['tipo']]}").read_bytes()) != v["arquivos"]["peca"]:
                raise ErroIntegridade("o conteúdo gravado no pacote não confere")
            os.rename(tmp, final)
        except BaseException:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
        try:
            reg.anexar_sem_trava("liberacao_manual", {
                "peca": peca, "versao": v["versao"], **aval.hashes, "identidade": identidade,
                "pacote": str(final.relative_to(amb.estado)), "simulacao": manifesto["simulacao"]})
        except BaseException:
            shutil.rmtree(final, ignore_errors=True)
            raise
        return {"pacote": str(final), "manifesto": manifesto}


# ---- auditoria --------------------------------------------------------------

def verificar_auditoria(amb: Ambiente, cliente_id: str, topo_exportado: Path | None = None) -> dict:
    reg = Registro(amb.estado, cliente_id)
    with trava(reg.trava):
        topo = reg.topo()
        if topo_exportado is not None:
            conferir_topo(reg, topo_exportado)
    return {"integro": True, "topo": topo,
            "observacao": "evidente a adulterações, não inviolável: compare com um topo "
                          "exportado e guardado fora desta máquina"}


def exportar_topo_auditoria(amb: Ambiente, cliente_id: str, destino: Path) -> dict:
    garantir_fora_do_git(Path(destino), "o destino do topo exportado")
    reg = Registro(amb.estado, cliente_id)
    with trava(reg.trava):
        return exportar_topo(reg, Path(destino))
