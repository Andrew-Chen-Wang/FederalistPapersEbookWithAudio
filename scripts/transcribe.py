#!/usr/bin/env python
"""Locally transcribe papers whose YouTube captions are missing or unusable.

Uses FluidAudio (Parakeet TDT v2 on CoreML, Apple Silicon) through the Swift
bridge in tools/fluidaudio-bridge — about 100x faster than CPU Whisper. The
bridge prints one JSON line: {"text", "duration", "words": [{word,start,end}]}.
Output is written in the same json3 shape yt-dlp produces, so align.py
consumes it unchanged: captions/fedNN.fluidaudio.json3

Usage: python scripts/transcribe.py 22 36 49        (or --force to redo)
The bridge is built automatically on first use (needs Xcode command line
tools); the Parakeet model downloads on the first transcription.
"""

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BRIDGE_DIR = ROOT / "tools" / "fluidaudio-bridge"
BRIDGE = BRIDGE_DIR / ".build" / "release" / "fluidaudio-bridge"

WORDS_PER_EVENT = 40  # json3 grouping only; alignment flattens all events


def ensure_bridge() -> None:
    if BRIDGE.exists():
        return
    print("building fluidaudio-bridge (first run)...")
    subprocess.run(
        ["swift", "build", "-c", "release"], cwd=BRIDGE_DIR, check=True
    )


def transcribe(n: int, force: bool = False) -> None:
    audio = ROOT / "audio" / f"fed{n:02d}.m4a"
    out = ROOT / "captions" / f"fed{n:02d}.fluidaudio.json3"
    if out.exists() and not force:
        print(f"fed{n:02d}: already transcribed, skipping")
        return
    proc = subprocess.run(
        [str(BRIDGE), str(audio)], capture_output=True, text=True, check=True
    )
    # The bridge prints exactly one JSON line; CoreML runtime warnings may
    # leak onto stdout after it, so parse the first line that looks like JSON.
    line = next(l for l in proc.stdout.splitlines() if l.startswith("{"))
    result = json.loads(line)
    words = result["words"]

    events = []
    for i in range(0, len(words), WORDS_PER_EVENT):
        group = words[i:i + WORDS_PER_EVENT]
        t0 = int(group[0]["start"] * 1000)
        events.append({
            "tStartMs": t0,
            "dDurationMs": int(group[-1]["end"] * 1000) - t0,
            "segs": [
                {"utf8": w["word"], "tOffsetMs": int(w["start"] * 1000) - t0}
                for w in group
            ],
        })
    out.write_text(json.dumps({"events": events}), encoding="utf-8")
    print(f"fed{n:02d}: {len(words)} words -> {out.name}")


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--force"]
    force = "--force" in sys.argv[1:]
    papers = [int(a) for a in args]
    if not papers:
        sys.exit("usage: transcribe.py [--force] N [N ...]")
    ensure_bridge()
    for n in papers:
        transcribe(n, force=force)


if __name__ == "__main__":
    main()
