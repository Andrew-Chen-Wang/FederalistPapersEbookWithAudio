#!/usr/bin/env python
"""Build EPUB3 editions of the Federalist Papers.

Three editions (one paper per chapter, table of contents in each):

  canonical    The authoritative Avalon text, with narration audio and
               media-overlay sentence highlighting where the narration
               matches. -> build/the-federalist-papers.epub
  transcript   Exactly what the narrator says (word-timestamped ASR
               transcript), with audio and media overlays; wording matches
               the audio 1:1. -> build/the-federalist-papers-transcript.epub
  textonly     The Avalon text alone, no audio.
               -> build/the-federalist-papers-text-only.epub

Usage: build_epub.py [canonical|transcript|textonly ...]   (default: all)

Inputs: text/fedNN.txt, audio/fedNN.m4a, captions/fedNN.*.json3,
        build/align/fedNN.json
"""

import html
import json
import pathlib
import sys

from ebooklib import epub

ROOT = pathlib.Path(__file__).resolve().parent.parent
ALIGN = ROOT / "build" / "align"
AUDIO = ROOT / "audio"
CAPS = ROOT / "captions"
BUILD = ROOT / "build"

EDITIONS = {
    "canonical": {
        "out": "the-federalist-papers.epub",
        "title": "The Federalist Papers (with Audio)",
        "uuid": "urn:uuid:963fcfe1-88eb-5f94-a1d6-bd6f7bcc1c2b",
        "audio": True,
    },
    "transcript": {
        "out": "the-federalist-papers-transcript.epub",
        "title": "The Federalist Papers — Narration Transcript (with Audio)",
        "uuid": "urn:uuid:963fcfe1-88eb-5f94-a1d6-bd6f7bcc1c2c",
        "audio": True,
    },
    "textonly": {
        "out": "the-federalist-papers-text-only.epub",
        "title": "The Federalist Papers",
        "uuid": "urn:uuid:963fcfe1-88eb-5f94-a1d6-bd6f7bcc1c2d",
        "audio": False,
    },
}

CSS = """\
body { font-family: serif; line-height: 1.6; margin: 1em; }
h1 { font-size: 1.4em; text-align: center; margin-bottom: 0.2em; }
p.byline { text-align: center; font-style: italic; margin-top: 0; }
p.attribution { text-align: center; font-variant: small-caps; }
p.audioplayer { text-align: center; margin: 1em 0; }
p.audioplayer audio { width: 100%; max-width: 30em; }
.-epub-media-overlay-active, .mo-active {
  background-color: #ffe9a8; color: #000; border-radius: 2px;
}
"""

# Transcript chunking: aim for sentence-sized highlight units.
UNIT_MAX_WORDS = 22
UNIT_MIN_WORDS = 6
UNITS_PER_PARA = 5


def clock(sec: float) -> str:
    """SMIL clock value, e.g. 0:04:31.250"""
    ms = round(sec * 1000)
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return f"{h}:{m:02d}:{s:02d}.{ms:03d}"


def load_caption_words(n: int):
    """[(raw_word, start_sec)] from the best available json3 captions."""
    rank = {"en-orig": 0, "fluidaudio": 1, "whisper": 2, "en": 3}
    caps = sorted(
        CAPS.glob(f"fed{n:02d}.*.json3"),
        key=lambda p: rank.get(p.name.split(".", 2)[1], 9),
    )
    data = json.loads(caps[0].read_text(encoding="utf-8"))
    words = []
    for ev in data.get("events", []):
        t0 = ev.get("tStartMs")
        if t0 is None or "segs" not in ev:
            continue
        for seg in ev["segs"]:
            raw = seg.get("utf8", "").strip()
            if not raw or raw == "\n":
                continue
            words.append((raw, (t0 + seg.get("tOffsetMs", 0)) / 1000.0))
    return words


def transcript_units(n: int, duration: float):
    """Chunk caption words into highlight units: break on sentence-ending
    punctuation once a unit is long enough, or at a hard word cap (YouTube
    ASR has no punctuation; FluidAudio transcripts do)."""
    words = load_caption_words(n)
    units, cur = [], []

    def flush(next_start):
        if cur:
            units.append({
                "text": " ".join(w for w, _ in cur),
                "begin": cur[0][1],
                "end": next_start,
            })
            cur.clear()

    for i, (w, t) in enumerate(words):
        cur.append((w, t))
        ends_sentence = w[-1] in ".?!;:" and len(cur) >= UNIT_MIN_WORDS
        if ends_sentence or len(cur) >= UNIT_MAX_WORDS:
            nxt = words[i + 1][1] if i + 1 < len(words) else duration
            flush(nxt)
    flush(duration)
    for i, u in enumerate(units):
        u["id"] = f"u{i + 1:04d}"
        u["para"] = i // UNITS_PER_PARA
    if units:
        units[0]["begin"] = 0.0
        units[-1]["end"] = max(duration, units[-1]["begin"])
    return units


