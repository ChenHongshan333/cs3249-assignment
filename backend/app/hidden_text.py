"""Find text that is in a PDF's text layer but invisible on the rendered page (red-team fix, prompt p7).

Text extraction (pypdf) ignores colour and size, so white or tiny text that a reader cannot see used to reach
retrieval, the overview summaries and the model exactly like the authors' visible text. Hidden instructions or
claims aimed at AI tools could then steer what PaperLens told the learner (red_team/, target T2).

A character counts as hidden when either
- its glyph box (font ascent to descent, after scaling) is under MIN_VISIBLE_PT high (e.g. 1-pt text; normal body
  text is 8-12 pt, small figure labels 3-6 pt), or
- its fill colour is (almost) the same as the page around it (e.g. white text on a white page). The background is
  sampled from the rendered page just outside the character's box, so white text on a dark figure stays visible.
Runs of hidden characters are returned per page, and `strip_hidden` removes them from the extracted page text.
A run must contain at least MIN_RUN_WORDS words of letters: text meant to steer a reader or a model is a sentence,
while the hidden runs found in real papers (a URL inside a screenshot, chart axis numbers) are not.
Text drawn in invisible render mode (OCR layers over scanned images) is not treated as hidden.
"""
from __future__ import annotations

import ctypes
import re

import pypdfium2 as pdfium
import pypdfium2.raw as raw

MIN_VISIBLE_PT = 2.0      # glyph heights below this (in points) cannot be read on a printed page
COLOUR_TOLERANCE = 40     # max per-channel difference between text colour and background to count as invisible
MIN_RUN_CHARS = 12        # ignore isolated hidden characters (rendering artefacts, invisible spaces)
MIN_RUN_WORDS = 5         # ...and runs that are not sentence-like (URLs in screenshots, axis numbers)
RENDER_SCALE = 1.5


def _background(bitmap, width: int, height: int, scale: float, box: tuple[float, float, float, float], page_h: float):
    """Median colour of four points just outside the character box (above, below, left, right)."""
    left, right, bottom, top = box
    cx, cy = (left + right) / 2, (bottom + top) / 2
    gap = max(1.0, (top - bottom) * 0.6)
    points = [(cx, top + gap), (cx, bottom - gap), (left - gap, cy), (right + gap, cy)]
    colours = []
    for x, y in points:
        px, py = int(x * scale), int((page_h - y) * scale)
        if 0 <= px < width and 0 <= py < height:
            colours.append(bitmap.getpixel((px, py))[:3])
    if not colours:
        return None
    colours.sort(key=sum)
    return colours[len(colours) // 2]


def find_hidden_text(pdf_bytes: bytes) -> list[dict]:
    """Return [{page, text, reason}] for every run of hidden text (page = 1-based PDF page index)."""
    found: list[dict] = []
    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        for index in range(len(pdf)):
            page = pdf[index]
            textpage = page.get_textpage()
            count = textpage.count_chars()
            if not count:
                continue
            page_h = page.get_height()
            image = None
            r, g, b, a = (ctypes.c_uint() for _ in range(4))
            loose = raw.FS_RECTF()
            l, rt, bt, tp = (ctypes.c_double() for _ in range(4))
            run, reasons = [], set()

            def close_run():
                text = re.sub(r"\s+", " ", "".join(run)).strip()
                words = re.findall(r"[^\W\d_]{2,}", text)
                if len(text) >= MIN_RUN_CHARS and len(words) >= MIN_RUN_WORDS:
                    found.append({"page": index + 1, "text": text, "reason": "+".join(sorted(reasons))})
                run.clear()
                reasons.clear()

            for i in range(count):
                char = chr(raw.FPDFText_GetUnicode(textpage.raw, i) or 32)
                if char.isspace() or not char.isprintable():
                    if run:
                        run.append(" ")
                    continue
                reason = ""
                # Effective size: the nominal font size ignores the text matrix (many PDFs scale a 1-pt font).
                raw.FPDFText_GetLooseCharBox(textpage.raw, i, loose)
                size = loose.top - loose.bottom
                if 0 < size < MIN_VISIBLE_PT:
                    reason = "tiny"
                elif raw.FPDFText_GetFillColor(textpage.raw, i, r, g, b, a) and a.value > 0:
                    raw.FPDFText_GetCharBox(textpage.raw, i, l, rt, bt, tp)
                    # Only near-background colours need a pixel check; dark text on a light page is the common case.
                    if image is None:
                        image = page.render(scale=RENDER_SCALE).to_pil().convert("RGB")
                    bg = _background(image, image.width, image.height, RENDER_SCALE,
                                     (l.value, rt.value, bt.value, tp.value), page_h)
                    if bg is not None and max(abs(bg[0] - r.value), abs(bg[1] - g.value), abs(bg[2] - b.value)) <= COLOUR_TOLERANCE:
                        reason = "same colour as background"
                if reason:
                    run.append(char)
                    reasons.add(reason)
                elif run:
                    close_run()
            if run:
                close_run()
            textpage.close()
            page.close()
    finally:
        pdf.close()
    return found


def strip_hidden(pages: list[dict], hidden: list[dict]) -> tuple[list[dict], list[dict]]:
    """Remove each hidden run from its page's extracted text. Returns (pages, hidden runs with removed=True/False).

    pypdf and pdfium can space words differently, so a run is matched word by word with flexible whitespace.
    """
    by_page = {p["page"]: dict(p) for p in pages}
    report = []
    for item in hidden:
        page = by_page.get(item["page"])
        words = item["text"].split()
        removed = False
        if page and words:
            pattern = r"\s*".join(re.escape(w) for w in words)
            new_text, n = re.subn(pattern, " ", page["text"])
            if n:
                page["text"], removed = new_text, True
        report.append({**item, "removed": removed})
    return [by_page[p["page"]] for p in pages], report
