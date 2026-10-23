# Incremento 4: aprovação e rastreabilidade

| Campo | Valor |
|---|---|
| Status | **4A, 4B e 4C implementados. 4D (assinatura autenticada) NÃO implementado**: aguarda verificação de compatibilidade e autorização específica |
| Decisões | D1 arquitetura A (4D depois); D2 fatos que influenciaram; D3 âncora local + topo exportável; D4 estado sempre fora do Git; D5 nova versão zera aprovações; D6 saúde com 2 revisores e validação independente (política inicial, não norma); D7 regra *deny* só proposta |
| Requisitos | Python 3.11+, só biblioteca padrão, sem rede, sem serviço pago, sem publicação |

## 1. Arquitetura

| Módulo | Responsabilidade |
|---|---|
| `shiba/hashes.py` | serialização canônica; hashes de conteúdo, laudo e achado |
| `shiba/auditoria.py` | registro encadeado por cliente, âncora, trava, topo exportável |
| `shiba/dependencias.py` | recalcula o trio de hashes de uma peça com a configuração atual |
| `shiba/identidades.py` | identidades lógicas como eventos; regras do cadastro controlado |
| `shiba/aprovacao.py` | política, validade de decisões e **cálculo do estado** |
| `shiba/fluxo.py` | API do fluxo, independente de interface: registrar, verificar, enviar, reconhecer, decidir, status, liberar, auditoria |
| `shiba/cli.py` | casca fina: comandos `identidade`, `peca`, `auditoria` |

### Diretório de estado (sempre fora do Git)

```
<estado>/                      --estado DIR (fictício) | o próprio --dados (real)
  pecas/<cliente>/<peca>/v<n>/ cópia imutável dos bytes de cada versão
  auditoria/<cliente>.jsonl    registro encadeado (só acréscimo)
  auditoria/<cliente>.ancora   último seq + hash
  auditoria/<cliente>.trava    trava entre processos
  liberadas/<cliente>/<peca>-v<n>/  pacote de CONTEÚDO TEXTUAL aprovado
```

O motor recusa um estado dentro de qualquer repositório Git ou dentro do código, **inclusive para clientes fictícios**.

## 2. Dependências de decisão (D2)

Cada decisão humana fica amarrada a três hashes. A decisão só conta enquanto **os três** forem iguais aos recalculados agora.

| Hash | Inclui |
|---|---|
| `hash_conteudo` | bytes exatos da peça e do arquivo de fatos da peça |
| `hash_config` | configuração efetiva do cliente na plataforma (todas as seções, com herança), perfil completo da plataforma, **registro completo de todo fato que influenciou a verificação** (qualquer vínculo, forte, ambíguo, inválido etc., **inclusive sem alerta**), bytes do léxico editorial e das listas de validação em uso, versão do motor (0.4.0) e dos esquemas |
| `hash_laudo` | resultado da verificação (achados e exigências), **sem a data**, recalculado com a data de hoje |

**O que não entra, e por quê:** fatos que não se ligaram a nenhum texto. Se um deles mudar de modo a afetar a peça, o laudo recalculado muda e o `hash_laudo` invalida a aprovação. Há testes para o fato influente sem alerta (muda → invalida), para o fato não influente (muda → continua valendo) e para o fato que vence (laudo muda → invalida).

## 3. Estados e atos

Os estados são **sempre calculados** a partir dos eventos válidos e dos hashes atuais. Não existe campo "aprovado" gravado.

| Estado | Significa |
|---|---|
| `rascunho` | versão com bloqueante, ou não verificada com a configuração e o laudo atuais |
| `verificado` | verificada sem bloqueante; **não é aprovação** |
| `aguardando_revisao` | falta quórum editorial ou reconhecer avisos |
| `aguardando_validacao_normativa` | falta o responsável competente (exigido pelo cliente ou pelo laudo) |
| `aprovado` | todas as decisões humanas exigidas, válidas para o conteúdo, a configuração e o laudo atuais. Significa **conteúdo textual aprovado por pessoas**: não é publicação |
| `rejeitado` | rejeição editorial ou recusa normativa da versão atual |
| `integridade_nao_confirmada` | histórico, âncora ou cópia da versão não conferem: **nada conta** (falha fechada) |

