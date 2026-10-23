# Perfis futuros: Médicos do Brasil, VTC e LNTD

| Campo | Valor |
|---|---|
| Status | **Arquitetura preparada. Nenhum dado cadastrado.** |
| Incremento | 3D |
| Regra | Nenhuma regra específica destes clientes foi presumida. Nada aqui afirma o que é permitido ou proibido. |

## O que já existe

| Cliente futuro | Segmento genérico | O que o segmento faz |
|---|---|---|
| Médicos do Brasil | `saude` | Liga a validação normativa: toda afirmação de saúde (mesmo apoiada em fato verificado) e todo tema da lista `validacao/saude.toml` gera aviso `validacao_normativa`; status de aprovação no calendário exige `validado_por`; o laudo nunca passa de `aguardando_validacao_normativa`. Sugere 2 aprovações (decisão do cliente no Incremento 4). |
| VTC | `social` | Só estrutura. Nenhuma validação ligada até o cliente definir. |
| LNTD | `esportivo` | Só estrutura. Nenhuma validação ligada até o cliente definir. |

Os três segmentos estão em `modelos/segmentos/`. São genéricos e versionados. Os **clientes reais nunca entram no repositório**: eles vivem no diretório de dados (`--dados`), fora de qualquer Git, com `ficticio = false`.

## Como um cliente real entra (quando autorizado)

1. Registrar a autorização de uso de dados (especificação, seção 9).
2. Criar `<dados>/clientes/<id>/perfil.toml` com `segmento = "saude" | "social" | "esportivo"` e as escolhas do cliente.
3. Criar `<dados>/clientes/<id>/fatos.toml` com fatos **fornecidos pelo cliente**, com fonte. Verificar o que for sensível.
4. Conferir com `python3 -m shiba dados verificar` e `python3 -m shiba config mostrar --cliente <id> --dados`.

## Questionário para o cliente

O cliente (ou o responsável dele) responde. Nada disso deve ser preenchido por suposição.

### Para todos

| Tema | Pergunta | Onde entra |
|---|---|---|
| Plataformas | Em quais redes o cliente publica? | `[plataformas.<id>]` ajustes |
| Hashtags | Faixa desejada por plataforma? Hashtags proibidas? | `[hashtags]` |
| Vocabulário | Palavras e expressões proibidas ou que exigem revisão? | `[palavras_proibidas]`, `[editorial] termos_extras` |
| Estilo | Preferências de tamanho de frase, tom, uso de caixa alta? | `[editorial]` |
| Equipe | Quais **papéis** existem (sem nomes no repositório)? Quem aprova? Quem valida normas? | `[equipe]` |
| Aprovação | Quantas aprovações por tipo de peça? | `[revisao] aprovacoes_sugeridas` (Incremento 4) |
| Fatos | Quais números, datas e afirmações podem ser usados? Qual a fonte de cada um? | `fatos.toml` |
| Roteiros | Taxa de fala calibrada a partir de vídeos autorizados? Janela do gancho? | `[roteiro]` |
| Calendário | Pilares editoriais, carga máxima por papel e por dia? | `[calendario]` |

### Médicos do Brasil (saúde)

| Pergunta | Onde entra |
|---|---|
| Quem é o responsável competente para validar as peças (papel, não nome)? | `[equipe] validadores_normativos` |
| Quais normas, códigos de ética, regulamentos ou políticas internas se aplicam? Com qual fonte oficial e data de consulta? | `[normas] referencias` (status `a_verificar` até a confirmação) |
| Os temas da lista `validacao/saude.toml` cobrem o que o cliente precisa revisar? Faltam temas? | lista própria aprovada pelo cliente |
| Há temas que o cliente não publica em hipótese alguma? | `[palavras_proibidas]` (bloqueio) |
| Como tratar depoimentos, imagens de pacientes, preços e especialidades? | definição do cliente, validada pelo responsável |

> O Shiba **não decide** essas respostas. O papel do motor é sinalizar e exigir que a pessoa competente valide e registre a validação.

### VTC (social)

| Pergunta | Onde entra |
|---|---|
| Há temas sensíveis (doações, beneficiários, menores de idade, prestação de contas, parcerias)? | lista de validação própria (`validacao/<nome>.toml`), ligada em `[revisao] listas_validacao` |
| Algum tema exige validação jurídica ou institucional antes de publicar? | `[revisao] exige_validacao_normativa`, `validadores_normativos` |
| Como tratar imagens de pessoas atendidas? | definição do cliente |

### LNTD (esportivo)

| Pergunta | Onde entra |
|---|---|
| Há patrocinadores, marcas ou temas de comunicação restrita? | `[palavras_proibidas]`, lista de validação própria |
| Resultados esportivos, estatísticas e recordes: qual a fonte oficial? | `fatos.toml` com fonte e verificação |
| Uso de imagem de atletas: quem autoriza? | `[equipe]`, validação |
| Algum tema exige validação jurídica (ex.: apostas, suplementos)? | `[revisao]` |

## Separação técnica × normativa

| Natureza | Quem resolve | Exemplos |
|---|---|---|
| `tecnica` | o próprio motor confere | número sem fato, fato sem fonte, cena sobreposta, peça aprovada sem `aprovado_por` |
| `revisao_humana` | qualquer revisor editorial | clichê, frase longa, gancho só visual, vínculo ambíguo |
| `validacao_normativa` | **somente** o responsável competente do cliente | afirmação de saúde, "antes e depois", depoimento, medicamento, preço de serviço de saúde |

O motor **nunca** transforma um alerta normativo em "permitido" ou "proibido". Ele só exige a validação e registra quem a fez (registro declarativo até o Incremento 4).
