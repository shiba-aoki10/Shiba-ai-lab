# Incremento 3: revisor editorial, roteiro, calendário e perfis futuros

| Campo | Valor |
|---|---|
| Status | Implementado (3A, 3B, 3C, 3D). O Incremento 4 **não** foi autorizado. |
| Decisões | TOML; taxa de fala sem valor padrão (opção A); validação normativa como aviso identificado que impede aprovação final (opção A); responsáveis como papéis |
| Requisitos | Python 3.11+, só biblioteca padrão, sem rede, sem credenciais, sem publicação |
| Dados | Só fictícios |

## Princípios aplicados

- **Natureza de cada achado:** `tecnica` (o motor confere), `revisao_humana` (julgamento editorial) e `validacao_normativa` (só o responsável competente).
- **Alertas editoriais nunca bloqueiam.** São explicáveis (justificativa + sugestão), configuráveis pela herança e sujeitos à revisão humana.
- **Nenhum laudo aprova uma peça.** Todo laudo traz `exigencias_aprovacao` (sempre com `aprovacao_humana`) e `status_maximo`, que nunca é "aprovado":

| `status_maximo` | Quando |
|---|---|
| `correcao_necessaria` | há bloqueante |
| `aguardando_validacao_normativa` | há alerta normativo; passar no técnico **não** basta |
| `aguardando_aprovacao_humana` | nos demais casos |

- **Limite declarado em todo laudo (`limites_da_verificacao`):** só o texto é verificado. **Imagem, áudio e vídeo finais não são analisados**: legendas queimadas, falas gravadas, trilha, cortes e elementos visuais podem conter afirmações que o laudo não viu.
- **Motor independente de interface:** `shiba/api.py` concentra o uso (origem dos dados, isolamento, laudos em dicionário JSON). A CLI é uma casca. Claude, agentes locais, um aplicativo ou o iPhone, via serviço local futuro, devem chamar a API.

## 3A: revisor editorial pt-BR

- **Léxico versionado** em `conhecimento/pt-BR/editorial.toml`, com 40 expressões nas categorias `ia` (expressões recorrentes de IA), `cliche` e `muleta`. Cada uma tem justificativa e sugestão. Não é detector de IA.
- **Regras:** acúmulo de expressões `ia` no parágrafo (sozinha = info; a partir do limiar = aviso), clichês, muletas, repetição de palavra no parágrafo, frases seguidas com o mesmo início, frase longa, parágrafo longo, advérbios em -mente, pontuação repetida e caixa alta.
- **Seção herdável `[editorial]`:** limiares (padrão com valores **[meta proposta, a calibrar]**), `regras_desativadas`, `termos_extras` e `termos_ignorados`. Regra desconhecida, valor não positivo ou chave inventada são recusados.

## 3B: roteiro audiovisual

`python3 -m shiba roteiro verificar roteiro.toml --cliente <id>`

O roteiro distingue dois tipos de bloco:
- **`[[cena]]`, sequenciais:** sobreposição entre cenas **bloqueia**; buraco ou início depois de 0 s gera aviso.
- **`[[elemento]]`, simultâneos:** texto na tela, legenda, trilha, grafismo, logo, CTA visual, efeito sonoro e locução em off. **Podem se sobrepor de propósito.**

São válidos: cena sem locução, vídeo só com trilha instrumental, motion graphics, silêncio declarado (`audio = ["silencio"]`) e CTA visual (`forma = "visual"`, por cena ou elemento).

| Verificação | Comportamento |
|---|---|
| Gancho | fala ou texto dentro de `janela_gancho_s`, ou `gancho` declarado (gancho só visual é aceito se declarado); sem nada, aviso de revisão |
| Mensagem principal | declarada; `termos_mensagem` precisam aparecer em fala ou texto (senão aviso: pode estar só na imagem) |
| CTA | declarado; referência a cena ou elemento inexistente **bloqueia**; CTA antes da última cena pede revisão |
| Duração | cenas × alvo (tolerância configurada); máximo da plataforma só **bloqueia** se `verificado` (hoje nenhuma plataforma tem valor verificado) |
| Fala estimada | **desligada**: `palavras_por_segundo` não tem valor padrão, por decisão; será calibrada com vídeos autorizados |
| Coerência | toda cena com visual (bloqueia se faltar) e com áudio próprio ou de elemento (aviso); texto na tela até o limite configurado |
| Regras de texto | fatos, afirmações sensíveis, palavras proibidas, editorial e validação normativa, em cada fala e texto, com o achado apontando `cena c2 · fala` |

## 3C: calendário editorial

`python3 -m shiba calendario verificar calendario.toml --cliente <id>`

- **Arquivo final depende do status** (`[calendario] status_exigem_arquivo`, padrão: `pronto`, `aprovado`, `agendado`, `publicado`). No planejamento (`ideia`, `planejado`, `em_producao`, `em_revisao`) o arquivo não é exigido; se citado e ausente, é só aviso.
- **Bloqueantes:**
  - id repetido;
  - status ou plataforma inválidos;
  - responsável ausente, malformado (nome em vez de papel) ou fora da equipe;
  - hora malformada;
  - status de aprovação sem `aprovado_por` (ou com papel que não é aprovador);
  - peça que exige validação normativa com status de aprovação sem `validado_por` de um papel validador.
