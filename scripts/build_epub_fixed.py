#!/usr/bin/env python
"""Build a FIXED-LAYOUT EPUB3 of the narration transcript, for Apple Books.

Apple Books only exposes its Read Aloud (media-overlay) UI for fixed-layout
(pre-paginated) EPUBs, so this edition trades reflowable text for native
read-along highlighting in Books. Text is the punctuated FluidAudio
transcript — word-for-word what the narrator says — paginated onto fixed
1200x1600 pages, one SMIL overlay per page.

Output: build/the-federalist-papers-transcript-fixed.epub
"""

import html
import json
import pathlib
import sys
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from build_epub import clock, transcript_units  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
ALIGN = ROOT / "build" / "align"
AUDIO = ROOT / "audio"
OUT = ROOT / "build" / "the-federalist-papers-transcript-fixed.epub"

PAGE_W, PAGE_H = 1200, 1600
CHARS_PER_PAGE = 1500  # ~60% of what fits at 28px/1.45 in the content box
BOOK_ID = "urn:uuid:963fcfe1-88eb-5f94-a1d6-bd6f7bcc1c2e"
TITLE = "The Federalist Papers — Narration Transcript (Read Aloud)"

CSS = f"""\
html, body {{ margin: 0; padding: 0; }}
body {{
  width: {PAGE_W}px; height: {PAGE_H}px;
  background: #fffef9; color: #1a1a1a;
  font-family: Georgia, serif; font-size: 28px; line-height: 1.45;
}}
div.page {{ padding: 90px 100px; }}
h1 {{ font-size: 1.3em; text-align: center; margin: 0 0 0.3em; }}
p.byline {{ text-align: center; font-style: italic; margin: 0 0 1em; }}
p {{ margin: 0 0 0.6em; text-align: justify; }}
.-epub-media-overlay-active, .mo-active {{
  background-color: #ffe9a8; border-radius: 4px;
}}
"""

CONTAINER = """\
<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="EPUB/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

APPLE_OPTIONS = """\
<?xml version="1.0" encoding="UTF-8"?>
<display_options>
  <platform name="*">
    <option name="fixed-layout">true</option>
  </platform>
</display_options>
"""


def page_xhtml(title: str, header: str, body_paras: str) -> str:
    return f"""\
<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="en" xml:lang="en">
<head>
<meta name="viewport" content="width={PAGE_W}, height={PAGE_H}"/>
<title>{html.escape(title)}</title>
<link rel="stylesheet" type="text/css" href="style/fixed.css"/>
</head>
<body>
<div class="page">
{header}{body_paras}
</div>
</body>
</html>
"""


def page_smil(page_name: str, n: int, pars: list) -> str:
    body = "\n".join(
        f'    <par id="p_{uid}">\n'
        f'      <text src="{page_name}.xhtml#{uid}"/>\n'
        f'      <audio src="audio/fed{n:02d}.m4a" '
        f'clipBegin="{clock(b)}" clipEnd="{clock(e)}"/>\n'
        f'    </par>'
        for uid, b, e in pars
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<smil xmlns="http://www.w3.org/ns/SMIL" '
        'xmlns:epub="http://www.idpf.org/2007/ops" version="3.0">\n'
        f'  <body>\n  <seq id="s_{page_name}" epub:textref="{page_name}.xhtml" '
        'epub:type="bodymatter chapter">\n'
        + body + "\n  </seq>\n  </body>\n</smil>\n"
    )


def paginate(units):
    """Split a paper's units into pages of ~CHARS_PER_PAGE characters."""
    pages, cur, size = [], [], 0
    for u in units:
        if cur and size + len(u["text"]) > CHARS_PER_PAGE:
            pages.append(cur)
            cur, size = [], 0
        cur.append(u)
        size += len(u["text"]) + 1
    if cur:
        pages.append(cur)
    return pages


