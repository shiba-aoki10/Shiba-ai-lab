# Shiba-ai-lab
Laboratório privado de desenvolvimento de agentes de IA, automações, produção audiovisual e marketing digital.

## Estado atual

Fase 1, protótipo do motor editorial `shiba`: verificação local de legendas, só com Python 3.11+ e a biblioteca padrão (sem dependências, sem rede, sem credenciais).

| Incremento | Conteúdo | Documento |
|---|---|---|
| 0 | `shiba verificar`: hashtags, palavras proibidas, número sem fato, limite de caracteres | [`docs/fase-1/INCREMENTO-0.md`](docs/fase-1/INCREMENTO-0.md) |
| 1 | Registro de fatos (fornecido, verificado, expirado, contestado), vínculo por valor, unidade e contexto, números por extenso, afirmações sensíveis, `fontes.md` | [`docs/fase-1/INCREMENTO-1.md`](docs/fase-1/INCREMENTO-1.md) |
| 2 | Herança padrão → segmento → cliente (com ajustes por plataforma), perfis de Instagram, TikTok e YouTube Shorts sem limites inventados, isolamento de dados reais fora do Git | [`docs/fase-1/INCREMENTO-2.md`](docs/fase-1/INCREMENTO-2.md) |

Visão geral e próximos passos: [`docs/fase-1/ESPECIFICACAO-MVP.md`](docs/fase-1/ESPECIFICACAO-MVP.md).

## Uso rápido

```bash
# verificar uma legenda (clientes fictícios em modelos/clientes/)
python3 -m shiba verificar tests/fixtures/sinteticos/legenda_passa.md \
    --cliente exemplo --plataforma instagram

# laudo em JSON, data fixa para validade dos fatos e trilha de fontes
python3 -m shiba verificar tests/fixtures/sinteticos/academia_passa.md \
    --cliente exemplo-academia --plataforma instagram \
    --formato json --data-referencia 2026-10-23 --fontes /tmp/fontes.md

# configuração efetiva após a herança, com a origem de cada valor
python3 -m shiba config mostrar --cliente exemplo-cafe --plataforma tiktok

# dados reais: só com --dados, e só fora de qualquer repositório Git
python3 -m shiba dados verificar ~/ShibaDados
python3 -m shiba verificar ~/ShibaDados/producao/peca.md \
    --cliente <id> --plataforma instagram --dados ~/ShibaDados

# testes
python3 -m unittest discover -s tests
```

Códigos de saída: `0` passou, `1` bloqueado, `2` erro de uso ou configuração.

> **"passou" não é aprovação.** O verificador aplica regras automáticas e heurísticas. Ele não garante que um texto seja verdadeiro, e a aprovação humana é sempre obrigatória.

## Estrutura

```
shiba/                motor (Python, biblioteca padrão)
plataformas/          limites de plataforma (_padrao + instagram, tiktok, youtube-shorts)
modelos/padrao.toml   camada padrão da herança (neutra)
modelos/segmentos/    segmentos genéricos de demonstração
modelos/clientes/     clientes FICTÍCIOS de demonstração
tests/                testes unittest e fixtures sintéticas
docs/                 auditoria, especificação e documentação de cada incremento
```

Dados reais de clientes **não** entram neste repositório (ver a especificação, seções 3.2 e 9).
