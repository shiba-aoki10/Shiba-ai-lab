# Especificação do MVP: Fase 1 do Shiba AI Lab

| Campo | Valor |
|---|---|
| Versão | 1.1 (revisada após as decisões D1–D6 e as correções obrigatórias 1–5) |
| Data | 23/10/2026 |
| Status | **Aprovada como direção arquitetural. Implementação NÃO autorizada.** |
| Base | [`docs/auditorias/instagram-skills/RELATORIO.md`](../auditorias/instagram-skills/RELATORIO.md) |
| Branch | `claude/instagram-skills-audit-mfdgav` (nada em `main`) |

> **Regra deste documento.** Nenhum número aqui é resultado medido. Limites de plataforma, parâmetros e metas aparecem marcados como **[a verificar]** (precisam de uma fonte oficial) ou **[meta proposta]** (alvo de projeto a calibrar com dados reais). Não há métricas de marketing, resultados de campanha nem dados de clientes neste documento.

---

## 1. Objetivo e escopo

**Objetivo:** produzir, verificar e aprovar peças de marketing em português brasileiro para **Instagram, TikTok e YouTube Shorts** (D6): roteiros de vídeo curto, legendas, hooks, hashtags e calendário editorial. O MVP atende vários clientes, começando pelo piloto **Shiba Aoki** (D3). Nenhuma peça sai sem aprovação humana registrada.

O sistema deve ser compatível no futuro com Claude Code, Hermes Agent e modelos locais.

**O MVP entrega:**
1. Skills em pt-BR no formato `SKILL.md` (padrão agentskills.io).
2. Um motor local (`shiba`) em Python, determinístico e sem rede.
3. Templates reutilizáveis por cliente, com herança padrão → segmento → cliente, configurados em **TOML** (D1).
4. Um verificador editorial automático, com regras fixas e sem LLM.
5. Um **registro de fatos** que separa fatos fornecidos de fatos verificados, com rastreabilidade de fonte (correção 2).
6. Um fluxo de aprovação obrigatório, com 1 aprovador por padrão e 2 quando configurado (D5).
7. Exportação de um pacote para publicação **manual**.

**Fora do escopo do MVP:**

| Item | Fase prevista |
|---|---|
| Publicação automática em qualquer plataforma | 3 |
| Coleta de dados externos (APIs de métricas, scraping) | 3 |
| Geração de imagem, voz e vídeo | 2 |
| Servidor MCP | 2 |
| Interface web | 4 |
| Autenticação forte de aprovadores (ver seção 6.4) | 2/3 |

---

## 2. Princípios

1. **Separação estrita** entre o motor (código), as skills (prompts e conhecimento) e as integrações (adaptadores externos).
2. **Local primeiro.** O motor roda sem rede. As integrações externas são opcionais e ficam desligadas por padrão.
3. **Nada inventado.** Nenhum componente cria números, métricas, resultados ou dados de cliente. Todo dado factual de uma peça aponta para um fato registrado (seção 5).
4. **Humano no controle.** O agente gera rascunhos, e só um aprovador humano libera uma peça.
5. **Dados de cliente fora do código.** Os dados reais ficam fora do Git por padrão (D2) e nunca entram em testes sem autorização registrada (correção 5).

---

## 3. Arquitetura

```
┌───────────────────────────────────────────────────────────────────┐
│ ORQUESTRADOR: Claude Code | Hermes Agent | terminal humano         │
└──────────┬──────────────────────────────────┬─────────────────────┘
           │ lê                               │ chama a CLI (saída JSON)
┌──────────▼────────────┐      ┌──────────────▼─────────────────────┐
│ SKILLS (só prompt)    │      │ MOTOR `shiba` (Python, sem rede)   │
│ skills/*/SKILL.md     │      │  dominio/     modelos e estados    │
│ conhecimento/pt-BR/   │      │  plataformas/ perfis IG/TT/Shorts  │
│ sem código, sem rede, │      │  fatos/       registro + rastreio  │
│ sem credenciais       │      │  templates/   renderização         │
└───────────────────────┘      │  qualidade/   regras + léxicos     │
                               │  aprovacao/   estados, hash, HMAC  │
                               │  exportacao/  pacote manual        │
                               └──────────────┬─────────────────────┘
┌───────────────────────┐      ┌──────────────▼─────────────────────┐
│ DADOS DE CLIENTE      │      │ INTEGRAÇÕES (interfaces)           │
│ FORA do Git (D2)      │─────▶│ MVP: só exportador manual          │
│ $SHIBA_DADOS/clientes │      │ Futuro: adaptadores atrás da       │
│ $SHIBA_DADOS/producao │      │ verificação de aprovação           │
└───────────────────────┘      └────────────────────────────────────┘
```

