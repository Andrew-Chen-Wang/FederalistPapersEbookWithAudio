# The Federalist Papers — Audio Ebook

This is an ebook of the Federalist Papers with audio embedded for listening.
All 85 papers are included, one chapter per paper, as an EPUB 3 with
[Media Overlays](https://www.w3.org/TR/epub-33/#sec-media-overlays): in a
reader that supports read-aloud (Apple Books, Thorium Reader, Colibrio…),
press play and the sentence being narrated is highlighted as the audio plays.

## Downloads

Three editions, from the [latest release](https://github.com/Andrew-Chen-Wang/FederalistPapersEbookWithAudio/releases/latest)
(too large for git; rebuild locally with the pipeline below if you prefer):

| Edition | Download | What it is |
|---|---|---|
| **Canonical + audio** | [the-federalist-papers.epub](https://github.com/Andrew-Chen-Wang/FederalistPapersEbookWithAudio/releases/latest/download/the-federalist-papers.epub) (~883 MB) | The authoritative Avalon text with embedded narration; sentences highlight where the narration matches the canonical text. The narrator reads a slightly different historical edition in places, so wording can occasionally differ from the audio. |
| **Transcript + audio** | [the-federalist-papers-transcript.epub](https://github.com/Andrew-Chen-Wang/FederalistPapersEbookWithAudio/releases/latest/download/the-federalist-papers-transcript.epub) (~883 MB) | Exactly what the narrator says, word for word, with embedded narration and highlight sync. Text comes from the punctuated, word-timestamped FluidAudio transcripts, so it follows the audio 1:1. |
| **Text only** | [the-federalist-papers-text-only.epub](https://github.com/Andrew-Chen-Wang/FederalistPapersEbookWithAudio/releases/latest/download/the-federalist-papers-text-only.epub) (~0.5 MB) | Just the canonical Federalist Papers, no audio. |

In readers that fully support EPUB media overlays (e.g. [Thorium Reader](https://thorium.edrlab.org/)),
the audio editions play with synchronized sentence highlighting. In Apple
Books, use the audio player at the top of each chapter (Books doesn't play
media overlays in reflowable books).

## Credits

- **Narration**: [VonClegg Classics](https://www.youtube.com/@voncleggclassics5928),
  from their [Federalist Papers playlist](https://www.youtube.com/playlist?list=PLri6XX7fEjPDOu5k5O83qNAusvT0thNcE).
  The audio belongs to VonClegg Classics; see [LICENSE](LICENSE) — the ebook
  is free to use and share but must not be monetized.
- **Text**: [The Avalon Project at Yale Law School](https://avalon.law.yale.edu/subject_menus/fed.asp)
  (public-domain text). Another good source for the text is
  [Project Gutenberg](https://www.gutenberg.org/files/1404/1404-h/1404-h.htm).
- **Local transcription**: [FluidAudio](https://github.com/FluidInference/FluidAudio)
  (Parakeet TDT on CoreML) fills in word timestamps for videos with missing or
  unusable YouTube captions. The Swift↔Python bridge approach comes from
  [anvanvan/mac-whisper-speedtest](https://github.com/anvanvan/mac-whisper-speedtest).

## What's in the repository

| Path | Contents |
|---|---|
| `audio/fedNN.m4a` | Narration for paper NN (AAC, straight from YouTube) |
| `captions/fedNN.*.json3` | Captions with per-word timestamps (YouTube ASR, or local FluidAudio transcription where YouTube's were missing/unusable) |
| `captions/fedNN.*.vtt` | The same captions as WebVTT, for human review |
| `text/fedNN.txt` | Canonical text of paper NN (Avalon) |
| `build/align/fedNN.json` | Sentence-level begin/end audio timings |
| `scripts/` | The pipeline: download → fetch text → align → build EPUB |
| `tools/fluidaudio-bridge/` | Swift CLI exposing FluidAudio word timestamps to Python |

Rebuild from scratch:

```sh
uv sync
scripts/download.sh                      # audio + captions (yt-dlp)
.venv/bin/python scripts/fetch_texts.py  # canonical text (Avalon)
.venv/bin/python scripts/transcribe.py 22 36 49 ...  # only papers with bad/missing captions
.venv/bin/python scripts/align.py        # captions ⇄ text forced alignment
.venv/bin/python scripts/build_epub.py   # EPUB3 with media overlays
```

## Reusing this approach for other YouTube audio

This repository was built almost entirely by a coding agent (Claude Code)
from a two-paragraph prompt, and the same recipe works for any narrated
public-domain work on YouTube. Guidelines if you want to reproduce it:

1. **Point the agent at a playlist and a canonical text source.** Give it
   the playlist URL and a stable, chapter-addressable source for the real
   text (Gutenberg, Avalon, Wikisource…). One video ↔ one chapter is the
   ideal shape.
2. **Ask for word-timestamped captions, not just subtitles.** YouTube's
   `json3` caption format carries a timestamp for every word, which is what
   makes precise audio⇄text sync possible. Have the agent verify captions
   exist for every video and fall back to local transcription for videos
   that have none — auto-captions are missing or garbage more often than
   you'd expect. (On Apple Silicon, FluidAudio's Parakeet CoreML model
   transcribed ~2.5 hours of audio in 35 seconds; Whisper works anywhere
   but is orders of magnitude slower on CPU.)
3. **Never use the captions as the book text.** ASR text is lowercase,
   unpunctuated, and full of mistakes. Instead have the agent align the
   canonical text against the caption word timings and keep the canonical
   words. Expect a >90% word match rate on clean narration; anything much
   lower means the video and the text don't correspond (wrong version,
   abridged reading) and is worth investigating rather than forcing.
4. **Make the agent validate and spot-check.** `epubcheck` for the EPUB,
   per-chapter match-rate reports for the alignment, and listening to a
   couple of random sentences against their highlight timing. The match
   report is what surfaced the surprises here (two full versions of one
   paper on a single Avalon page; a narrator who skipped half a paper).
5. **Let it run unattended, but in stages.** Downloading, transcribing,
   aligning, and building are all resumable, background-friendly steps.
   Rate limits (HTTP 429) are normal — the agent should retry with backoff
   rather than hammer.
6. **Sort out licensing up front.** The text may be public domain while
   the narration is not: credit the narrator, and state clearly what may
   be reused and whether it can be monetized.

## License

Code is MIT. The ebook is free to use, copy, and share. The narration is
the property of VonClegg Classics, is included with attribution, and must
not be monetized. Details in [LICENSE](LICENSE).
