# Incremento 0: protótipo do `shiba verificar`

| Campo | Valor |
|---|---|
| Status | Protótipo implementado. Só o Incremento 0 foi autorizado. |
| Especificação | [`ESPECIFICACAO-MVP.md`](ESPECIFICACAO-MVP.md), seção 14.1 |
| Requisitos | Python 3.11+ (usa `tomllib`). Nenhuma dependência externa. |
| Dados | Só o cliente **fictício** `exemplo` e fixtures sintéticas. |

## O que faz

Verifica **uma legenda de Instagram** (arquivo de texto UTF-8) contra 4 regras e emite um laudo em texto ou JSON.

```bash
python3 -m shiba verificar tests/fixtures/sinteticos/legenda_passa.md \
    --cliente exemplo --plataforma instagram [--formato json]
```

| Código de saída | Significado |
|---|---|
| 0 | `passou`: nenhum achado bloqueante |
| 1 | `bloqueado`: pelo menos 1 achado bloqueante |
| 2 | erro de uso ou de configuração |

> **"passou" não é aprovação.** Significa só que nenhuma regra automática bloqueou a peça. A aprovação humana é o Incremento 4 e ainda não existe.

## As quatro regras

| Regra | Bloqueia quando | Avisa quando |
|---|---|---|
| `hashtags` | a quantidade está fora da faixa `[hashtags] minimo..maximo` do cliente; hashtag da lista `proibidas` | hashtag repetida (sem diferenciar maiúsculas e acentos) |
| `palavra_proibida` | termo de `[palavras_proibidas] termos` aparece como palavra inteira (sem diferenciar maiúsculas e acentos; expressões aceitam qualquer espaço ou quebra de linha) | — |
| `numero_sem_fato` | número escrito com algarismos que não corresponde a nenhum fato com status `fornecido` ou `verificado` em `fatos.toml` (inclusive quando só corresponde a fato `expirado` ou `contestado`) | — |
| `limite_caracteres` | legenda vazia; excesso de caracteres **se** o limite da plataforma estiver `verificado` | excesso de caracteres com limite `a_verificar` ou `expirado` (mais um `info` lembrando que o limite não foi verificado) |

## Estrutura

```
shiba/
  __main__.py   entrada de `python -m shiba`
  cli.py        argumentos, leitura do arquivo (UTF-8, ≤ 64 KiB), códigos de saída
  config.py     carga e validação dos TOML (plataforma, cliente, fatos)
  regras.py     as 4 regras, como funções puras
  numeros.py    detecção e normalização de números pt-BR
  texto.py      utilitários que preservam posições (dobra de acento, trecho, linha)
  verificar.py  orquestra as regras e monta o laudo (esquema shiba.laudo/0.1)
plataformas/instagram.toml               limite com status, fonte e data
modelos/clientes/exemplo/perfil.toml     cliente fictício
modelos/clientes/exemplo/fatos.toml      fatos fictícios (verificado, fornecido, expirado)
tests/                                   unittest; fixtures sintéticas em tests/fixtures/sinteticos/
```

## Esquema do laudo (`shiba.laudo/0.1`)

```json
{
  "esquema": "shiba.laudo/0.1",
  "cliente": "exemplo",
  "plataforma": "instagram",
  "resultado": "passou | bloqueado",
  "resumo": {"bloqueante": 0, "aviso": 0, "info": 0},
  "metricas": {"caracteres": 0, "hashtags": 0, "numeros": 0},
  "achados": [
    {"regra": "...", "severidade": "bloqueante | aviso | info", "mensagem": "...",
     "inicio": 0, "fim": 0, "linha": 1, "trecho": "..."}
  ]
}
```

`inicio`, `fim`, `linha` e `trecho` só aparecem quando o achado tem posição no texto. `inicio` e `fim` são índices de caractere (ponto de código) no texto já normalizado (ver "Leitura do arquivo").

## Como rodar os testes

```bash
python3 -m unittest discover -s tests -v
```

Na entrega: 74 testes, cobrindo casos positivos, negativos e extremos de cada regra, a validação dos TOML, a CLI e uma checagem que falha se o pacote `shiba/` importar algo fora da biblioteca padrão ou um módulo de rede.