### 3.1 Estrutura do repositório (somente código e modelos)

```
shiba/                 motor (pacote Python)
skills/                skills pt-BR
conhecimento/pt-BR/    fórmulas de hook, voz, léxico anti-IA, hashtags, datas BR
plataformas/           perfis de plataforma em TOML (com fonte e data de cada limite)
modelos/clientes/      templates de cliente FICTÍCIOS (_modelo, exemplos de segmento)
tests/                 testes com fixtures SINTÉTICAS apenas
docs/
NOTICE                 atribuição MIT ao instagram-skills (commit 6a12448)
```

### 3.2 Dados reais, fora do Git (D2)

- Ficam num diretório definido pela variável `SHIBA_DADOS` (ex.: `~/ShibaDados/`). O padrão fica **fora** da árvore do repositório.
- O motor **se recusa** a usar um `SHIBA_DADOS` que esteja dentro de um repositório Git. Isso evita commit acidental.
- O `.gitignore` do repositório bloqueia, como segunda barreira, os nomes `clientes/`, `producao/`, `corpus/` e `*.chave`.

```
$SHIBA_DADOS/
  clientes/<id>/perfil.toml, voz.md, fatos.toml, autorizacao.toml
  producao/<id>/<AAAA-MM>/<peça>/   rascunho, laudos, aprovações, exportação
  corpus/<id>/                      material real para calibragem (exige autorização)
  auditoria/log.jsonl
```

### 3.3 Dependências e custos (correção 3)

**Software:**
- **Execução:** Python 3.11+ com a biblioteca padrão apenas (`tomllib`, `hashlib`, `hmac`, `json`, `argparse`, `string`).
- **Testes:** `unittest`, também da biblioteca padrão. Assim o protótipo não precisa de nenhuma instalação. `pytest` e `ruff` (MIT) entram depois, como opção de desenvolvimento, e só com autorização.
- Todo o software do MVP tem licença livre e **custo de licença zero**.

**Software gratuito ≠ operação sem custos.** A operação tem custos que este documento **não estima**, porque não há dados para isso:

| Custo de operação | Natureza | Observação |
|---|---|---|
| Tempo humano | Redação de briefings, revisão, aprovação, cadastro de fatos, verificação de fontes | Principal custo do MVP |
| Hardware | Máquina com a RTX 5060 para os modelos locais | Investimento e depreciação; capacidade a diagnosticar (D4) |
| Energia elétrica | Inferência local | Depende do uso real |
| LLM em nuvem | Assinatura ou consumo de API, se Claude ou outro serviço for usado | Opcional, mas provável na revisão final |
| Armazenamento e backup | Dados de cliente e log de auditoria fora do Git | Disco local e/ou serviço de backup |
| Contas de plataforma | Instagram, TikTok, YouTube | Sem custo de API no MVP (publicação manual) |
| Manutenção | Atualizar léxicos, perfis de plataforma e skills | Recorrente |

---

## 4. Plataformas (D6)

Cada plataforma tem um perfil em `plataformas/<id>.toml`. **Todo limite registra fonte, data de consulta e status.** Um limite com status `a_verificar` gera só **aviso**, nunca bloqueio, até alguém confirmá-lo na documentação oficial.

