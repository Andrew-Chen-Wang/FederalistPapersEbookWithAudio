#!/bin/bash
# Download audio (AAC m4a) and English auto-captions (json3 + vtt) for the
# Federalist Papers playlist, one file set per paper, named fedNN by playlist index.
set -uo pipefail
cd "$(dirname "$0")/.."
PLAYLIST="https://www.youtube.com/playlist?list=PLri6XX7fEjPDOu5k5O83qNAusvT0thNcE"
mkdir -p audio captions

.venv/bin/yt-dlp \
  -f "140/bestaudio[ext=m4a]/bestaudio" \
  --write-auto-subs --sub-langs "en-orig" --sub-format "json3" \
  --sleep-requests 1 \
  -o "audio/fed%(playlist_index)02d.%(ext)s" \
  -o "subtitle:captions/fed%(playlist_index)02d.%(ext)s" \
  --download-archive .yt-archive.txt \
  "$PLAYLIST"

.venv/bin/yt-dlp \
  --skip-download \
  --write-auto-subs --sub-langs "en-orig" --sub-format "vtt" \
  --sleep-requests 1 \
  -o "subtitle:captions/fed%(playlist_index)02d.%(ext)s" \
  "$PLAYLIST"
