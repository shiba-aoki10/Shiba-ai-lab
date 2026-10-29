#!/usr/bin/env python3
"""Corta as pausas (silêncios) de um vídeo usando FFmpeg.

Uso:
    python3 scripts/cortar_pausas.py material-bruto/video.mp4 [saida.mp4]
        [--pausa 0.1] [--ruido -30] [--margem 0.05]

--pausa   duração mínima (s) de silêncio para cortar (padrão 0.1)
--ruido   limiar de silêncio em dB (padrão -30; ambiente barulhento: -25)
--margem  respiro (s) mantido antes/depois de cada fala (padrão 0.05)
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile


def duracao(arquivo):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", arquivo],
        capture_output=True, text=True, check=True,
    ).stdout
    return float(out.strip())


def detectar_silencios(arquivo, ruido, pausa):
    log = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", arquivo,
         "-af", f"silencedetect=noise={ruido}dB:d={pausa}", "-f", "null", "-"],
        capture_output=True, text=True,
    ).stderr
    inicios = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", log)]
    fins = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", log)]
    return list(zip(inicios, fins + [None] * (len(inicios) - len(fins))))


def trechos_com_fala(silencios, total, margem):
    trechos, cursor = [], 0.0
    for ini, fim in silencios:
        fim = total if fim is None else fim
        corte_ini = max(ini + margem, cursor)
        if corte_ini > cursor:
            trechos.append((cursor, corte_ini))
        cursor = max(fim - margem, corte_ini)
    if cursor < total:
        trechos.append((cursor, total))
    return [(a, b) for a, b in trechos if b - a > 0.02]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("entrada")
    p.add_argument("saida", nargs="?")
    p.add_argument("--pausa", type=float, default=0.1)
    p.add_argument("--ruido", type=float, default=-30)
    p.add_argument("--margem", type=float, default=0.05)
    a = p.parse_args()

    saida = a.saida or os.path.splitext(a.entrada)[0] + "_sem-pausas.mp4"
    total = duracao(a.entrada)
    trechos = trechos_com_fala(detectar_silencios(a.entrada, a.ruido, a.pausa), total, a.margem)
    if not trechos:
        sys.exit("Nenhuma fala detectada — tente um --ruido menor (ex.: -40).")

    partes = []
    for i, (ini, fim) in enumerate(trechos):
        partes.append(f"[0:v]trim={ini:.3f}:{fim:.3f},setpts=PTS-STARTPTS[v{i}];")
        partes.append(f"[0:a]atrim={ini:.3f}:{fim:.3f},asetpts=PTS-STARTPTS[a{i}];")
    entradas = "".join(f"[v{i}][a{i}]" for i in range(len(trechos)))
    partes.append(f"{entradas}concat=n={len(trechos)}:v=1:a=1[v][a]")

    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write("\n".join(partes))
        script = f.name
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", a.entrada,
             "-filter_complex_script", script, "-map", "[v]", "-map", "[a]",
             "-c:v", "libx264", "-crf", "18", "-preset", "medium",
             "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", saida],
            check=True,
        )
    finally:
        os.unlink(script)

    final = sum(b - a for a, b in trechos)
    print(f"{len(trechos)} trechos mantidos · {total:.1f}s → {final:.1f}s "
          f"({total - final:.1f}s de pausas removidas)\n→ {saida}")


if __name__ == "__main__":
    main()
