#!/usr/bin/env python
"""Force-align the canonical Avalon text with YouTube ASR word timings.

For each paper:
  - text/fedNN.txt        canonical text (heading lines, blank line, paragraphs)
  - captions/fedNN.en-orig.json3   ASR captions with per-word timestamps
  - audio/fedNN.m4a       audio (duration read via ffprobe)

The canonical text is split into sentence-level sync units. Canonical words
are aligned to ASR words with difflib.SequenceMatcher over normalized tokens;
each sentence gets begin/end times from its first/last matched word. Interior
sentences with no matches are interpolated; sentence times are then made
contiguous so highlighting tracks the narration without gaps.

Output: build/align/fedNN.json
  {"duration": float, "match_ratio": float, "heading": [...],
   "units": [{"id","para","text","begin","end","synced"} ...]}

Also prints a per-paper QA line (match ratio between caption text and
canonical text) so bad papers stand out.
"""

import difflib
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEXT = ROOT / "text"
CAPS = ROOT / "captions"
AUDIO = ROOT / "audio"
OUT = ROOT / "build" / "align"

NORM_RE = re.compile(r"[^a-z0-9]+")

# Sentence boundary: ., ;, :, ?, ! followed by whitespace. The 18th-century
# prose has very long sentences; semicolons/colons give finer highlight units.
SENT_RE = re.compile(r"(?<=[.;:?!])\s+")


def norm(token: str) -> str:
    return NORM_RE.sub("", token.lower())