- **Avisos e informações:**
  - data fora do período, data vencida ou publicação com data futura;
  - conflito de horário na mesma plataforma;
  - carga por responsável;
  - pilares e variedade de ganchos.
- **Peça cancelada:** é ignorada nas checagens.
- **`aprovado_por` e `validado_por`:** são **registros declarativos**, não autenticação (Incremento 4).
- **Pessoas:** a seção `[equipe]` só aceita **identificadores de papel**. Nomes de pessoas ficam fora do Git. Há teste que varre modelos e fixtures.

## 3D: perfis futuros e saúde

- **Segmentos genéricos:** `saude`, `social` e `esportivo` (`modelos/segmentos/`). Nenhum cliente real cadastrado e nenhuma regra presumida. Há teste garantindo que não existe nada com "medicos", "vtc" ou "lntd" em `modelos/`.
- **Questionário de entrada** de cada cliente: [`PERFIS-FUTUROS.md`](PERFIS-FUTUROS.md).
- **`[revisao]`:**
  - `exige_validacao_normativa`;
  - `categorias_validacao_normativa`;
  - `listas_validacao` (listas em `conhecimento/pt-BR/validacao/`; a de saúde traz 19 temas, cada um com motivo e sem citar norma);
  - `aprovacoes_sugeridas` (para o Incremento 4).
- **`[normas] referencias`:** cadastradas **pelo cliente**, com título, status, fonte e data. O motor só as lista no laudo (`normas_registradas`) e nunca as interpreta.
- **Regra `validacao_normativa`** (aviso, natureza `validacao_normativa`): marcadores da categoria, quantidades ligadas a fatos da categoria **mesmo verificados** e termos das listas. A mensagem sempre diz: "o motor não avalia se é permitido".
- **Teste anti-conclusão jurídica:** varre código, conhecimento e modelos atrás de frases como "proibido por lei", "segundo a resolução" ou "a ANVISA proíbe". Ressalvas ("não avalia se é permitido") são aceitas, e o próprio detector é testado.

## Testes

```bash
python3 -m unittest discover -s tests -v
```

**353 testes: 352 OK, 1 pulado, 0 falhas.**

| Etapa | Testes |
|---|---|
| Anteriores (Incrementos 0–2) | 238, **sem nenhuma alteração** |
| 3A `test_editorial.py` | 30 |
| 3B `test_roteiro.py` | 36 |
| 3C `test_calendario.py` | 27 |
| 3D `test_normativa.py` | 22 |

O teste pulado continua sendo o de pasta sem permissão, porque o ambiente roda como root.

**Correções feitas durante o trabalho:**
1. Calendário: uma peça com status desconhecido escondia os demais problemas dela.
2. Marcador de saúde: "prevenir" e "prevenção" não eram detectados (lacuna do Incremento 1; acrescentado `preven*`).
3. Docstring de `normativa.py` reescrita para não soar como conclusão.
4. A fixture de calendário trocou um nome de pessoa fictício por um identificador malformado.

## Limitações e riscos

### Só texto
- **Imagem, áudio e vídeo não são analisados.** Um roteiro aprovado no papel pode virar outro vídeo na edição, e legendas queimadas ou falas gravadas fora do roteiro não são vistas. **Risco alto** se alguém tratar o laudo como revisão da peça final.

### Editorial
- **Heurísticas de estilo** erram para os dois lados. Não há análise sintática, sinônimos, ironia nem contexto. As listas são curtas e curadas internamente, sem medição.
- **Advérbios em -mente:** há exceções que escapam (verbos como "implemente" foram tratados manualmente).
- **Os limiares do padrão não foram calibrados** com textos reais autorizados.

### Roteiro
- **Gancho, mensagem e CTA são conferidos por presença de texto,** não por eficácia.
- **Fala estimada desligada** até haver taxa calibrada.
- **Duração máxima das plataformas sem valor** verificado.

### Calendário
- **Aprovação e validação são declarativas.** Qualquer pessoa com acesso ao arquivo pode escrever `aprovado_por = "resp-02"`. O Incremento 4 precisa trazer identidade e registro à prova de alteração.
- **Conteúdo das peças:** o calendário confere só a existência dos arquivos citados, não o conteúdo.

### Saúde e normas
- **A lista de temas de saúde é um ponto de partida genérico,** não validado por profissional. Ausência de termo não dispensa validação: no segmento `saude`, toda peça exige validação no calendário.
- **O motor não sabe quais normas se aplicam.** Isso depende do cliente e do responsável competente.
- **O teste anti-conclusão jurídica cobre padrões comuns em pt-BR,** não todas as formulações possíveis.

### Arquitetura
- **A API em Python ainda não é um serviço:** não há HTTP, autenticação nem controle de acesso. Expor o motor a um app ou iPhone exige um serviço local com essas camadas, que hoje não existe.
