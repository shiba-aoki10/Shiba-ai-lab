#!/usr/bin/env bash
# Instala as 5 ferramentas do editor de vídeo (macOS com Homebrew ou Linux com apt).
#   1. Remotion      github.com/remotion-dev/remotion   (via npx, sem instalação global)
#   2. HyperFrames   github.com/heygen-com/hyperframes  (via npx + skills do Claude Code)
#   3. FFmpeg        github.com/FFmpeg/FFmpeg
#   4. Whisper       github.com/ggml-org/whisper.cpp
#   5. yt-dlp        github.com/yt-dlp/yt-dlp
set -euo pipefail
cd "$(dirname "$0")/.."

ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
falha(){ printf '  \033[31m✗\033[0m %s\n' "$1"; }

echo "== Instalando dependências =="
if command -v brew >/dev/null; then
  brew install ffmpeg yt-dlp whisper-cpp node
elif command -v apt-get >/dev/null; then
  sudo apt-get update
  sudo apt-get install -y ffmpeg python3-pip pipx nodejs npm cmake build-essential git
  pipx install yt-dlp || pip3 install --user -U yt-dlp
  if ! command -v whisper-cli >/dev/null; then
    git clone --depth 1 https://github.com/ggml-org/whisper.cpp "$HOME/.local/src/whisper.cpp"
    cmake -S "$HOME/.local/src/whisper.cpp" -B "$HOME/.local/src/whisper.cpp/build" -DCMAKE_BUILD_TYPE=Release
    cmake --build "$HOME/.local/src/whisper.cpp/build" -j --config Release
    mkdir -p "$HOME/.local/bin"
    ln -sf "$HOME/.local/src/whisper.cpp/build/bin/whisper-cli" "$HOME/.local/bin/whisper-cli"
  fi
else
  echo "Instale manualmente: ffmpeg, yt-dlp, whisper.cpp e Node 22+."; exit 1
fi

echo "== Baixando modelo do Whisper (large-v3-turbo, ~1,6 GB) =="
MODELO="$HOME/.cache/whisper/ggml-large-v3-turbo.bin"
if [ ! -f "$MODELO" ]; then
  mkdir -p "$(dirname "$MODELO")"
  curl -L --fail -o "$MODELO" \
    https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin
fi

echo "== Skills de vídeo para o Claude Code =="
npx -y hyperframes skills update || true
npx -y skills add remotion-dev/skills || true

echo "== Testando cada ferramenta =="
command -v ffmpeg  >/dev/null && ok "FFmpeg  $(ffmpeg -version | head -1 | cut -d' ' -f3)" || falha "FFmpeg"
command -v yt-dlp  >/dev/null && ok "yt-dlp  $(yt-dlp --version)" || falha "yt-dlp"
{ command -v whisper-cli || command -v whisper-cpp; } >/dev/null && [ -f "$MODELO" ] \
  && ok "Whisper (whisper.cpp + modelo)" || falha "Whisper"
NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
[ "$NODE_MAJOR" -ge 22 ] && ok "Node $(node -v) (Remotion + HyperFrames via npx)" \
  || falha "Node 22+ é necessário para HyperFrames (atual: $(node -v 2>/dev/null || echo nenhum))"
npx -y hyperframes --version >/dev/null 2>&1 && ok "HyperFrames" || falha "HyperFrames"
npx -y @remotion/cli --version >/dev/null 2>&1 && ok "Remotion" || falha "Remotion"

echo
echo "Pronto. Abra o Claude Code nesta pasta (editor-de-video) e siga o README."