## Limitações conhecidas

### Detecção de números (`numero_sem_fato`)

1. **Números por extenso não são detectados.** "três mil clientes", "o dobro", "metade" passam sem cobrança. Esta é a lacuna mais importante: um texto pode fazer uma afirmação numérica sem algarismos.
2. **Afirmações factuais sem número não são detectadas** ("somos líderes", "a primeira da cidade"). Hoje, só a lista de palavras proibidas cobre isso, e apenas de forma parcial.
3. **Ambiguidade de separadores.** "1.500" é sempre lido como mil e quinhentos (pt-BR). Um texto em convenção en-US ("1.5") é lido como 1,5 só quando não segue o padrão de milhar. "1,500,000" vira comparação literal.
4. **Números colados a letras são cobrados de propósito** ("covid19", "4K", "iPhone 15"). Isso gera falsos positivos em nomes de produto; até existir um cadastro de exceções, registre-os como fato.
5. **Números estruturais também são cobrados.** "3 erros que…" exige fato, embora "3" seja só a contagem de itens do post. O briefing por peça (Incremento 1) deve resolver isso.
6. **Ignorados por desenho:** números dentro de hashtags, @menções, URLs e e-mails; enumeração no início da linha ("1. ", "2) "); emoji de tecla (1️⃣).
7. **Sinal negativo e unidades não são considerados.** "-5" vira 5; "24" casa com o fato "24" seja ele horas ou dias.
8. **Datas e horas** ("23/10", "18h30") são comparadas literalmente: "23/10" não casa com "23/10/2026".
9. **Comparação por valor, não por contexto.** Se existe um fato com "24", qualquer "24" da legenda passa, mesmo que se refira a outra coisa.
10. **Status `fornecido` é aceito sem aviso** neste protótipo. A distinção entre fornecido e verificado, com o aviso que exige reconhecimento, é o Incremento 1.

### Limites de plataforma (`limite_caracteres`)

1. **O limite do Instagram (2.200) NÃO está verificado.** O valor veio do código do projeto auditado instagram-skills, não da documentação oficial da Meta. Por isso o status é `a_verificar` e o excesso gera **só aviso**.
2. **A contagem é por ponto de código Unicode** (`len()` do Python). A plataforma pode contar emoji compostos, modificadores de tom de pele e quebras de linha de outro jeito. Não há confirmação de como ela conta.
3. **O limite do texto antes do "mais"** e os limites de TikTok e YouTube Shorts ainda não existem (Incremento 2).
4. **Nenhum limite muda sozinho.** Se a plataforma mudar uma regra, o arquivo TOML precisa ser atualizado e verificado por uma pessoa.

### Hashtags

1. **A faixa mínima e máxima é configuração do cliente**, não recomendação de desempenho.
2. **Hashtag é `#` seguido de letras, dígitos ou `_`.** "C#", "#" solto e âncoras de URL não contam. Hashtags só de dígitos (#2026) contam, embora a plataforma possa tratá-las de outro jeito.
3. **Não há verificação** de existência, popularidade ou adequação da hashtag.

### Palavras proibidas

1. **Flexões não são detectadas.** "garantido" não pega "garantida" nem "garantidos"; cada forma precisa ser cadastrada. Na legenda de demonstração, "GARANTIDA" passou e só "garantido" foi bloqueado.
2. **Sinônimos e paráfrases não são detectados.**

### Leitura do arquivo

1. **O arquivo inteiro é a legenda.** Não há frontmatter nem metadados.
2. Espaços e quebras de linha no início e no fim são removidos, e `\r\n` vira `\n` antes da contagem.
3. O arquivo precisa estar em UTF-8 e ter no máximo 64 KiB.

### Escopo

- **Só clientes fictícios:** o motor recusa `perfil.toml` sem `ficticio = true`.
- **Fora do protótipo:** aprovação, publicação, integrações, rede, LLM, skills, `SHIBA_DADOS`, TikTok e Shorts.
- **"passou" não é aprovação humana.**
