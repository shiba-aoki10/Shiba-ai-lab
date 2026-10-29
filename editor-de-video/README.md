# Editor de Vídeo IA

Estúdio para editar vídeos com o Claude Code usando Remotion, HyperFrames, FFmpeg, Whisper e yt-dlp.

## Passo 1 · A estrutura

No seu computador, clone o repositório e abra o Claude Code **nesta pasta** (`editor-de-video`). No app: chat novo → **Local** → escolha a pasta. O Claude lê o `CLAUDE.md` daqui e já sabe como trabalhar.

```
editor-de-video/
├── material-bruto/   ← solte suas gravações aqui
├── referencias/      ← vídeos de referência, músicas, logos
├── exportacoes/      ← vídeos finais
├── projetos/         ← criado pelo Claude, um por vídeo
├── ficha-de-estilo.md
└── scripts/
```

## Passo 2 · As ferramentas

Rode uma vez (macOS com Homebrew ou Linux):

```bash
bash scripts/instalar.sh
```

Ou peça ao Claude:

> Quero que você seja meu editor de vídeo. Roda `scripts/instalar.sh`, testa cada ferramenta e me avisa quando estiver tudo pronto.

## Passo 3 · O seu estilo

Mande de 3 a 5 vídeos (de outro criador ou seus):

> Aprende o estilo de edição desses vídeos: [LINK 1] [LINK 2] [LINK 3]
> 1. Baixa cada um na pasta `referencias/`.
> 2. Estuda o que eles têm em comum: fontes, cores e legendas; cortes, zooms e ritmo; motion graphics, música e som.
> 3. Preenche a `ficha-de-estilo.md` pra eu revisar. Com a minha cara, não uma cópia.
>
> Quando eu aprovar, segue ela toda vez que editar pra mim.

## Passo 4 · Grava e manda editar

Solte o arquivo em `material-bruto/` e cole:

> Edita o meu vídeo novo e transforma num Reel do Instagram: [NOME DO ARQUIVO], na pasta `material-bruto/`.
> 1. Corta toda pausa maior que 0,1 segundo.
> 2. Segue a minha ficha de estilo.
> 3. Coloca legenda, música e motion graphics.
> 4. Usa o que tiver na pasta `referencias/`.
>
> Me mostra um storyboard pra revisar primeiro e depois exporta em `exportacoes/`.

## Scripts prontos

| Script | O que faz |
|---|---|
| `scripts/instalar.sh` | Instala e testa as 5 ferramentas + skills do Remotion e HyperFrames |
| `scripts/cortar_pausas.py <video> [saida] --pausa 0.1` | Remove silêncios (ajuste `--ruido -25` se o ambiente for barulhento) |
| `scripts/legendar.sh <video> [pt]` | Gera `.srt` e `.json` (tempo por palavra) com Whisper |

## Observações

- Rode localmente: renderizar vídeo precisa de CPU/GPU e dos seus arquivos, então a sessão na nuvem não serve para isso.
- HyperFrames precisa de Node 22+.
- Remotion é gratuito para pessoas físicas e empresas com até 3 funcionários; acima disso exige licença.
- yt-dlp: baixe referências só para estudo; não publique trechos de vídeos de outras pessoas.