### Três atos distintos

| Ato | Quem | O que significa |
|---|---|---|
| **Aprovação editorial** | identidades com papel em `[equipe] aprovadores` | o texto está bom editorialmente |
| **Validação normativa** | identidade com papel em `validadores_normativos`, independente | o responsável competente validou; o motor não interpreta normas |
| **Liberação manual** | identidade revisora ou validadora | monta o pacote textual; **não é aprovação nem publicação** |

### Regras de validade de uma decisão

1. **Versão atual.** Toda nova versão zera as anteriores (D5), mesmo com bytes idênticos a uma versão antiga.
2. **Hashes atuais.** Os três hashes precisam ser os atuais.
3. **Identidade válida.** A identidade precisa estar ativa e ter o papel exigido, e o papel ainda precisa estar na equipe.
4. **Nível de garantia** igual ou maior que `nivel_minimo`. Exigir `autenticada` hoje **falha seguro**: nenhuma decisão conta até o 4D.
5. **Independência por identidade**, configurável:
   - o autor não aprova nem reconhece avisos da própria peça;
   - cada voto do quórum é de uma identidade distinta (duplicadas são descartadas);
   - o validador normativo não pode ser o autor nem um revisor da versão.
6. **Avisos reconhecidos.** Todo aviso do laudo atual precisa ser reconhecido, com justificativa, por um revisor.
7. **Nada de simulação em cliente real.** Decisões simuladas não contam para cliente real.

### Política inicial (configurável em `[revisao]`)

| Chave | Padrão | Segmento saúde |
|---|---|---|
| `aprovacoes_minimas` | 1 | **2** |
| `revisao_independente` | true | true |
| `validacao_normativa_independente` | true | true |
| `nivel_minimo` | declarativa | declarativa; **recomendado** `autenticada` para cliente real, **só depois** que o 4D existir e for autorizado |

O quórum 2 da saúde é uma **política inicial adotada por prudência**. **Não** se afirma que ele seja exigido por lei ou norma.

## 4. Identidade: o que é e o que não é

- **Papel ≠ identidade.** O papel (`resp-02`) diz o que se pode fazer; a identidade lógica (`id-rev1`) diz quem fez, segundo o cadastro.
- **Cadastro controlado.** Identidades são **eventos** no registro encadeado:
  - quem cadastrou (papel em `[equipe] cadastradores`);
  - referência do processo de cadastro (ex.: termo arquivado fora do sistema);
  - "bootstrap" só para a primeira identidade, que precisa ser cadastradora;
  - sem autocadastro e sem reaproveitar identificadores revogados.
- **O motor NÃO verifica identidade civil.** O vínculo pessoa ↔ identidade é responsabilidade do processo de cadastro do cliente.
- **Declarativa:** registra quem *afirmou* decidir. Não prova nada. Todo `status` e todo pacote dizem isso.
- **Autenticada (4D):** provará a **posse de uma chave privada**. Assinatura criptográfica **não comprova identidade civil por si só**: isso depende do cadastro que associou a chave à pessoa.
- **Não é** certificado digital nem assinatura eletrônica qualificada. O valor jurídico deve ser avaliado pelo jurídico do cliente.

## 5. IA e decisões humanas

| Operação | Pode ser executada por IA? |
|---|---|
| Registrar versão, verificar, enviar para revisão, status, auditoria | sim (não são decisões) |
| Cadastrar ou revogar identidade, reconhecer aviso, aprovar, rejeitar, validar ou recusar normativamente, liberar | **não**, exceto em `simulacao`, que só vale para cliente fictício e marca tudo como SIMULAÇÃO |