| Campo | Instagram (Reels/feed) | TikTok | YouTube Shorts |
|---|---|---|---|
| Limite de caracteres da legenda/descrição | [a verificar] | [a verificar] | [a verificar] |
| Título | não se aplica | não se aplica | [a verificar] |
| Duração máxima do vídeo | [a verificar] | [a verificar] | [a verificar] |
| Texto visível antes do "mais" | [a verificar] | [a verificar] | não se aplica |
| Faixa de hashtags recomendada | [meta proposta] | [meta proposta] | [meta proposta] |

Formato de exemplo (valores ilustrativos, **não** usar sem verificação):

```toml
[limites.legenda_max_caracteres]
valor = 0            # preencher após verificação
status = "a_verificar"   # a_verificar | verificado | expirado
fonte = ""           # URL da documentação oficial
consultado_em = ""   # AAAA-MM-DD
verificado_por = ""
```

As faixas de hashtags e as fórmulas de hook vindas do instagram-skills são **heurísticas do autor original**, sem evidência publicada. Elas entram como hipótese editorial, não como regra de desempenho.

---

## 5. Registro de fatos (correção 2)

### 5.1 Modelo

Cada cliente tem um `fatos.toml` com fatos identificados. Há **dois níveis** de confiança:

| Status | Significado | Requisitos mínimos |
|---|---|---|
| `fornecido` | Informado pelo cliente ou pela equipe, ainda sem conferência | `fonte.tipo` (ex.: `cliente_declarou`, `briefing`, `documento_interno`), `fonte.referencia`, `informado_por`, `informado_em` |
| `verificado` | Conferido contra uma fonte checável | Tudo de `fornecido` + `verificacao.fonte` (URL, documento ou registro), `verificacao.metodo`, `verificado_por`, `verificado_em` |
| `expirado` | Passou da `valido_ate` | Bloqueia o uso até ser renovado |
| `contestado` | Alguém marcou como duvidoso | Bloqueia o uso |

```toml
[[fato]]
id = "F-0001"
texto = "<afirmação exatamente como pode ser usada>"
valores = []                      # números presentes na afirmação, se houver
categoria = "institucional"       # institucional | produto | preco | saude | financeiro | comparativo | resultado
status = "fornecido"
valido_ate = ""                   # opcional
[fato.fonte]
tipo = "cliente_declarou"
referencia = "<briefing, e-mail ou reunião de AAAA-MM-DD>"
informado_por = "<nome>"
informado_em = "AAAA-MM-DD"
# [fato.verificacao] só existe quando status = "verificado"
```

### 5.2 Regras no verificador

| Situação na peça | Severidade |
|---|---|
| Número ou afirmação factual **sem** fato associado (nem no registro, nem no briefing da peça) | **bloqueante** |
| Uso de fato `expirado` ou `contestado` | **bloqueante** |
| Uso de fato `fornecido` (não verificado) | **aviso**: o aprovador precisa reconhecer de forma explícita |
| Fato das categorias `saude`, `financeiro`, `comparativo` ou `resultado` sem status `verificado` | **bloqueante** (as categorias são configuráveis por segmento) |
| Promessa de resultado de marketing ou de negócio ("aumenta X%", "garante") sem fato `verificado` | **bloqueante** |

### 5.3 Rastreabilidade

- Cada peça grava em `fatos_usados` os IDs e o status de cada fato **no momento da aprovação**.
- O pacote exportado inclui um `fontes.md` com cada afirmação, o ID do fato, o status e a fonte.
- Mudar o status de um fato depois da aprovação não altera o registro já aprovado (que fica imutável), mas o exportador avisa se algum fato usado mudou desde então.

### 5.4 Regras para as skills (correção 4)

- As skills **não podem** inventar números, depoimentos, nomes de clientes, resultados nem métricas.
- Faltou um dado: a skill pergunta. Se não houver resposta, a afirmação sai do texto.
- As skills **não** fazem previsões de desempenho ("este hook vai gerar mais salvamentos"). Elas citam a fórmula usada e a marcam como hipótese editorial.

---

