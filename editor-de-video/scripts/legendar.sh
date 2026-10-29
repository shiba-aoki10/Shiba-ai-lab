#!/usr/bin/env bash
# Gera legendas (SRT + JSON com tempo por palavra) com whisper.cpp.
# Uso: scripts/legendar.sh material-bruto/video.mp4 [idioma=pt]
set -euo pipefail

VIDEO="${1:?Uso: scripts/legendar.sh <video> [idioma]}"
IDIOMA="${2:-pt}"
MODELO="${WHISPER_MODEL:-$HOME/.cache/whisper/ggml-large-v3-turbo.bin}"
BASE="${VIDEO%.*}"

BIN="$(command -v whisper-cli || command -v whisper-cpp || true)"
[ -n "$BIN" ] || { echo "whisper.cpp não encontrado — rode scripts/instalar.sh"; exit 1; }
[ -f "$MODELO" ] || { echo "Modelo não encontrado em $MODELO — rode scripts/instalar.sh"; exit 1; }

WAV="$(mktemp -t legenda.XXXXXX).wav"
trap 'rm -f "$WAV"' EXIT
# whisper.cpp exige WAV 16 kHz mono
ffmpeg -y -hide_banner -loglevel error -i "$VIDEO" -ar 16000 -ac 1 -c:a pcm_s16le "$WAV"

"$BIN" -m "$MODELO" -f "$WAV" -l "$IDIOMA" -osrt -ojf -of "$BASE"
echo "→ $BASE.srt"
echo "→ $BASE.json (tempo por palavra, para legendas animadas)"