def main() -> None:
    manifest, spine, metas, toc_lis = [], [], [], []
    files = {}  # zip path -> bytes
    total = 0.0

    for n in range(1, 86):
        align = json.loads((ALIGN / f"fed{n:02d}.json").read_text(encoding="utf-8"))
        duration = align["duration"]
        heading = align["heading"]
        title = heading[0] if heading else f"Federalist No. {n}"
        chap_title = f"No. {n}. {title}"
        units = transcript_units(n, duration)
        total += duration

        files[f"EPUB/audio/fed{n:02d}.m4a"] = (AUDIO / f"fed{n:02d}.m4a").read_bytes()
        manifest.append(
            f'<item id="audio{n:02d}" href="audio/fed{n:02d}.m4a" '
            'media-type="audio/mp4"/>'
        )

        for pi, page_units in enumerate(paginate(units), start=1):
            page = f"chap{n:02d}_p{pi:03d}"
            header = ""
            if pi == 1:
                header = f'<h1>No. {n}: {html.escape(title)}</h1>\n'
                if len(heading) > 1:
                    header += f'<p class="byline">{html.escape(heading[1])}</p>\n'
            spans = " ".join(
                f'<span id="{u["id"]}">{html.escape(u["text"])}</span>'
                for u in page_units
            )
            files[f"EPUB/{page}.xhtml"] = page_xhtml(
                chap_title, header, f"<p>{spans}</p>"
            ).encode()
            pars = [(u["id"], u["begin"], u["end"]) for u in page_units
                    if u["end"] > u["begin"]]
            files[f"EPUB/{page}.smil"] = page_smil(page, n, pars).encode()

            manifest.append(
                f'<item id="{page}" href="{page}.xhtml" '
                f'media-type="application/xhtml+xml" media-overlay="smil_{page}"/>'
            )
            manifest.append(
                f'<item id="smil_{page}" href="{page}.smil" '
                'media-type="application/smil+xml"/>'
            )
            page_dur = sum(e - b for _, b, e in pars)
            metas.append(
                f'<meta property="media:duration" refines="#smil_{page}">'
                f'{clock(page_dur)}</meta>'
            )
            spine.append(f'<itemref idref="{page}"/>')
            if pi == 1:
                toc_lis.append(
                    f'<li><a href="{page}.xhtml">{html.escape(chap_title)}</a></li>'
                )

    nav = f"""\
<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="en" xml:lang="en">
<head><title>Table of Contents</title></head>
<body>
<nav epub:type="toc" id="toc"><h1>Table of Contents</h1>
<ol>
{chr(10).join(toc_lis)}
</ol>
</nav>
</body>
</html>
"""

    opf = f"""\
<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id" prefix="rendition: http://www.idpf.org/vocab/rendition/# ibooks: http://vocabulary.itunes.apple.com/rdf/ibooks/vocabulary-extensions-1.0/">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="id">{BOOK_ID}</dc:identifier>
    <dc:title>{html.escape(TITLE)}</dc:title>
    <dc:language>en</dc:language>
    <dc:creator id="creator1">Alexander Hamilton</dc:creator>
    <dc:creator id="creator2">James Madison</dc:creator>
    <dc:creator id="creator3">John Jay</dc:creator>
    <meta property="dcterms:modified">2026-07-09T00:00:00Z</meta>
    <meta property="rendition:layout">pre-paginated</meta>
    <meta property="rendition:orientation">auto</meta>
    <meta property="rendition:spread">auto</meta>
    <meta property="ibooks:specified-fonts">true</meta>
    <meta property="media:active-class">-epub-media-overlay-active</meta>
    <meta property="media:duration">{clock(total)}</meta>
    {chr(10).join('    ' + m for m in metas).strip()}
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="css" href="style/fixed.css" media-type="text/css"/>
    {chr(10).join('    ' + m for m in manifest).strip()}
  </manifest>
  <spine>
    {chr(10).join('    ' + s for s in spine).strip()}
  </spine>
</package>
"""

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT, "w") as z:
        z.writestr("mimetype", "application/epub+zip",
                   compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", CONTAINER)
        z.writestr("META-INF/com.apple.ibooks.display-options.xml", APPLE_OPTIONS)
        z.writestr("EPUB/content.opf", opf)
        z.writestr("EPUB/nav.xhtml", nav)
        z.writestr("EPUB/style/fixed.css", CSS)
        for path, data in sorted(files.items()):
            z.writestr(path, data, compress_type=zipfile.ZIP_DEFLATED)

    n_pages = sum(1 for p in files if p.endswith(".xhtml"))
    print(f"wrote {OUT.name} ({OUT.stat().st_size / 1e6:.1f} MB, "
          f"{n_pages} fixed pages, narration {clock(total)})")


if __name__ == "__main__":
    main()
