"""PDF ingestion: extract text per page -> clean -> chunk -> embed -> Chroma, then build a sourced overview.

Status flow stored in data/papers/<paper_id>/paper.json:
    queued -> parsing -> indexing -> summarizing -> ready      (or failed, with failed_stage + error)
"""
from __future__ import annotations

import hashlib
import io
import re
import traceback
import unicodedata
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

from . import storage
from .config import settings
from .llm import ModelError, structured_call
from .prompts import load_prompt
from .retrieval import replace_paper_chunks
from .schemas import OverviewSummary

MIN_TOTAL_CHARS = 1500        # below this, we treat the PDF as having no usable text layer
MIN_TEXT_PAGE_RATIO = 0.5     # at least half of the pages must have extractable text
OVERVIEW_GROUP_CHARS = 7000   # roughly how much text each overview summary covers
MAX_PDF_BYTES = 50 * 1024 * 1024


class IngestError(RuntimeError):
    pass


def paper_id_for(pdf_bytes: bytes) -> str:
    return hashlib.sha256(pdf_bytes).hexdigest()[:16]


# ---------------------------------------------------------------- extraction

def safe_text(text: str) -> str:
    """Make extracted text safe to store and embed.

    pypdf sometimes returns UTF-16 surrogate halves (e.g. mathematical italic letters such as
    U+1D465), which cannot be written as UTF-8. Valid pairs are rejoined, lone halves are
    dropped, and NFKC maps styled math letters and ligatures (fi, fl) to plain characters.
    """
    text = text.encode("utf-16", "surrogatepass").decode("utf-16", "ignore")
    return unicodedata.normalize("NFKC", text)


def extract_pages(pdf_bytes: bytes) -> tuple[list[dict], dict]:
    """Return [{page, page_label, text}] (page = 1-based PDF page index) and document info."""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        if reader.is_encrypted:
            reader.decrypt("")
        labels = list(reader.page_labels) if reader.page_labels else []
        pages = []
        for index, page in enumerate(reader.pages):
            try:
                text = safe_text(page.extract_text() or "")
            except Exception:
                text = ""
            pdf_page = index + 1
            label = labels[index] if index < len(labels) else str(pdf_page)
            pages.append({"page": pdf_page, "page_label": label, "text": text})
        title = ""
        if reader.metadata and reader.metadata.title:
            title = safe_text(str(reader.metadata.title)).strip()
    except Exception as exc:
        raise IngestError(f"Could not read this PDF ({exc}).") from exc
    return pages, {"metadata_title": title, "page_count": len(pages)}


def _norm_line(line: str) -> str:
    return re.sub(r"\d+", "#", re.sub(r"\s+", " ", line.strip().lower()))


def clean_pages(pages: list[dict]) -> list[dict]:
    """Remove repeated headers/footers and bare page numbers, re-join hyphenated words and broken lines."""
    split = [[ln for ln in p["text"].splitlines()] for p in pages]
    # Header/footer candidates: first/last 2 non-empty lines of each page that repeat across many pages.
    edge_counts: Counter[str] = Counter()
    for lines in split:
        non_empty = [ln for ln in lines if ln.strip()]
        for ln in set(non_empty[:2] + non_empty[-2:]):
            edge_counts[_norm_line(ln)] += 1
    threshold = max(3, int(0.5 * len(pages)) + 1)
    repeated = {key for key, count in edge_counts.items() if count >= threshold and key}

    cleaned = []
    for page, lines in zip(pages, split):
        non_empty_idx = [i for i, ln in enumerate(lines) if ln.strip()]
        edges = set(non_empty_idx[:2] + non_empty_idx[-2:])
        kept = []
        for i, ln in enumerate(lines):
            stripped = ln.strip()
            if i in edges and (_norm_line(ln) in repeated or re.fullmatch(r"(page\s*)?\d{1,4}", stripped, re.I)):
                continue
            kept.append(ln.rstrip())
        text = "\n".join(kept)
        text = re.sub(r"(\w)-\n(?=[a-z])", r"\1", text)        # re-join hyphenated words across lines
        text = re.sub(r"[ \t]*\n[ \t]*\n+", "\n\n", text)        # keep paragraph breaks
        text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)            # single line breaks -> spaces
        text = re.sub(r"[ \t]{2,}", " ", text).strip()
        cleaned.append({**page, "text": text})
    return cleaned


def check_text_layer(pages: list[dict]) -> None:
    total = sum(len(p["text"]) for p in pages)
    with_text = sum(1 for p in pages if len(p["text"]) >= 100)
    if not pages:
        raise IngestError("The PDF has no pages.")
    if total < MIN_TOTAL_CHARS or with_text / len(pages) < MIN_TEXT_PAGE_RATIO:
        raise IngestError(
            f"Not enough extractable text ({total} characters; {with_text} of {len(pages)} pages contain text). "
            "This PDF is probably a scanned image. PaperLens v1 does not run OCR, so it cannot answer from this file. "
            "Please upload a PDF whose text you can select and copy."
        )


# ---------------------------------------------------------------- chunking