## 6. Aprovação

### 6.1 Estados

```
rascunho ─verificar─▶ verificado ─enviar─▶ em_revisão ─aprovar (1 ou 2)─▶ aprovado ─exportar─▶ exportado
    ▲                     │ (bloqueante)         │ ajustes
    └─────────────────────┴──────────────────────┘
```

### 6.2 Aprovadores (D5)

- `perfil.toml` define `aprovadores = [...]` e `aprovacoes_minimas = 1` por padrão.
- Dá para exigir `2` por cliente, por tipo de peça ou por categoria de fato (ex.: peças com fatos de `saude`).
- Quando são 2, os aprovadores precisam ser pessoas diferentes.

### 6.3 Mecanismo

- Cada aprovação registra: aprovador, data e hora, SHA-256 do conteúdo canônico mais os anexos, `fatos_usados`, as justificativas dos avisos e um HMAC calculado com uma chave local fora do repositório.
- O exportador recalcula o hash e o HMAC. Se houver divergência, a peça volta para `rascunho`.
- `shiba aprovar` exige um terminal interativo. O agente fica bloqueado de chamá-lo por regras de permissão do orquestrador (deny no Claude Code; restrição equivalente no Hermes).
- Toda transição vai para um log de auditoria só de acréscimo, com hash encadeado.

### 6.4 Limites de segurança (correção 1)

> **A aprovação do MVP NÃO é autenticação forte.** Ela só garante que um conteúdo aprovado não foi alterado depois e deixa uma trilha de auditoria. Ela **não prova quem aprovou**.

| O mecanismo garante | O mecanismo NÃO garante |
|---|---|
| Detectar alteração de conteúdo ou anexo depois da aprovação | Identidade do aprovador: o nome é declarado, não autenticado |
| Impedir exportação de peça sem registro de aprovação | Que o agente não forje uma aprovação se tiver acesso à chave HMAC e a um terminal irrestrito na mesma conta |
| Detectar edição ou remoção no meio do log encadeado | Proteção contra quem controla a máquina, a chave e o log ao mesmo tempo |
| Separar o fluxo do agente do fluxo humano por regra de permissão | Não-repúdio: o aprovador pode negar que aprovou |

**Por que é aceitável no MVP:** nada é publicado automaticamente. A publicação manual é, ela própria, um segundo ato humano.

**Pré-requisito para qualquer publicação automática (fase 3):**
1. Assinatura por aprovador com chave pessoal (ex.: assinatura SSH ou GPG, ferramentas livres).
2. Chave guardada fora do alcance do agente (outro usuário do sistema operacional ou token de hardware).
3. Um serviço de aprovação separado do ambiente onde o agente roda.

---

## 7. Templates de cliente

- **Herança:** `padrao` → `segmento` → `cliente`. Listas são somadas, e escalares são sobrescritos pelo nível mais específico.
- **No Git:** só modelos **fictícios** (`modelos/clientes/_modelo`, `exemplo-gastronomia`, `exemplo-educacao`). O cliente "Shiba Aoki" vive só em `$SHIBA_DADOS`.
- **Arquivos por cliente:**
  - `perfil.toml`: identidade, público, tom, pilares e pesos, palavras e expressões proibidas, hashtags fixas e proibidas, CTAs, emojis e @ permitidos, plataformas ativas, aprovadores, sobrescritas de regras;
  - `voz.md`: impressão digital da voz, construída **só** a partir de amostras reais fornecidas e autorizadas;
  - `fatos.toml` (seção 5);
  - `autorizacao.toml` (seção 9);
  - modelos de peça: `legenda`, `roteiro-curto` (15/30/60 s), `calendario-semanal`.

---

## 8. Componentes

### 8.1 Skills