**Como isso é aplicado, e os limites:**
- **Na API:** decisões não simuladas são recusadas quando o ambiente tem `CLAUDECODE`, `CLAUDE_CODE_ENTRYPOINT` ou `AI_AGENT`. **É uma barreira de processo, não criptográfica.** Quem controla o ambiente pode remover as variáveis ou chamar funções internas; há um teste que demonstra isso explicitamente.
- **Na CLI:** decisões não simuladas exigem terminal interativo e a digitação dos 8 primeiros caracteres do hash. **É atrito, não proteção criptográfica.** A digitação também garante que a pessoa viu a versão certa: se algo mudar entre a exibição e a decisão, ela é recusada.
- **Só o 4D** (assinatura com chave fora do alcance do agente, idealmente FIDO2 com toque físico) impede de fato que um agente com acesso a shell decida em nome de alguém.

### Proposta de regra *deny* para o Claude Code (D7): NÃO aplicada

```json
{
  "permissions": {
    "deny": [
      "Bash(python3 -m shiba identidade:*)",
      "Bash(python3 -m shiba peca reconhecer:*)",
      "Bash(python3 -m shiba peca aprovar:*)",
      "Bash(python3 -m shiba peca rejeitar:*)",
      "Bash(python3 -m shiba peca validar-normativo:*)",
      "Bash(python3 -m shiba peca recusar-normativo:*)",
      "Bash(python3 -m shiba peca liberar:*)"
    ]
  }
}
```

Limite: a regra casa por **prefixo de comando**. Ela não impede `python3 -c "…"`, outro caminho de interpretador nem a edição direta dos arquivos de estado. É mais uma camada de processo, não uma fronteira de segurança.

## 6. Registro de auditoria

- **Formato:** cada linha é `{seq, anterior, evento, dados, hash}`; a âncora guarda o último `seq` e hash; a gravação é só por acréscimo, sob trava, e a âncora é escrita de forma atômica.
- **Detecta:** edição de campo, remoção no meio, troca de ordem, inserção forjada, hash adulterado, truncamento no fim e âncora ou log apagados.
- **Falha fechada:** com histórico adulterado, nada conta e nada se acrescenta.
- **Evidente a adulterações, NÃO inviolável.** Quem controla a máquina pode **reescrever a cadeia inteira e a âncora**. Isso só é detectado comparando com um **topo exportado** (`auditoria exportar-topo`) guardado num lugar independente; há teste para isso.
- **Tentativas recusadas** (aprovação duplicada, autor aprovando etc.) também viram eventos.

## 7. Liberação (snapshot consistente)

`peca liberar` faz tudo **sob a trava do registro**:
1. lê histórico, âncora e a cópia da versão;
2. reavalia e exige `aprovado`;
3. grava o pacote numa pasta temporária;
4. **relê e reavalia tudo** e confere que histórico, bytes e os três hashes não mudaram;
5. só então renomeia a pasta para o nome final e registra `liberacao_manual`.

Qualquer divergência aborta sem deixar pacote nem temporário. Há teste que altera a configuração no meio da liberação.

**O pacote** contém `conteudo.*`, `laudo.json`, `manifesto.json`, `LEIA-ANTES.md` e `fontes.md` (legenda), e é identificado como **CONTEÚDO TEXTUAL APROVADO**:
- `escopo = "conteudo_textual"`;
- `publicacao_audiovisual_autorizada = false`;
- `publicacao_automatica = false`;
- os três atos aparecem separados e o nível de garantia é explícito;
- em simulação, leva "SIMULAÇÃO: NÃO PUBLICAR".

A aprovação de uma legenda ou roteiro **não significa** que o vídeo final foi revisado.

## 8. Testes

**431 testes: 430 OK, 1 pulado, 0 falhas.** Os 353 anteriores passaram **sem alteração**.

| Parte | Arquivo | Testes |
|---|---|---|
| 4A | `test_auditoria.py` | 21 |
| 4B | `test_aprovacao.py` | 34 |
| 4C | `test_fluxo.py` | 23 |

Os testes de segurança pedidos:

