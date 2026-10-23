# Incremento 2: herança de configuração e isolamento de dados

| Campo | Valor |
|---|---|
| Status | Implementado. O Incremento 3 **não** foi autorizado. |
| Especificação | [`ESPECIFICACAO-MVP.md`](ESPECIFICACAO-MVP.md), seções 3.2, 4 e 7 |
| Requisitos | Python 3.11+, só biblioteca padrão, sem rede, sem credenciais |
| Dados | Só fictícios. Nenhum dado real foi usado; os testes de "dados reais" usam conteúdo fictício em pastas temporárias |

## 1. Herança: padrão → segmento → cliente

### Onde fica cada camada

| Camada | Arquivo | Versionado? |
|---|---|---|
| Padrão | `modelos/padrao.toml` | sim (genérico, neutro) |
| Segmento | `modelos/segmentos/<id>.toml` (`gastronomia`, `fitness`) | sim (genérico) |
| Cliente fictício | `modelos/clientes/<id>/perfil.toml` | sim (`ficticio = true` obrigatório) |
| Cliente real | `<dados>/clientes/<id>/perfil.toml` | **não**: fora do Git (seção 3) |

O cliente escolhe o segmento com `segmento = "<id>"`. O padrão e os segmentos vêm **sempre** dos modelos versionados, porque são genéricos e não contêm dados de cliente.

### Ordem de aplicação

Para um cliente numa plataforma P:

```
padrão → padrão@P → segmento → segmento@P → cliente → cliente@P
```

`@P` é a tabela `[plataformas.P]` dentro da própria camada. Com essa ordem, o ajuste **geral** do cliente vence o ajuste por plataforma do **segmento**, porque quem decide é o cliente. Já o ajuste do cliente para P vence tudo.

### Regras de substituição

| Situação | Regra |
|---|---|
| Tabela (`[hashtags]`) | mesclada chave a chave, recursivamente |
| Valor simples (número, texto, booleano) | a camada mais específica **substitui** |
| Lista | **somada** à herdada, sem repetir (comparação sem maiúsculas, acentos e `#`); herdados primeiro |
| `chave__substituir = [...]` | troca a lista herdada inteira (`[]` esvazia) |
| `chave__remover = [...]` | tira itens da lista herdada; depois entram os itens de `chave` da mesma camada |
| `chave` e `chave__substituir` na mesma camada | **erro** (ambíguo) |
| Chave ausente | herda da camada anterior |
| Campo obrigatório ausente em **todas** as camadas | **erro**: nenhum valor é suposto |
| Tipos diferentes entre camadas (lista × texto) | **erro** |
| Chave desconhecida (ex.: `[palavras_proibida]`) | **erro**: um erro de digitação não pode desligar uma regra em silêncio |
| `[plataformas.X]` com X sem perfil (ex.: `tiktk`) | **erro** |
| Identidade (`id`, `nome`, `ficticio`, `segmento`) | **nunca** herdada: só vale no arquivo do próprio cliente |

Não há como "apagar" um valor simples, porque o TOML não tem nulo. Só dá para sobrescrevê-lo.

### Exemplo funcionando: `exemplo-cafe` (fictício)

O segmento `gastronomia` define hashtags 3–5, proíbe `#sigam` e `#likeforlike` e os termos `milagr*`, `light` e `detox`. No TikTok, o máximo do segmento é 4. O cliente:

```toml
segmento = "gastronomia"
[hashtags]
minimo = 2
maximo = 4
proibidas = ["#cafezinho"]
[palavras_proibidas]
termos__remover = ["light"]
termos = ["barato"]
[plataformas.tiktok.hashtags]
maximo = 3
[plataformas.tiktok.palavras_proibidas]
termos = ["promoção"]
[plataformas.youtube-shorts.hashtags]
minimo = 0
proibidas__substituir = ["#shorts"]
```

Resultado (`python3 -m shiba config mostrar --cliente exemplo-cafe --plataforma <P>`):

| Plataforma | Hashtags (mín–máx) | Hashtags proibidas | Termos proibidos |
|---|---|---|---|
| Instagram | 2–4 | #sigam, #likeforlike, #cafezinho | milagr*, detox, barato |
| TikTok | 2–**3** (de `cliente@tiktok`) | #sigam, #likeforlike, #cafezinho | milagr*, detox, barato, **promoção** |
| YouTube Shorts | **0**–4 | **#shorts** (lista substituída) | milagr*, detox, barato |

O `config mostrar` também lista a origem de cada valor, por exemplo `"hashtags.maximo": "cliente@tiktok"` e `"detox": "segmento:gastronomia"`.

**Compatibilidade:** o padrão é neutro, então os clientes `exemplo` e `exemplo-academia` têm exatamente a mesma configuração efetiva de antes. Há teste para isso.

## 2. Plataformas: Instagram, TikTok e YouTube Shorts