| Skill | Saída |
|---|---|
| `shiba-roteiro` | roteiro por cenas para IG, TikTok e Shorts: tempo, visual, fala, texto na tela; duração estimada pelo parâmetro configurável [meta proposta, calibrar com vídeos reais autorizados] |
| `shiba-legenda` | legenda ou descrição por plataforma, com hook, corpo, 1 CTA e `fatos_usados` |
| `shiba-hooks` | opções por fórmula (marcadas como hipótese), ou a classificação de um hook colado |
| `shiba-hashtags` | conjunto por plataforma; tamanho das hashtags rotulado como **estimativa não medida** |
| `shiba-calendario` | calendário multiplataforma: formato, pilar, hook, objetivo editorial e datas comemorativas BR |
| `shiba-revisor` | reescrita anti-IA em pt-BR + laudo do verificador |
| `shiba-perfil-voz` | rascunho de `voz.md` a partir de amostras autorizadas |

Regras comuns: frontmatter só com `name`/`description`; orçamento de tokens por skill [meta proposta: ≤ 12 mil]; seção 5.4 obrigatória; checklist manual quando não houver terminal.

### 8.2 Verificador (`shiba verificar`)

- **Legenda/descrição, por plataforma:** limites do perfil de plataforma (bloqueia só se `verificado`); hashtags (contagem, duplicadas, proibidas); palavras proibidas do cliente; fatos (seção 5.2); léxico anti-IA pt-BR por densidade de parágrafo (aviso); aberturas genéricas; isca de engajamento; pilhas de frases curtas; travessões e emojis acima do limite do cliente; CTA ausente ou múltiplo; link e @ fora da lista permitida.
- **Roteiro:** duração estimada contra a duração-alvo e o máximo da plataforma; hook dentro da janela inicial configurada; cada cena com visual e áudio; texto na tela por cena dentro do limite configurado; fatos na fala e no texto na tela.
- **Calendário:** distribuição de pilares, formatos e plataformas contra o configurado; fórmula de hook repetida em dias seguidos; datas duplicadas; datas comemorativas de uma lista local com fonte.
- **Saída:** JSON com esquema versionado + laudo legível que cita o trecho exato, a regra e a severidade.
- **Limiares:** todos os limiares numéricos vêm de configuração. Os padrões são **[meta proposta]** e mudam conforme a calibragem.

---

## 9. Dados de clientes e testes (correção 5)

1. **Os testes automatizados usam só fixtures sintéticas**, escritas para o teste e marcadas como fictícias. Nenhum dado real entra em `tests/` nem no Git.
2. **O uso de dados reais**, inclusive os do piloto Shiba Aoki, exige um `autorizacao.toml` em `$SHIBA_DADOS/clientes/<id>/` com: quem autorizou, data, escopo (`calibragem`, `geracao`, `envio_a_llm_em_nuvem`, `envio_a_llm_local`), validade e restrições.
3. **A calibragem com corpus real é um comando separado** (`shiba calibrar`). Ele não roda em CI, verifica a autorização antes de ler qualquer arquivo e publica só resultados **agregados** (contagens por regra), sem trechos do conteúdo.
4. **Envio a LLM em nuvem** de dados de um cliente só acontece com o escopo `envio_a_llm_em_nuvem` autorizado. Sem ele, as skills operam com modelo local ou com dados fictícios.
5. **Corpus pequeno (D3).** Com poucas amostras, a calibragem **reporta** contagens observadas sem declarar aprovação ou reprovação estatística. Os limiares formais entram em vigor quando o corpus atingir um tamanho mínimo [meta proposta, a definir com você].

---

## 10. Diagnóstico da RTX 5060 (D4)

A escolha do modelo local fica **suspensa** até o diagnóstico. Ele é feito por você, na sua máquina. Não é possível fazê-lo a partir deste ambiente de nuvem.

**Coleta (comandos somente leitura, a executar por você):**

| Item | Como obter |
|---|---|
| Modelo exato da GPU e VRAM total/livre | `nvidia-smi --query-gpu=name,memory.total,memory.free,driver_version --format=csv` |
| Versão do driver e do CUDA | `nvidia-smi` (cabeçalho) |
| RAM do sistema e CPU | Gerenciador de tarefas / `free -h` / `lscpu` |
| Sistema operacional | Windows/WSL2/Linux e versão |
| Espaço em disco para modelos | `df -h` ou equivalente |