| Pedido | Onde |
|---|---|
| Edição posterior à aprovação | `TestEdicaoPosterior`, `TestSeguranca.test_edicao_da_copia…`, `test_arquivo_de_trabalho_editado`, `test_versao_nova_com_os_mesmos_bytes_zera` |
| Aprovação duplicada | `TestDuplicadaEConflitos.test_aprovacao_duplicada`, `test_tentativa_recusada_fica_no_historico` |
| Papéis conflitantes | autor aprovando, identidade sem papel, revogada, papel retirado, validador que foi revisor, independência desligada |
| Histórico adulterado | 10 casos em `TestCadeia` + `test_historico_adulterado_bloqueia_tudo` + reescrita total vs. topo exportado |
| Configuração modificada | `TestConfiguracaoModificada` (config, política, fato influente sem alerta, fato não influente, fato vencido), `test_configuracao_modificada_depois_da_aprovacao`, `test_mudanca_durante_a_liberacao…` |
| Reutilizar aprovação de outra peça | `test_aprovacao_reutilizada_de_outra_peca`, `test_aprovacao_de_outra_peca_nao_libera` |

## 9. Limitações e riscos

1. **Aprovação declarativa não prova identidade.** A independência entre papéis também é declarativa: uma pessoa que mente sobre a identidade burla o quórum.
2. **IA e decisões:** barreira de processo (variáveis de ambiente, TTY, regra *deny* proposta), contornável por quem controla o ambiente. Só o 4D com chave FIDO2 fecha esse caminho.
3. **Administrador local** pode apagar ou reescrever o histórico inteiro. A cadeia só detecta isso com o topo exportado guardado fora. As assinaturas do 4D impedirão **forjar**, não **apagar**.
4. **Carimbo de tempo** é do relógio local: informativo, não confiável. A ordem vem da cadeia.
5. **Trava no Windows** é mais fraca que o `flock` do POSIX. Não há sincronização entre máquinas.
6. **Só texto.** Vídeo, imagem e áudio finais continuam fora do escopo; o pacote diz isso.
7. **Juridicamente,** não é assinatura eletrônica qualificada nem certificado digital.

## 10. Plano de compatibilidade para o 4D (não implementado)

**Verificação feita neste ambiente** (somente leitura): o container de desenvolvimento **não tem OpenSSH** (`ssh` e `ssh-keygen` ausentes). Os testes do nível autenticado não podem rodar aqui sem instalar algo, e isso exige sua autorização.

**Na sua máquina**, comandos somente leitura para rodar e me mandar o resultado:

| Item | Comando | Necessário |
|---|---|---|
| Versão do OpenSSH | `ssh -V` | ≥ 8.2 para `-Y sign/verify` com chaves `-sk`. `-Y sign` existe desde a 8.1; recomendo 8.9+ |
| `ssh-keygen` presente | `command -v ssh-keygen` (Windows: `where ssh-keygen`) | sim |
| Suporte a FIDO2 | `ssh -Q key \| grep sk-` | lista `sk-ssh-ed25519@openssh.com` |
| Biblioteca FIDO | só se for usar chave física | `libfido2` (Linux/macOS) ou o OpenSSH do Windows 10/11 com Windows Hello |
| Sistema | `uname -a` / versão do Windows | — |

**Desenho previsto** (para aprovação futura):
- adaptador `shiba/assinatura.py` chamando `ssh-keygen -Y sign` e `ssh-keygen -Y verify` com namespace `shiba-aprovacao` e um arquivo `allowed_signers` **fora do Git**, gerado a partir das identidades cadastradas;
- assinatura sobre o payload canônico: cliente, peça, versão, ato, papel e três hashes;
- verificação **a cada cálculo de estado**;
- `nivel_minimo = "autenticada"` passa a valer;
- **nenhuma chave gerada pelo motor:** cada pessoa gera a própria, de preferência `ed25519-sk` com toque físico, e o cadastro registra só a chave pública e a impressão digital;
- testes com chaves **descartáveis geradas em pasta temporária**, sem tocar em `~/.ssh` (exigem OpenSSH no ambiente de testes).

**Riscos do 4D:**
- dependência de um binário externo, com versões diferentes por sistema;
- comportamento do Windows;
- perda ou troca de chave exige um processo de revogação;
- assinatura prova posse de chave, não identidade civil.