def load_asr_words(path: pathlib.Path):
    """Return [(normalized_word, start_sec, end_sec)] from a json3 file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    words = []
    for ev in data.get("events", []):
        t0 = ev.get("tStartMs")
        if t0 is None or "segs" not in ev:
            continue
        for seg in ev["segs"]:
            raw = seg.get("utf8", "")
            w = norm(raw)
            if not w:
                continue
            start = (t0 + seg.get("tOffsetMs", 0)) / 1000.0
            words.append([w, start, start])  # end filled below
    # End of a word = start of the next one (ASR gives onsets only).
    for i in range(len(words) - 1):
        words[i][2] = words[i + 1][1]
    if words:
        words[-1][2] = words[-1][1] + 1.0
    return [tuple(w) for w in words]


def audio_duration(path: pathlib.Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def split_units(txt: str):
    """Split canonical text into (heading_lines, [(para_index, sentence)])."""
    heading, _, body = txt.partition("\n\n")
    heading_lines = [ln.strip() for ln in heading.splitlines() if ln.strip()]
    units = []
    for pi, para in enumerate(body.split("\n\n")):
        para = para.strip()
        if not para:
            continue
        for sent in SENT_RE.split(para):
            sent = sent.strip()
            if sent:
                units.append((pi, sent))
    return heading_lines, units


def align_paper(n: int):
    txt_path = TEXT / f"fed{n:02d}.txt"
    # Preference: en-orig (good YouTube ASR) > fluidaudio/whisper (local) >
    # en (the remaining videos' YouTube "en" track is legacy ASR, near-useless).
    rank = {"en-orig": 0, "fluidaudio": 1, "whisper": 2, "en": 3}
    caps = sorted(
        CAPS.glob(f"fed{n:02d}.*.json3"),
        key=lambda p: rank.get(p.name.split(".", 2)[1], 9),
    )
    if not caps:
        raise FileNotFoundError(2, "no captions", str(CAPS / f"fed{n:02d}.*.json3"))
    cap_path = caps[0]
    audio_path = AUDIO / f"fed{n:02d}.m4a"

    heading_lines, units = split_units(txt_path.read_text(encoding="utf-8"))
    asr = load_asr_words(cap_path)
    duration = audio_duration(audio_path)

    # Canonical token stream, remembering which unit each token belongs to.
    canon_tokens, canon_unit = [], []
    unit_texts = []
    for ui, (pi, sent) in enumerate(units):
        unit_texts.append((pi, sent))
        for tok in sent.split():
            w = norm(tok)
            if w:
                canon_tokens.append(w)
                canon_unit.append(ui)

    asr_tokens = [w for w, _, _ in asr]
    sm = difflib.SequenceMatcher(a=canon_tokens, b=asr_tokens, autojunk=False)

    # For each canonical token: the matched ASR word interval, if any.
    tok_time = [None] * len(canon_tokens)
    matched = 0
    for a, b, size in sm.get_matching_blocks():
        for k in range(size):
            tok_time[a + k] = (asr[b + k][1], asr[b + k][2])
        matched += size

    # Per-unit begin/end from first/last matched token.
    n_units = len(unit_texts)
    begins = [None] * n_units
    ends = [None] * n_units
    match_counts = [0] * n_units
    tok_counts = [0] * n_units
    for ti, ui in enumerate(canon_unit):
        tok_counts[ui] += 1
        tt = tok_time[ti]
        if tt is None:
            continue
        match_counts[ui] += 1
        if begins[ui] is None:
            begins[ui] = tt[0]
        ends[ui] = tt[1]

    # A unit counts as genuinely synced if enough of its words matched.
    synced = [
        begins[ui] is not None and match_counts[ui] >= max(1, tok_counts[ui] // 4)
        for ui in range(n_units)
    ]

    # Interpolate interior unsynced units between their synced neighbours;
    # leading unsynced units start at 0 (the narrator reads the heading first).
    units_out = []
    last_synced = max((i for i in range(n_units) if synced[i]), default=None)
    for ui in range(n_units):
        units_out.append({
            "id": f"u{ui + 1:04d}",
            "para": unit_texts[ui][0],
            "text": unit_texts[ui][1],
            "begin": begins[ui] if synced[ui] else None,
            "end": ends[ui] if synced[ui] else None,
            "synced": bool(synced[ui]),
        })

    # Fill missing begins by scanning: unsynced units inherit a window from
    # surrounding synced units so playback order stays monotonic.
    prev_end = 0.0
    for ui, u in enumerate(units_out):
        if u["begin"] is None:
            nxt = next(
                (units_out[j]["begin"] for j in range(ui + 1, n_units)
                 if units_out[j]["begin"] is not None),
                duration if (last_synced is None or ui > last_synced) else prev_end,
            )
            u["begin"] = prev_end
            u["end"] = nxt
        if u["end"] is None or u["end"] < u["begin"]:
            u["end"] = u["begin"]
        prev_end = u["end"]

    # Make times contiguous & monotonic: each unit ends where the next begins.
    for ui in range(n_units - 1):
        nxt_begin = max(units_out[ui + 1]["begin"], units_out[ui]["begin"])
        units_out[ui + 1]["begin"] = nxt_begin
        units_out[ui]["end"] = nxt_begin
    if units_out:
        units_out[0]["begin"] = 0.0
        units_out[-1]["end"] = max(duration, units_out[-1]["begin"])

    ratio = matched / max(1, len(canon_tokens))
    result = {
        "paper": n,
        "duration": duration,
        "match_ratio": round(ratio, 4),
        "heading": heading_lines,
        "units": units_out,
    }
    (OUT / f"fed{n:02d}.json").write_text(
        json.dumps(result, indent=1), encoding="utf-8"
    )
    synced_count = sum(1 for u in units_out if u["synced"])
    print(f"fed{n:02d}: {ratio:6.1%} words matched, "
          f"{synced_count}/{n_units} units synced, {duration:7.1f}s")
    return ratio


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    papers = [int(a) for a in sys.argv[1:]] or range(1, 86)
    low = []
    for n in papers:
        try:
            ratio = align_paper(n)
            if ratio < 0.80:
                low.append((n, ratio))
        except FileNotFoundError as exc:
            print(f"fed{n:02d}: SKIPPED - missing {exc.filename}", file=sys.stderr)
            low.append((n, 0.0))
    if low:
        print("\nLow-confidence papers:", ", ".join(f"#{n} ({r:.0%})" for n, r in low))


if __name__ == "__main__":
    main()