**Critérios de escolha:**
- tamanho de contexto efetivo que cabe na VRAM (o Hermes documenta ≥ 64k; o cache KV de contexto longo consome VRAM);
- aderência a instruções em pt-BR, testada nas tarefas de referência com fixtures sintéticas;
- licença do modelo compatível com uso comercial.

**Importante:** a RTX 5060 tem variantes com quantidades de memória diferentes. Nenhuma suposição será feita antes do diagnóstico.

**Saída:** uma tabela "modelo × quantização × contexto × cabe/não cabe", preenchida **só** com valores observados na sua máquina.

---

## 11. Critérios de aceitação

**Motor e dados**
- **CA-01.** `shiba cliente validar <id>` rejeita um perfil inválido indicando o campo, e aceita os modelos fictícios.
- **CA-02.** A herança padrão → segmento → cliente está coberta por testes de sobrescrita e de soma de listas.
- **CA-03.** O motor roda sem rede e sem pacotes externos. Um teste falha se encontrar import fora da biblioteca padrão ou de rede.
- **CA-04.** O motor recusa um `SHIBA_DADOS` dentro de um repositório Git.

**Plataformas e fatos**
- **CA-05.** Um limite `a_verificar` produz só aviso; um limite `verificado` sem `fonte` ou sem `consultado_em` é rejeitado na validação.
- **CA-06.** Número ou afirmação sem fato associado é **sempre** bloqueado (100% dos casos no conjunto de teste sintético).
- **CA-07.** Fato `fornecido` gera aviso que exige reconhecimento; fato de categoria sensível sem `verificado` bloqueia; fato `expirado` ou `contestado` bloqueia.
- **CA-08.** O pacote exportado contém `fontes.md` com o ID, o status e a fonte de todo fato usado.
- **CA-09.** Promessa de resultado sem fato `verificado` é bloqueada.

**Verificador**
- **CA-10.** Cada regra tem pelo menos 1 teste positivo e 1 negativo com fixtures sintéticas.
- **CA-11.** O laudo cita o trecho, a regra e a severidade; o JSON segue um esquema versionado.
- **CA-12.** Com corpus real autorizado, `shiba calibrar` produz um relatório agregado sem trechos de conteúdo. As metas de falso positivo e falso negativo são definidas **depois** da primeira calibragem, não antes.

**Aprovação**
- **CA-13.** Peça com achado bloqueante não entra em `em_revisão`.
- **CA-14.** Alterar 1 caractere ou 1 anexo depois da aprovação faz a exportação falhar.
- **CA-15.** `shiba aprovar` falha fora de terminal interativo, com aprovador fora da lista e, quando `aprovacoes_minimas = 2`, com o mesmo aprovador duas vezes.
- **CA-16.** O log encadeado detecta remoção ou edição de uma entrada intermediária.
- **CA-17.** A documentação de operação inclui a seção 6.4 (limites de segurança) de forma literal.

**Dados de clientes**
- **CA-18.** Um teste automatizado falha se `tests/` contiver arquivo fora do padrão de fixture sintética marcada.
- **CA-19.** `shiba calibrar` e as operações sobre dados reais recusam a execução sem `autorizacao.toml` válido para o escopo pedido.

**Skills e compatibilidade**
- **CA-20.** Todas as skills passam no validador de frontmatter e no orçamento de tokens configurado.
- **CA-21.** No Claude Code, com briefing **sintético**, as skills de legenda e roteiro geram peças que o verificador aceita (sem bloqueante) para as 3 plataformas.
- **CA-22.** Depois do diagnóstico D4, as mesmas tarefas rodam no Hermes Agent com o modelo local escolhido. O resultado é registrado num comparativo descritivo, sem meta numérica no MVP.
- **CA-23.** Nenhuma saída de skill nos testes de referência contém número ausente do briefing ou do registro de fatos (checado pelo próprio verificador).

