"""Figures and tables: find them by their captions, render their pages, and ask a vision model to describe them.

Why captions: they are the authors' own words, so they can be quoted and highlighted like any passage, and a
caption reliably marks that a figure or table is on that page. The description itself is model-generated and is
stored and shown as such (like the overview), never as the authors' words.
"""
from __future__ import annotations

import base64
import io
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from pydantic import BaseModel, Field

MAX_FIGURES = 20          # per paper, to keep indexing time bounded
CAPTION_MAX_CHARS = 300
RENDER_DPI = 130          # enough to read labels; the model downsizes larger images anyway

# "Figure 3: ...", "Fig. 3. ...", "Table 2.4 ...", "TABLE II. ..." at the START of a line. Mentions in running text
# ("as shown in Figure 3") are not at a line start or continue in lower case, so they do not match.
_CAPTION = re.compile(
    r"^\s*(?P<kind>Figure|Fig\.|FIGURE|FIG\.|Table|TABLE)\s+(?P<num>\d+(?:\.\d+)*|[IVXLC]+)\b(?P<sep>\s*[:.|—–-])?\s*(?P<rest>.*)$")


MIN_IMAGE_AREA = 0.10     # uncaptioned figure: an embedded image covering at least 10% of the page ...
MIN_VECTOR_PATHS = 40     # ... or a vector drawing made of many path objects (e.g. the MDA diagram)


class FigureDescription(BaseModel):
    kind: Literal["figure", "table", "none"] = Field(
        description="'figure' or 'table'; 'none' if the page has no such content (only text or decorative lines).")
    description: str = Field(description="3-6 sentences describing only what is visible: what type of figure or table it is, "
                                          "its parts, axes, columns or labels, and the main trends or values that can be read.")
    unreadable_parts: str = Field(default="", description="Anything that cannot be read reliably (small text, dense cells). Empty if none.")


def _kind(word: str) -> str:
    return "table" if word.lower().startswith("tab") else "figure"


def find_captions(raw_pages: list[dict]) -> list[dict]:
    """Captions found in the raw (line-preserving) page text, first occurrence of each label only."""
    found: dict[tuple[str, str], dict] = {}
    for page in raw_pages:
        lines = page["text"].splitlines()
        for i, line in enumerate(lines):
            match = _CAPTION.match(line)
            if not match:
                continue
            rest = match.group("rest").strip()
            # a caption has a separator ("Figure 3:") or starts with a capital/quote ("Table 2.4 English consonants");
            # running text such as "Figure 3 shows ..." has neither
            if not (match.group("sep") or (rest[:1].isupper() or rest[:1] in "\"“'‘(")):
                continue
            if not rest and i + 1 >= len(lines):
                continue
            text = line.strip()
            # Only a caption with a separator ("Figure 3: ...") continues onto the next lines, until its first full
            # stop. A title-style caption ("Table 2.4 Example words ...") is one line: what follows it is usually the
            # text inside the figure or table (axis labels, column headers), not more caption.
            if match.group("sep"):
                for following in lines[i + 1:]:
                    if text.endswith(".") and len(text) >= 20:
                        break
                    if not following.strip() or len(text) >= CAPTION_MAX_CHARS or _CAPTION.match(following):
                        break
                    text = re.sub(r"(\w)-$", r"\1", text) + ("" if text.endswith("-") else " ") + following.strip()
            kind = _kind(match.group("kind"))
            label = f"{'Table' if kind == 'table' else 'Figure'} {match.group('num')}"
            key = (kind, match.group("num"))
            if key not in found:
                found[key] = {"label": label, "kind": kind, "page": page["page"], "page_label": page["page_label"],
                              "caption": re.sub(r"\s{2,}", " ", text)[:CAPTION_MAX_CHARS]}
    captions = sorted(found.values(), key=lambda c: (c["page"], c["label"]))
    return captions[:MAX_FIGURES]