def chunk_pages(paper_id: str, pages: list[dict]) -> list[dict]:
    """Split each page separately so every chunk maps to exactly one PDF page."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", ". ", "; ", ", ", " ", ""],
        keep_separator="end",
    )
    chunks = []
    for page in pages:
        if not page["text"]:
            continue
        for index, piece in enumerate(splitter.split_text(page["text"])):
            piece = piece.strip()
            if len(piece) < 40:
                continue
            chunks.append({
                "chunk_id": f"{paper_id[:8]}-p{page['page']:03d}-c{index:02d}",
                "text": piece,
                "metadata": {
                    "paper_id": paper_id,
                    "page": page["page"],
                    "page_label": page["page_label"],
                    "chunk_index": index,
                },
            })
    return chunks


# ---------------------------------------------------------------- overview

def build_overview(pages: list[dict]) -> list[dict]:
    """Summarise consecutive page groups. Each summary keeps the pages it was generated from."""
    groups: list[list[dict]] = [[]]
    size = 0
    for page in pages:
        if not page["text"]:
            continue
        if groups[-1] and size + len(page["text"]) > OVERVIEW_GROUP_CHARS:
            groups.append([])
            size = 0
        groups[-1].append(page)
        size += len(page["text"])
    prompt = load_prompt("overview")
    groups = [g for g in groups if g]

    def summarise(group: list[dict]) -> OverviewSummary:
        text = "\n\n".join(f"[PDF page {p['page']}]\n{p['text']}" for p in group)
        return structured_call(prompt, f"<paper_pages>\n{text}\n</paper_pages>", OverviewSummary)

    with ThreadPoolExecutor(max_workers=4) as pool:  # independent calls, so run a few in parallel
        results = list(pool.map(summarise, groups))
    return [{
        "overview_id": f"ov-{number + 1}",
        "pages": [p["page"] for p in group],
        "summary": result.summary,
        "key_points": result.key_points,
    } for number, (group, result) in enumerate(zip(groups, results))]


def guess_title(info: dict, pages: list[dict], filename: str) -> str:
    title = info.get("metadata_title", "")
    if title and not re.match(r"(microsoft word|untitled|\S+\.(docx?|pdf|tex))", title, re.I):
        return title[:200]
    first = next((p["text"] for p in pages if p["text"]), "")
    first_sentence = re.split(r"(?<=[.!?])\s|\n", first, maxsplit=1)[0].strip()
    if 10 <= len(first_sentence) <= 160:
        return first_sentence
    return re.sub(r"\.pdf$", "", filename, flags=re.I)


# ---------------------------------------------------------------- pipeline

def register_upload(pdf_bytes: bytes, filename: str) -> dict:
    """Store the PDF and create its status record. Returns existing metadata if the same file is already indexed."""
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise IngestError("PDF is larger than 50 MB.")
    if not pdf_bytes.startswith(b"%PDF"):
        raise IngestError("This file is not a PDF.")
    paper_id = paper_id_for(pdf_bytes)
    existing = storage.load_paper_meta(paper_id)
    if existing and existing.get("status") == "ready":
        return existing
    storage.paper_pdf_path(paper_id).write_bytes(pdf_bytes)
    meta = {
        "paper_id": paper_id, "filename": filename, "title": re.sub(r"\.pdf$", "", filename, flags=re.I),
        "status": "queued", "error": None, "failed_stage": None, "created_at": storage.now_iso(),
    }
    storage.save_paper_meta(paper_id, meta)
    return meta


def run_ingestion(paper_id: str) -> None:
    """Background job. Every stage updates the status file so the frontend can show progress."""
    stage = "parsing"
    try:
        meta = storage.load_paper_meta(paper_id) or {}
        storage.update_paper_meta(paper_id, status="parsing", error=None, failed_stage=None)
        pdf_bytes = storage.paper_pdf_path(paper_id).read_bytes()
        raw_pages, info = extract_pages(pdf_bytes)
        pages = clean_pages(raw_pages)
        check_text_layer(pages)
        storage.save_paper_json(paper_id, "pages.json", pages)
        labels_differ = any(p["page_label"] != str(p["page"]) for p in pages)

        stage = "indexing"
        storage.update_paper_meta(paper_id, status="indexing", page_count=len(pages),
                                  title=guess_title(info, pages, meta.get("filename", "")),
                                  page_labels_differ=labels_differ)
        chunks = chunk_pages(paper_id, pages)
        replace_paper_chunks(paper_id, chunks)
        storage.save_paper_json(paper_id, "chunks.json", chunks)

        stage = "summarizing"
        storage.update_paper_meta(paper_id, status="summarizing", chunk_count=len(chunks))
        overview = build_overview(pages)
        storage.save_paper_json(paper_id, "overview.json", overview)
        storage.update_paper_meta(paper_id, status="ready", overview_count=len(overview))
    except (IngestError, ModelError) as exc:
        storage.update_paper_meta(paper_id, status="failed", failed_stage=stage, error=str(exc))
    except Exception as exc:  # unexpected bug: keep the trace for debugging
        storage.update_paper_meta(paper_id, status="failed", failed_stage=stage,
                                  error=f"Unexpected error: {exc}", trace=traceback.format_exc()[-2000:])


def fetch_pdf_from_url(url: str) -> tuple[bytes, str]:
    """Download a direct PDF link (arXiv /abs/ links are converted to /pdf/). DOIs are not resolved."""
    url = url.strip()
    if not re.match(r"https?://", url, re.I):
        raise IngestError("Please paste a full http(s) link to a PDF. DOI resolution is not supported; upload the PDF instead.")
    url = re.sub(r"arxiv\.org/abs/", "arxiv.org/pdf/", url)
    request = urllib.request.Request(url, headers={"User-Agent": "PaperLens/1.0 (course prototype)"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read(MAX_PDF_BYTES + 1)
    except Exception as exc:
        raise IngestError(f"Could not download the PDF ({exc}).") from exc
    if not data.startswith(b"%PDF"):
        raise IngestError("The link did not return a PDF file. Open the paper's PDF link, or download and upload it.")
    name = url.rstrip("/").split("/")[-1] or "paper"
    return data, name if name.lower().endswith(".pdf") else f"{name}.pdf"
