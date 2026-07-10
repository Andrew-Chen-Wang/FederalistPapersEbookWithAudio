#!/bin/bash
# Retry caption downloads for papers whose videos lack the en-orig track or
# were rate-limited. Tries en-orig then en, with backoff on HTTP 429.
set -u
cd "$(dirname "$0")/.."
PLAYLIST_JSON="$1"   # path to flat playlist JSON (id order = paper order)

for n in $(seq 1 85); do
  nn=$(printf "%02d" "$n")
  ls "captions/fed$nn".*.json3 >/dev/null 2>&1 && continue
  id=$(python3 -c "
import json,sys
d=json.load(open('$PLAYLIST_JSON'))
print(d['entries'][$n-1]['id'])")
  for attempt in 1 2 3 4 5; do
    .venv/bin/yt-dlp --skip-download --write-auto-subs \
      --sub-langs "en-orig,en" --sub-format "json3" \
      -o "captions/fed$nn.%(ext)s" \
      "https://www.youtube.com/watch?v=$id" > /tmp/ytc.$$ 2>&1
    if ls "captions/fed$nn".*.json3 >/dev/null 2>&1; then
      echo "fed$nn: json3 OK (attempt $attempt)"
      break
    fi
    if grep -q "429" /tmp/ytc.$$; then
      echo "fed$nn: 429, backing off 90s (attempt $attempt)"
      sleep 90
    else
      echo "fed$nn: no captions available?"
      grep -E "no subtitles|ERROR" /tmp/ytc.$$ | head -2
      sleep 10
      break
    fi
  done
  # vtt copy for human review
  if ls "captions/fed$nn".*.json3 >/dev/null 2>&1 && ! ls "captions/fed$nn".*.vtt >/dev/null 2>&1; then
    for attempt in 1 2 3 4 5; do
      .venv/bin/yt-dlp --skip-download --write-auto-subs \
        --sub-langs "en-orig,en" --sub-format "vtt" \
        -o "captions/fed$nn.%(ext)s" \
        "https://www.youtube.com/watch?v=$id" > /tmp/ytc.$$ 2>&1
      ls "captions/fed$nn".*.vtt >/dev/null 2>&1 && { echo "fed$nn: vtt OK"; break; }
      grep -q "429" /tmp/ytc.$$ && { echo "fed$nn: vtt 429, backing off 90s"; sleep 90; } || break
    done
  fi
  sleep 5
done
rm -f /tmp/ytc.$$
echo "DONE json3=$(ls captions/*.json3 | wc -l) vtt=$(ls captions/*.vtt | wc -l)"