- `plataformas/_padrao.toml` declara **quais** limites existem (`legenda_max_caracteres`, `duracao_max_segundos`), **sem valor** e com status `a_verificar`. Cada perfil herda dele.
- **Instagram:** mantém o valor preliminar 2.200, `a_verificar`, com origem registrada (código do instagram-skills, não fonte oficial).
- **TikTok e YouTube Shorts:** **nenhum valor**. Nenhum limite foi verificado em fonte oficial e nenhum número foi inventado. Há um teste que falha se um valor aparecer nesses perfis sem origem.
- **Limite sem valor:** não é aplicado. O laudo diz "não tem limite de caracteres definido; o tamanho não foi verificado" (info). Legenda vazia continua bloqueando.
- **Shorts:** `texto_principal = "descricao"` registra que o texto verificado é a descrição do vídeo. Por enquanto, essa informação é só documental.
- **Valores aceitos:** `valor` sem status `verificado` só gera aviso; `verificado` exige valor, fonte e data de consulta.

## 3. Isolamento de dados reais

### Separação

| O quê | Onde |
|---|---|
| Código, padrão, segmentos, clientes fictícios, testes | repositório (Git) |
| Clientes reais, fatos reais, rascunhos e relatórios reais | diretório de dados **fora** de qualquer repositório |

Os dados reais só são usados com a opção **explícita** `--dados DIR`, ou `--dados` sem argumento, que lê a variável `SHIBA_DADOS`. Sem essa opção, o motor só enxerga os clientes fictícios. A variável de ambiente **sozinha não ativa nada**, para que um terminal configurado não troque a origem dos dados sem você perceber.

### Detecção de repositório

Antes de usar dados reais, o motor recusa (código de saída 2) quando:
- o diretório de dados está num repositório Git, em **qualquer nível acima**: há `.git` como pasta, `.git` como arquivo (worktree ou submódulo) ou um repositório "nu";
- o mesmo vale para o caminho **real**: links simbólicos e `..` são resolvidos e as duas formas são conferidas;
- o diretório está dentro do código do Shiba, mesmo que o código tenha sido exportado sem `.git`;
- `GIT_DIR` ou `GIT_WORK_TREE` estão definidas no ambiente;
- alguma pasta do caminho não pode ser inspecionada (recusa conservadora);
- o diretório não existe ou não é uma pasta.

Com `--dados`, a mesma checagem vale para **tudo o que contém ou recebe conteúdo real**: o arquivo da legenda, o `--fatos-peca` e o destino do `--fontes`. Assim, um relatório com dados reais não pode ser gravado dentro de um repositório.

`python3 -m shiba dados verificar [DIR]` confere um diretório **sem listar o conteúdo** e avisa se outros usuários do sistema podem acessá-lo (sugere `chmod 700`).

### Sem vazamento

- Com `--dados`, as mensagens de erro mostram `<dados>/clientes/<id>/...`, nunca o caminho real.
- Erros de campo dizem o **nome** do campo, não o valor. O erro de TOML inválido diz linha e coluna, não o conteúdo.
- O motor não grava logs nem arquivos temporários. Ele só grava o que você pede (`--fontes`), e só fora do Git quando houver dados reais.
- O laudo não inclui os dados do perfil (como o nome do cliente).
- Há testes com um marcador sigiloso em perfis "reais" fictícios, confirmando que ele não aparece em nenhuma saída de erro, e um retrato do diretório de dados antes e depois, confirmando que nada é criado ou alterado.

## Testes

```bash
python3 -m unittest discover -s tests -v
```

Resultado: **238 testes: 237 OK e 1 pulado.**
- Os **162 testes anteriores passam sem nenhuma alteração.**
- 76 novos: `test_heranca.py` (18), `test_config_heranca.py` (25), `test_isolamento.py` (33).
- **O pulado** é `test_pasta_sem_permissao_e_recusada`. O ambiente de desenvolvimento roda como *root*, e o root ignora permissões de pasta. Num usuário comum, o teste roda.

## Limitações e riscos restantes

1. **A detecção de repositório procura marcadores** (`.git`, repositório nu). Ela **não executa o Git**. Ficam de fora casos exóticos, como `core.worktree` configurado em outro lugar, repositório com `.git` renomeado ou outro sistema de versão (Mercurial, SVN). O risco não é zero, mas é baixo.
2. **Sincronização em nuvem não é detectada.** Pastas do Dropbox, Google Drive ou OneDrive estão "fora do Git" e são aceitas, mas copiam os dados para terceiros. A escolha do diretório é responsabilidade de quem configura.
3. **A saída que você pede é conteúdo real.** O laudo impresso no terminal (trechos da legenda) e o `fontes.md` contêm conteúdo real. Redirecionar a saída para um arquivo dentro de um repositório (`> repo/laudo.txt`) não é algo que o motor consiga impedir.
4. **Corrida de tempo (TOCTOU).** A checagem acontece antes da leitura e da gravação. Se alguém mover pastas no intervalo, a checagem pode ficar desatualizada. É aceitável para uso local de uma pessoa.
5. **Permissões só no POSIX:** no Windows, o aviso de diretório acessível a outros usuários não é emitido.
6. **O conteúdo dos segmentos genéricos é de demonstração.** Faixas de hashtags e termos não são recomendação de desempenho e precisam de revisão editorial antes do uso real.
7. **Limites de plataforma continuam sem fonte oficial.** O Instagram tem só o valor preliminar; TikTok e Shorts, nenhum. Enquanto ninguém registrar as fontes, o tamanho do texto não é controlado nessas plataformas.
8. **A ordem "cliente geral vence segmento@plataforma" é uma decisão de projeto.** Se o segmento precisar impor algo a todos os clientes numa plataforma, hoje não há como "travar" um valor.
