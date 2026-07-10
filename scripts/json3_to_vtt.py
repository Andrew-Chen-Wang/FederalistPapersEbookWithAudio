#!/usr/bin/env python
"""Generate WebVTT review files from json3 captions, for papers where the
.vtt download was rate-limited or the transcript came from whisper.

Usage: python scripts/json3_to_vtt.py   (fills in any missing fedNN vtt)
"""

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
CAPS = ROOT / "captions"


def ts(ms: int) -> str:
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def convert(src: pathlib.Path, dest: pathlib.Path) -> None:
    data = json.loads(src.read_text(encoding="utf-8"))
    cues = []
    for ev in data.get("events", []):
        t0 = ev.get("tStartMs")
        segs = ev.get("segs")
        if t0 is None or not segs:
            continue
        text = "".join(s.get("utf8", "") for s in segs).strip()
        if not text:
            continue
        end = t0 + ev.get("dDurationMs", 2000)
        cues.append(f"{ts(t0)} --> {ts(end)}\n{text}")
    dest.write_text("WEBVTT\n\n" + "\n\n".join(cues) + "\n", encoding="utf-8")
    print(f"{dest.name}: {len(cues)} cues")


def main() -> None:
    for n in range(1, 86):
        if list(CAPS.glob(f"fed{n:02d}.*.vtt")):
            continue
        srcs = sorted(CAPS.glob(f"fed{n:02d}.*.json3"))
        if not srcs:
            print(f"fed{n:02d}: no json3 to convert")
            continue
        src = srcs[0]
        lang = src.name.split(".", 1)[1].rsplit(".", 1)[0]  # en-orig / en / whisper
        convert(src, CAPS / f"fed{n:02d}.{lang}.vtt")


if __name__ == "__main__":
    main()
