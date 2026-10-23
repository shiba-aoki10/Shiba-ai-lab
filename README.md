# Shiba-ai-lab
Laboratório privado de desenvolvimento de agentes de IA, automações, produção audiovisual e marketing digital.

## Estado atual

Fase 1, protótipo do motor editorial `shiba`: verificação local de legendas, só com Python 3.11+ e a biblioteca padrão (sem dependências, sem rede, sem credenciais).

| Incremento | Conteúdo | Documento |
|---|---|---|
| 0 | `shiba verificar`: hashtags, palavras proibidas, número sem fato, limite de caracteres | [`docs/fase-1/INCREMENTO-0.md`](docs/fase-1/INCREMENTO-0.md) |
| 1 | Registro de fatos (fornecido, verificado, expirado, contestado), vínculo por valor, unidade e contexto, números por extenso, afirmações sensíveis, `fontes.md` | [`docs/fase-1/INCREMENTO-1.md`](docs/fase-1/INCREMENTO-1.md) |

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

# testes
python3 -m unittest discover -s tests
```

Códigos de saída: `0` passou, `1` bloqueado, `2` erro de uso ou configuração.

> **"passou" não é aprovação.** O verificador aplica regras automáticas e heurísticas. Ele não garante que um texto seja verdadeiro, e a aprovação humana é sempre obrigatória.

## Estrutura

```
shiba/                motor (Python, biblioteca padrão)
plataformas/          limites de plataforma, com status, fonte e data
modelos/clientes/     clientes FICTÍCIOS de demonstração
tests/                testes unittest e fixtures sintéticas
docs/                 auditoria, especificação e documentação de cada incremento
```

Dados reais de clientes **não** entram neste repositório (ver a especificação, seções 3.2 e 9).