**Licença**
- **CA-24.** `NOTICE` com a atribuição MIT, e arquivos derivados citando a origem.

---

## 12. Riscos

| # | Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|---|
| R1 | O léxico anti-IA pt-BR gera falsos positivos | Alta | Médio | Começa como aviso; calibrar com corpus autorizado; exceções por cliente |
| R2 | O modelo local segue mal as regras longas | Alta | Médio | Orçamento de tokens; verificador determinístico; revisão final humana |
| R3 | Aprovação forjada pelo agente ou identidade não comprovada | Baixa no MVP | Alto | Seção 6.4; sem publicação automática; assinatura por aprovador antes da fase 3 |
| R4 | Vazamento de dados de cliente (Git, LLM em nuvem, logs) | Média | Alto | Dados fora do Git com recusa ativa; autorização por escopo; calibragem só agregada |
| R5 | Afirmações falsas publicadas | Média | Alto | Registro de fatos; bloqueio sem fato; categorias sensíveis exigem verificação |
| R6 | Limites de plataforma mudam ou são registrados errados | Alta | Médio | Status, fonte e data por limite; `a_verificar` só avisa; revisão periódica |
| R7 | Corpus do piloto pequeno demais para calibrar | Alta | Médio | Calibragem descritiva; limiares formais só com corpus mínimo |
| R8 | VRAM insuficiente para o contexto exigido pelo Hermes | Média | Médio | Diagnóstico D4 antes de escolher; alternativa com modelo em nuvem autorizado |
| R9 | Hermes incompatível com algum detalhe das skills | Média | Médio | Teste de fumaça cedo, só com recursos do padrão agentskills.io |
| R10 | Escopo cresce (mídia, publicação automática) | Alta | Médio | Fora de escopo explícito; mudanças só com a sua autorização |
| R11 | Peça "aprovada pelo verificador" mas fraca criativamente | Média | Médio | O verificador garante o mínimo; o humano decide a qualidade |
| R12 | Dependência de uma só pessoa (chave, operação) | Média | Médio | Documentação; procedimento de backup e rotação da chave |

---

## 13. Estimativa de esforço

Estimativa para 1 pessoa técnica. São horas de **projeto**, não de resultado.

| Pacote | Conteúdo | Horas |
|---|---|---|
| P0 | Estrutura, convenções, `NOTICE`, `.gitignore` defensivo, esquema do log | 4–6 |
| P1 | Conhecimento pt-BR (hooks, voz, léxico anti-IA, datas BR com fonte) | 16–24 |
| P2 | Motor: domínio, TOML, herança, templates, CLI, `SHIBA_DADOS` | 12–18 |
| P2b | Perfis de plataforma (IG, TikTok, Shorts) com verificação de fonte de cada limite | 6–10 |
| P2c | Registro de fatos e rastreabilidade | 8–12 |
| P3 | Verificador (legenda, roteiro e calendário × 3 plataformas) | 20–30 |
| P4 | Aprovação 1/2 aprovadores, hash/HMAC, log encadeado, exportador, documentação de limites | 14–22 |
| P5 | 7 skills pt-BR | 18–26 |
| P6 | Modelos fictícios de cliente + estrutura do piloto em `SHIBA_DADOS` | 6–10 |
| P7 | Testes com fixtures sintéticas, `shiba calibrar`, controles de autorização | 10–16 |
| P8 | Diagnóstico D4 (com você), validação no Claude Code e no Hermes | 6–12 |
| P9 | Guias de operação, de cliente novo e de cadastro de fatos | 5–8 |
| **Total** | | **125–194 h** |

O aumento em relação à versão 1.0 (100–154 h) vem de 3 plataformas, do registro de fatos, dos controles de autorização e da documentação de segurança.

---

## 14. Plano de implementação incremental

Cada incremento é pequeno, testável só com `unittest` (sem instalar nada) e termina num **gate de autorização** seu. Nada abaixo foi iniciado.

