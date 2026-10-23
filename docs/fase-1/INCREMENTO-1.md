# Incremento 1: registro e verificação de fatos

| Campo | Valor |
|---|---|
| Status | Implementado. O Incremento 2 **não** foi autorizado. |
| Especificação | [`ESPECIFICACAO-MVP.md`](ESPECIFICACAO-MVP.md), seção 5 |
| Requisitos | Python 3.11+, só biblioteca padrão, sem rede, sem credenciais |
| Dados | Clientes **fictícios** `exemplo` e `exemplo-academia`; fixtures sintéticas |

> **Leia primeiro.** Tudo o que este incremento faz com afirmações é **heurística determinística**: listas de palavras, comparação de valores, unidades e termos de contexto. Um vínculo "forte" quer dizer só que valor, unidade e contexto coincidem. Ele **não prova** que a afirmação é verdadeira nem que se refere ao fato indicado. Por isso: casos ambíguos viram **aviso de revisão humana**, o `fontes.md` declara essa limitação no topo, e "passou" nunca é aprovação.

## O que mudou

### 1. Registro de fatos

Cada `[[fato]]` em `fatos.toml` (do cliente) ou no arquivo `--fatos-peca` (do briefing de uma peça) aceita:

| Campo | Obrigatório | Uso |
|---|---|---|
| `id`, `texto`, `valores`, `status` | sim | como no Incremento 0 |
| `categoria` | não (padrão `institucional`) | `institucional`, `produto`, `preco`, `saude`, `financeiro`, `comparativo`, `resultado` |
| `contexto` | não, mas sem ele todo vínculo é ambíguo | termos que precisam aparecer **na mesma frase** (`ferment*` = prefixo; sem acento e sem diferenciar maiúsculas) |
| `unidade` | não | `hora`, `dia`, `semana`, `kg`, `brl`… (sinônimos são normalizados: "horas", "h" → `hora`) |
| `valido_ate` | não | data `AAAA-MM-DD`; depois dela o fato conta como **expirado** |
| `[fato.fonte]` | para liberar afirmações | `tipo`, `referencia`, `informado_por`, `informado_em` |
| `[fato.verificacao]` | quando `status = "verificado"` | `fonte`, `metodo`, `verificado_por`, `verificado_em` |

**Validações na carga:**
- `verificado` sem `[fato.fonte]` e `[fato.verificacao]` é recusado;
- `fornecido` com `[fato.verificacao]` é recusado;
- fonte ou verificação incompletas são recusadas;
- categoria e data inválidas são recusadas;
- ids repetidos entre o registro do cliente e os fatos da peça são recusados.

### 2. Estados dos fatos

| Status efetivo | Efeito numa afirmação vinculada |
|---|---|
| `verificado` | libera, inclusive afirmações sensíveis |
| `fornecido` | libera com **aviso** `fato_nao_verificado`, que o aprovador precisa reconhecer; **bloqueia** se a categoria for sensível |
| `expirado` (status ou `valido_ate` vencido) | **bloqueia** |
| `contestado` | **bloqueia** |
| fato sem `[fato.fonte]` | **bloqueia** (`fato_sem_fonte`): sem fonte não há rastreabilidade |

A data usada para a validade é a de hoje, ou a passada em `--data-referencia AAAA-MM-DD`, o que torna o resultado reproduzível.

### 3. Vínculo por valor, unidade e contexto

Para cada quantidade na legenda:

| Situação | Quando | Severidade |
|---|---|---|
| `forte` | valor igual + unidade compatível + termo de `contexto` na mesma frase | depende do status do fato (tabela acima) |
| `ambiguo` | valor igual, mas a frase não contém o contexto do fato (ou o fato não tem contexto) | **aviso**: revisão humana |
| `unidade_divergente` | valor igual, unidades diferentes ("24 dias" × fato em horas) | **bloqueante** |
| `invalido` | só há fato expirado ou contestado com esse valor | **bloqueante** |
| `sem_fato` | nenhum fato com esse valor | **bloqueante** |
| `estrutural` | número editorial sem fato ("5 dicas", "parte 2") | **aviso**: confirme a contagem |
| `vago` | "o dobro", "dezenas", "metade", "três vezes mais" | **aviso**: não dá para conferir |

Exemplo: o fato "A massa fermenta por 24 horas" (contexto `massa`, `ferment*`) faz um vínculo **forte** com "a massa descansa 24 horas". Já em "entregamos em 24 horas" o vínculo é **ambíguo**: mesmo número, outro assunto.

### 4. Números por extenso, unidades e números editoriais

- **Por extenso:** "três", "vinte e cinco", "cento e vinte", "dois mil e quinhentos", "um milhão e duzentos mil", "dez por cento".
- **Misto:** "2 mil" e "1,5 milhão" viram um valor só (2000; 1500000).
- **O "e" só une partes compatíveis:** "entre três e cinco" são dois números, não oito.
- **Artigo:** "um"/"uma" sozinhos são tratados como artigo.
- **Unidades:** tempo, massa, volume, distância e reais (`R$` antes do número).
- **Editoriais:** número seguido de "dicas", "erros", "passos", "motivos"… ou precedido de "parte", "top", "passo"… vira aviso em vez de bloqueio.

### 5. Afirmações sensíveis

Listas de marcadores por categoria, em `shiba/afirmacoes.py`:

| Categoria | Marcadores fortes (bloqueiam sem apoio) | Marcadores fracos (pedem revisão) |
|---|---|---|
| resultado | garant*, comprovad*, sem risco | aumenta*, triplica*, multiplica*, transforma*, resultado* |
| saúde | cura, curam, curar, emagrec* | previn*, imunidade, saudáve*, tratamento*, trata, alivia*, combate*, detox… |
| financeiro | — | lucro*, rendimento*, investiment*, juros, renda extra… |
| comparativo | líder*, número 1, "melhor/maior do bairro/da cidade/do Brasil" | melhor, maior, mais barat*, único… |

