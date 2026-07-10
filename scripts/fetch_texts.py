#!/usr/bin/env python
"""Fetch canonical Federalist Papers text from the Avalon Project.

Writes text/fedNN.txt for NN = 01..85. File format:
  line 1..k : heading lines (title / publication / author, from the <H3> block)
  blank line
  paragraphs separated by blank lines (as on the Avalon page, tags stripped)
"""

import html
import pathlib
import re
import sys
import time

import requests

BASE = "https://avalon.law.yale.edu/18th_century/fed{:02d}.asp"
OUT = pathlib.Path(__file__).resolve().parent.parent / "text"

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def clean(fragment: str) -> str:
    text = TAG_RE.sub("", fragment)
    text = html.unescape(text)
    return WS_RE.sub(" ", text).strip()


def extract(page: str) -> str:
    # Heading: the <H3>/<H4> block inside the title table (lines split by <BR>)
    m = re.search(r"<H[34]>(.*?)</H[34]>", page, re.S | re.I)
    if not m:
        raise ValueError("no <H3>/<H4> heading found")
    heading_lines = [
        clean(part) for part in re.split(r"<BR\s*/?>", m.group(1), flags=re.I)
    ]
    heading_lines = [ln for ln in heading_lines if ln]

    # Body: every <P>...</P> on the page (navigation chrome uses tables, not <P>)
    body = page[m.end():]
    # fed70 carries a second, "slightly different" full version of the paper;
    # keep only the primary version (the narrator reads one of them).
    body = re.split(r'<A NAME="70b">', body, flags=re.I)[0]
    paragraphs = [clean(p) for p in re.findall(r"<P[^>]*>(.*?)</P>", body, re.S | re.I)]
    paragraphs = [p for p in paragraphs if p]
    if not paragraphs:
        raise ValueError("no paragraphs found")

    return "\n".join(heading_lines) + "\n\n" + "\n\n".join(paragraphs) + "\n"


def main() -> None:
    OUT.mkdir(exist_ok=True)
    session = requests.Session()
    session.headers["User-Agent"] = "federalist-papers-ebook/0.1 (personal archival project)"
    failures = []
    for n in range(1, 86):
        dest = OUT / f"fed{n:02d}.txt"
        if dest.exists() and dest.stat().st_size > 0:
            continue
        url = BASE.format(n)
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            dest.write_text(extract(resp.text), encoding="utf-8")
            print(f"fed{n:02d}: {dest.stat().st_size} bytes")
        except Exception as exc:  # noqa: BLE001
            failures.append((n, exc))
            print(f"fed{n:02d}: FAILED - {exc}", file=sys.stderr)
        time.sleep(0.5)
    if failures:
        sys.exit(f"{len(failures)} papers failed: {[n for n, _ in failures]}")


if __name__ == "__main__":
    main()