| Inc. | Entrega | Testável por | Horas | Gate |
|---|---|---|---|---|
| **0 – Protótipo** | `shiba verificar` para **1 legenda de Instagram** em arquivo Markdown, com 4 regras: (a) contagem de hashtags; (b) palavras proibidas; (c) **número sem fato** contra um `fatos.toml` sintético; (d) limite de caracteres lido do perfil de plataforma com status. Cliente fictício `exemplo`. Saída JSON + texto. | ~15–20 testes `unittest` com fixtures sintéticas | 6–10 | Você revisa o laudo e o formato dos arquivos TOML |
| 1 – Fatos | Status `fornecido`/`verificado`/`expirado`/`contestado`, categorias sensíveis, `fatos_usados`, `fontes.md` | Testes CA-06 a CA-09 | 8–12 | Revisão do modelo de fatos |
| 2 – Clientes e plataformas | Herança de perfis, recusa de `SHIBA_DADOS` dentro do Git, perfis TikTok e Shorts (limites `a_verificar` até checar a fonte) | CA-01 a CA-05 | 12–18 | Você confirma as fontes dos limites |
| 3 – Verificador completo | Léxico anti-IA pt-BR, regras de roteiro e calendário | CA-10, CA-11 | 16–24 | Revisão editorial do léxico |
| 4 – Aprovação | Estados, 1/2 aprovadores, hash/HMAC, log encadeado, exportador, documentação 6.4 | CA-13 a CA-17 | 14–22 | **Autorização para gerar a chave local** |
| 5 – Skills prioritárias | `shiba-legenda` e `shiba-revisor` (briefing sintético, Claude Code) | CA-20, CA-21, CA-23 | 8–12 | Avaliação das saídas |
| 6 – Demais skills | Roteiro, hooks, hashtags, calendário, perfil de voz | CA-20 a CA-23 | 10–14 | Avaliação das saídas |
| 7 – Diagnóstico e modelo local | Você roda o diagnóstico D4; escolha do modelo; teste no Hermes | CA-22 | 6–12 | **Autorização para instalar o runtime local** |
| 8 – Piloto Shiba Aoki | `autorizacao.toml`, corpus inicial pequeno, `shiba calibrar`, primeiras peças reais aprovadas | CA-12, CA-19 | contínuo | **Autorização para uso de dados reais** e definição do corpus mínimo |

### 14.1 Detalhe do Incremento 0 (protótipo)

**Arquivos previstos:**
- `shiba/__init__.py`, `shiba/cli.py`, `shiba/verificar.py`, `shiba/config.py`;
- `plataformas/instagram.toml`, com limites `a_verificar` até a fonte ser confirmada;
- `modelos/clientes/exemplo/{perfil,fatos}.toml`, fictícios;
- `tests/fixtures/sinteticos/*.md`, `tests/test_verificar.py`.

**Fora do protótipo:** aprovação, skills, LLM, rede, dados reais.

**Definição de pronto:**
- `python -m unittest` passa sem instalar nada;
- `python -m shiba verificar <arquivo> --cliente exemplo --plataforma instagram` gera JSON válido e um laudo legível;
- a regra de número sem fato bloqueia em 100% das fixtures preparadas para isso.

**Riscos do protótipo:** quase nenhum, porque é local, sem dados reais e sem dependências. O principal é o formato TOML precisar de ajuste, e o gate existe justamente para isso.

---

## 15. Decisões registradas

| ID | Decisão |
|---|---|
| D1 | TOML |
| D2 | Dados reais de clientes fora do Git por padrão, separados do código |
| D3 | Piloto Shiba Aoki, com corpus inicial pequeno e crescente conforme houver material real |
| D4 | Diagnosticar a RTX 5060 e a VRAM antes de escolher o modelo local |
| D5 | 1 aprovador no piloto; 2 quando configurado |
| D6 | Instagram, TikTok e YouTube Shorts |

**Pendências para os próximos gates:**
- autorização do Incremento 0;
- tamanho mínimo de corpus para ativar limiares formais;
- fontes oficiais dos limites de cada plataforma;
- resultado do diagnóstico D4.