Um marcador só é **apoiado** por um fato que cumpra as três condições:
1. está **verificado** e é **da mesma categoria**;
2. **afirma a mesma coisa**, ou seja, o texto do fato contém o termo do marcador;
3. está ligado à frase pelo `contexto` ou por uma quantidade com vínculo forte.

Fato da categoria que só foi fornecido, ou que está expirado ou contestado, **bloqueia** (`afirmacao_sensivel` / `promessa_resultado`).

Por que a condição 2: na frase "80% dos alunos emagrecem…, resultado garantido", o fato verificado "80% dos alunos avaliaram as aulas como boas" coincide em número e contexto, mas não afirma nem emagrecimento nem garantia. Sem essa condição, ele "apoiaria" a promessa. Esse caso apareceu nos testes e foi corrigido.

O cliente pode desligar categorias em `perfil.toml`, em `[fatos] categorias_sensiveis = [...]`.

### 6. `fontes.md`

`--fontes CAMINHO` grava a trilha da peça (e recusa sobrescrever sem `--sobrescrever`). O arquivo contém:
- aviso de que os vínculos são heurísticos e não garantem veracidade;
- metadados: cliente, plataforma, arquivo, **SHA-256 do texto verificado**, data de referência e resultado;
- tabela de cada afirmação: linha, elemento, frase, fato(s) com status e situação do vínculo;
- cada fato citado com status efetivo, categoria, arquivo de origem, fonte e verificação ("NÃO REGISTRADA" quando faltar);
- pendências (bloqueantes e avisos).

### 7. Laudo JSON

Campos **acrescentados** ao esquema `shiba.laudo/0.1`, sem mudar os existentes:
- `data_referencia`;
- `requer_revisao_humana` (verdadeiro se houver aviso);
- `vinculos` (cada elemento com situação, frase e fatos);
- `fatos_usados` (id, status efetivo, categoria, situações, `tem_fonte`).

### 8. Correções pequenas do Incremento 0

- `README.md` com uso, estrutura e links;
- `.gitignore` agora permite `.env.example`;
- `palavras_proibidas` aceita prefixo (`garantid*` pega "garantida" e "garantidos").

## Testes

```bash
python3 -m unittest discover -s tests -v
```

Resultado: **162 testes, todos OK** (74 do Incremento 0 + 88 novos).

- **Um teste do Incremento 0 foi ajustado:** `test_cli.test_legenda_bloqueada` fixava o conjunto exato de regras bloqueantes da legenda ruim. A regra nova `promessa_resultado` bloqueia corretamente o "Aqui é garantido". A asserção continua exata, agora com 4 regras.
- **Os demais 73 testes seguem inalterados.** Dois deles documentavam limitações do protótipo e continuam válidos, porque descrevem o comportamento da *regra específica* que testam:
  - `test_positivo_fato_fornecido_e_aceito_no_prototipo`: `numero_sem_fato` aceita o valor; o aviso de "fornecido" vem de `regra_vinculo_fatos`;
  - `test_limitacao_numero_por_extenso_nao_e_detectado`: `numero_sem_fato` só olha algarismos; o extenso é tratado por `numero_por_extenso`.

## Limitações restantes

### Vínculo e significado
1. **Contexto é presença de palavra, não compreensão.** "Não temos 3 unidades" faz vínculo forte com "3 unidades". **Negação não é detectada.**
2. **Coincidência de contexto passa.** Se a frase cita uma palavra do contexto por acaso, o vínculo é "forte" sem ser a mesma afirmação. O `fontes.md` existe para a pessoa conferir cada linha.
3. **O vínculo é por frase.** Uma afirmação cujo contexto está na frase anterior vira "ambígua". A divisão de frases não conhece abreviações ("Dr.", "Av.").
4. **Afirmações sem número e sem marcador** ("somos referência na região") não são detectadas.

### Números e unidades
1. Frações e decimais por extenso ("dois e meio", "meia dúzia") e ordinais ("primeiro", "terceira") não são reconhecidos.
2. "um"/"uma" sozinhos nunca contam como número, nem quando são ("só uma unidade").
3. **A lista de unidades é fechada** (tempo, massa, volume, distância, reais). Contagens como "alunos" e "clientes" não são unidade, então não diferenciam "3 alunos" de "3 unidades". Quem diferencia é o contexto.
4. **Número editorial depende de lista.** "3 grandes erros" (adjetivo no meio) não é reconhecido como editorial.
5. Números colados a letras ("covid19", "4K") continuam sendo cobrados, de propósito.

### Afirmações sensíveis
1. **As listas de marcadores são curtas, em pt-BR, e não cobrem sinônimos nem gírias.** Ausência de marcador **não** significa ausência de afirmação sensível.
2. **Marcadores fracos geram ruído de propósito:** "o melhor jeito de guardar pão" pede revisão.
3. A condição "o texto do fato contém o termo do marcador" é literal: o fato "líder de vendas" não apoia "liderança".

### Fontes e status
1. **O verificador não confere a fonte.** Ele só exige que os campos existam. Se a fonte é real e diz o que o fato afirma, quem confere é uma pessoa.
2. "Reconhecer um aviso" ainda não tem mecanismo. Isso é o Incremento 4 (aprovação); por enquanto, o laudo marca `requer_revisao_humana`.

### Limites de plataforma
Sem mudança desde o Incremento 0: o limite do Instagram continua `a_verificar` (só aviso), e TikTok e Shorts são o Incremento 2.
