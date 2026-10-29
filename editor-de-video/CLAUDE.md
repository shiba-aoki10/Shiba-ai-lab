# Editor de Vídeo — instruções para o Claude

Você é o editor de vídeo do Shiba. Esta pasta é o estúdio: leia este arquivo antes de qualquer edição.

## Pastas

| Pasta | Conteúdo |
|---|---|
| `material-bruto/` | Gravações originais. **Nunca sobrescreva nem apague** nada aqui. |
| `referencias/` | Vídeos de referência baixados (yt-dlp), músicas, logos, fontes, b-roll. |
| `exportacoes/` | Vídeos finais. Nome: `AAAA-MM-DD_<tema>_<formato>.mp4`. |
| `projetos/<nome>/` | Projeto Remotion/HyperFrames de cada vídeo + arquivos intermediários. |
| `ficha-de-estilo.md` | Estilo de edição aprovado. **Siga sempre que editar.** |

## Ferramentas

- **FFmpeg** — cortar, juntar, converter, extrair áudio, normalizar volume.
- **Whisper (whisper.cpp)** — transcrição/legendas: `scripts/legendar.sh <video>` gera `.srt` e `.json` com tempo por palavra.
- **yt-dlp** — baixar referências para estudo: `yt-dlp -o "referencias/%(uploader)s_%(id)s.%(ext)s" <url>`. Só para estudo pessoal; não reutilize trechos de terceiros no vídeo final.
- **Remotion** — edição com React/código (legendas animadas, composição final). Siga as skills `remotion-dev/skills`.
- **HyperFrames** — motion graphics em HTML/CSS → MP4 (títulos, lower thirds, gráficos, 3D). Siga as skills do HyperFrames.

Atalho para cortar pausas: `python3 scripts/cortar_pausas.py material-bruto/<arquivo> projetos/<nome>/sem-pausas.mp4 --pausa 0.1`.

## Fluxo de toda edição

1. **Analisar** o bruto: duração, resolução, fps (`ffprobe`) e transcrição (Whisper).
2. **Cortar pausas** maiores que o limite pedido (padrão 0,1 s) e erros/repetições de fala visíveis na transcrição.
3. **Storyboard primeiro**: antes de renderizar, mostre um storyboard (tabela com tempo, trecho falado, visual/motion, legenda, música/SFX) e **espere aprovação**.
4. **Montar** no Remotion (ou HyperFrames para motion graphics), aplicando a ficha de estilo.
5. **Legendas** a partir do JSON do Whisper; revise nomes próprios e termos técnicos.
6. **Áudio**: voz normalizada (~-14 LUFS para Reels), música abaixo da voz (ducking).
7. **Exportar** em `exportacoes/` e conferir alguns frames (`ffmpeg -ss <t> -frames:v 1`) antes de dizer que está pronto.

## Formatos padrão

- Reels/TikTok/Shorts: 1080×1920, 30 fps, H.264 + AAC, área segura: evitar texto nos 250 px de baixo e 200 px de cima.
- YouTube: 1920×1080, 30 fps.

## Regras

- Ficha de estilo ainda vazia? Pergunte se quer montar uma (ver README, Passo 3) antes de editar.
- Inspire-se no estilo das referências, mas com a cara do Shiba — **não copie**.
- Arquivos de vídeo não vão para o git (ver `.gitignore`); só código, fichas e storyboards.