def chapter_parts(n: int, heading: list, with_player: bool):
    title = heading[0] if heading else f"Federalist No. {n}"
    parts = [f'<h1 id="h1">No. {n}: {html.escape(title)}</h1>']
    if len(heading) > 1:
        parts.append(f'<p class="byline">{html.escape(heading[1])}</p>')
    if len(heading) > 2:
        parts.append(f'<p class="attribution">{html.escape(heading[2])}</p>')
    if with_player:
        # Visible fallback player: readers without media-overlay support for
        # reflowable EPUBs (e.g. Apple Books) can still play the narration.
        parts.append(
            f'<p class="audioplayer"><audio controls="controls" preload="none" '
            f'src="audio/fed{n:02d}.m4a"></audio></p>'
        )
    return title, parts


def render_units(n: int, units, parts, with_audio: bool):
    """Append unit spans as paragraphs; return SMIL <par> lines."""
    base = f"chap{n:02d}"
    cur_para, para_buf, smil_pars = None, [], []

    def flush_para():
        if para_buf:
            parts.append("<p>" + " ".join(para_buf) + "</p>")
            para_buf.clear()

    for u in units:
        if u["para"] != cur_para:
            flush_para()
            cur_para = u["para"]
        para_buf.append(f'<span id="{u["id"]}">{html.escape(u["text"])}</span>')
        if with_audio and u["end"] > u["begin"]:
            smil_pars.append(
                f'    <par id="p_{u["id"]}">\n'
                f'      <text src="{base}.xhtml#{u["id"]}"/>\n'
                f'      <audio src="audio/fed{n:02d}.m4a" '
                f'clipBegin="{clock(u["begin"])}" clipEnd="{clock(u["end"])}"/>\n'
                f'    </par>'
            )
    flush_para()
    return smil_pars


def make_smil(n: int, smil_pars) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<smil xmlns="http://www.w3.org/ns/SMIL" '
        'xmlns:epub="http://www.idpf.org/2007/ops" version="3.0">\n'
        '  <body>\n'
        f'  <seq id="seq{n:02d}" epub:textref="chap{n:02d}.xhtml" '
        'epub:type="bodymatter chapter">\n'
        + "\n".join(smil_pars)
        + "\n  </seq>\n  </body>\n</smil>\n"
    )


def build_edition(kind: str) -> None:
    cfg = EDITIONS[kind]
    with_audio = cfg["audio"]

    book = epub.EpubBook()
    book.set_identifier(cfg["uuid"])
    book.set_title(cfg["title"])
    book.set_language("en")
    book.add_author("Alexander Hamilton", uid="creator1")
    book.add_author("James Madison", uid="creator2")
    book.add_author("John Jay", uid="creator3")
    if with_audio:
        book.add_metadata(None, "meta", "-epub-media-overlay-active",
                          {"property": "media:active-class"})

    css = epub.EpubItem(uid="style", file_name="style/main.css",
                        media_type="text/css", content=CSS.encode())
    book.add_item(css)

    chapters = []
    total = 0.0
    for n in range(1, 86):
        align = json.loads((ALIGN / f"fed{n:02d}.json").read_text(encoding="utf-8"))
        duration = align["duration"]
        title, parts = chapter_parts(n, align["heading"], with_player=with_audio)

        if kind == "transcript":
            units = transcript_units(n, duration)
        else:
            units = align["units"]
        smil_pars = render_units(n, units, parts, with_audio)

        chap_kwargs = {}
        if with_audio and smil_pars:
            smil = epub.EpubSMIL(uid=f"smil{n:02d}",
                                 file_name=f"chap{n:02d}.smil",
                                 content=make_smil(n, smil_pars).encode())
            book.add_item(smil)
            chap_kwargs["media_overlay"] = f"smil{n:02d}"
            book.add_metadata(None, "meta", clock(duration),
                              {"property": "media:duration",
                               "refines": f"#smil{n:02d}"})
            total += duration

        chap = epub.EpubHtml(uid=f"chap{n:02d}",
                             file_name=f"chap{n:02d}.xhtml",
                             title=f"No. {n}. {title}",
                             lang="en", **chap_kwargs)
        chap.set_content(f"<html><body>{'\n'.join(parts)}</body></html>")
        chap.add_item(css)
        book.add_item(chap)
        chapters.append(chap)

        if with_audio:
            book.add_item(epub.EpubItem(
                uid=f"audio{n:02d}",
                file_name=f"audio/fed{n:02d}.m4a",
                media_type="audio/mp4",
                content=(AUDIO / f"fed{n:02d}.m4a").read_bytes(),
            ))

    if with_audio:
        book.add_metadata(None, "meta", clock(total),
                          {"property": "media:duration"})

    book.toc = tuple(chapters)
    book.add_item(epub.EpubNcx())
    nav = epub.EpubNav()
    nav.add_item(css)
    book.add_item(nav)
    book.spine = ["nav", *chapters]

    out = BUILD / cfg["out"]
    out.parent.mkdir(parents=True, exist_ok=True)
    epub.write_epub(str(out), book)
    extra = f", narration {clock(total)}" if with_audio else ""
    print(f"{kind}: wrote {out.name} ({out.stat().st_size / 1e6:.1f} MB{extra})")


def main() -> None:
    kinds = sys.argv[1:] or list(EDITIONS)
    for kind in kinds:
        if kind not in EDITIONS:
            sys.exit(f"unknown edition {kind!r}; choose from {list(EDITIONS)}")
        build_edition(kind)


if __name__ == "__main__":
    main()