def find_uncaptioned(pdf_bytes: bytes, pages: list[dict], captioned_pages: set[int]) -> list[dict]:
    """Pages with no caption that still look like they contain a figure: a large embedded image or a vector drawing.

    The vision model can still answer 'none' (e.g. for decorative rules), in which case nothing is stored.
    """
    import pypdfium2 as pdfium
    import pypdfium2.raw as pdfium_c

    labels = {p["page"]: p["page_label"] for p in pages}
    found = []
    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        for index in range(len(pdf)):
            number = index + 1
            if number in captioned_pages:
                continue
            page = pdf[index]
            width, height = page.get_size()
            image_area = 0.0
            for obj in page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_IMAGE], max_depth=3):
                left, bottom, right, top = obj.get_bounds()
                image_area = max(image_area, (right - left) * (top - bottom) / (width * height))
            paths = sum(1 for _ in page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_PATH], max_depth=3))
            if image_area >= MIN_IMAGE_AREA or paths >= MIN_VECTOR_PATHS:
                found.append({"label": f"Figure on p. {number}", "kind": "figure", "page": number,
                              "page_label": labels.get(number, str(number)), "caption": ""})
    finally:
        pdf.close()
    return found


def render_page_jpeg(pdf_bytes: bytes, page_number: int) -> str:
    """Render one PDF page (1-based) to a base64 JPEG."""
    import pypdfium2 as pdfium  # imported lazily so the rest of the app does not depend on it

    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        image = pdf[page_number - 1].render(scale=RENDER_DPI / 72).to_pil().convert("RGB")
    finally:
        pdf.close()
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=80)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def describe_figures(pdf_bytes: bytes, items: list[dict], paper_id: str) -> tuple[list[dict], list[dict]]:
    """Describe each figure/table with the vision model. Returns (figure chunks, problems).

    A failure for one figure is recorded and skipped; it never fails the whole ingestion. Uncaptioned candidates the
    model reports as 'none' (no real figure on the page) are dropped.
    """
    from .llm import ModelError, vision_structured_call
    from .prompts import load_prompt

    prompt = load_prompt("figure")
    images = {p: render_page_jpeg(pdf_bytes, p) for p in {item["page"] for item in items}}

    def describe(item: dict):
        if item["caption"]:
            request = (f"Describe {item['label']} on this page. Its caption reads:\n<caption>{item['caption']}</caption>\n"
                       "If several figures or tables are on the page, describe only this one.")
        else:
            request = ("This page has no figure caption. Describe the main figure, diagram, chart or table on it. "
                       "If the page contains only text or decorative elements, set kind to 'none'.")
        try:
            return vision_structured_call(prompt, request, images[item["page"]], FigureDescription), None
        except ModelError as exc:
            return None, str(exc)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(describe, items))

    chunks, problems = [], []
    for item, (result, error) in zip(items, results):
        if result is None:
            problems.append({"label": item["label"], "page": item["page"], "error": error})
            continue
        if result.kind == "none":
            if item["caption"]:   # a caption without visible content is worth knowing about; an empty candidate is not
                problems.append({"label": item["label"], "page": item["page"], "error": "model saw no figure or table"})
            continue
        label = item["label"]
        if item["caption"]:
            suffix = ("tab" if item["kind"] == "table" else "fig") + re.sub(r"\W", "", label.split(" ", 1)[1])
        else:
            label = f"{'Table' if result.kind == 'table' else 'Figure'} on p. {item['page']}"
            suffix = "figp"
        unreadable = f" Not readable: {result.unreadable_parts}" if result.unreadable_parts.strip() else ""
        caption_line = f"Caption (authors' words): {item['caption']}" if item["caption"] else "No caption in the paper."
        chunks.append({
            "chunk_id": f"{paper_id[:8]}-p{item['page']:03d}-{suffix}",
            # Embedded and shown together: the generated description plus the authors' caption (the only quotable part).
            "text": f"{label} (PaperLens description of the image): {result.description}{unreadable}\n{caption_line}",
            "metadata": {"paper_id": paper_id, "page": item["page"], "page_label": item["page_label"],
                         "chunk_index": -1, "kind": "figure", "label": label, "caption": item["caption"]},
        })
    return chunks, problems
