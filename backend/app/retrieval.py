"""Chroma vector store. One persistent collection; every query is filtered to a single paper_id."""
from __future__ import annotations

import re
from functools import lru_cache

import chromadb

from .config import settings
from .llm import embed_query, embed_texts

COLLECTION = "paper_chunks"


@lru_cache(maxsize=1)
def _collection():
    client = chromadb.PersistentClient(path=str(settings.data_dir / "chroma"))
    # Embeddings are computed by us (OpenRouter), so Chroma's own embedding function is never used.
    return client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"}, embedding_function=None)


def replace_paper_chunks(paper_id: str, chunks: list[dict]) -> None:
    """(Re)index one paper: delete its old chunks, embed the new ones, add them."""
    collection = _collection()
    collection.delete(where={"paper_id": paper_id})
    if not chunks:
        return
    vectors = embed_texts([c["text"] for c in chunks])
    collection.add(
        ids=[c["chunk_id"] for c in chunks],
        embeddings=vectors,
        documents=[c["text"] for c in chunks],
        metadatas=[c["metadata"] for c in chunks],
    )


def search(paper_id: str, query: str, k: int | None = None) -> list[dict]:
    """Top-k chunks of THIS paper for the query, with cosine similarity (1 - distance)."""
    result = _collection().query(
        query_embeddings=[embed_query(query)],
        n_results=k or settings.top_k,
        where={"paper_id": paper_id},
        include=["documents", "metadatas", "distances"],
    )
    return [_hit(chunk_id, text, meta, round(1 - float(distance), 4))
            for chunk_id, text, meta, distance in zip(result["ids"][0], result["documents"][0],
                                                      result["metadatas"][0], result["distances"][0])]


def _hit(chunk_id: str, text: str, meta: dict, similarity: float | None) -> dict:
    hit = {
        "chunk_id": chunk_id,
        "text": text,
        "page": int(meta["page"]),
        "page_label": str(meta.get("page_label", meta["page"])),
        "similarity": similarity,
        "kind": meta.get("kind", "paper"),   # "paper" (original passage) or "figure" (generated description + caption)
    }
    if hit["kind"] == "figure":
        hit["label"] = meta.get("label", "")
        hit["caption"] = meta.get("caption", "")
    return hit


_FIGURE_REF = re.compile(r"\b(fig(?:ure)?\.?|table)\s*(\d+(?:\.\d+)*)", re.I)
_FIGURE_REF_ZH = re.compile(r"(图|圖|表)\s*(\d+(?:\.\d+)*)")


_FIGURE_WORD = re.compile(r"\b(fig(?:ure)?s?|tables?|charts?|graphs?|plots?|diagrams?|images?|pictures?)\b|图|圖|表", re.I)
_PAGE_REF = re.compile(r"\b(?:page|p\.)\s*(\d{1,4})\b|第\s*(\d{1,4})\s*[页頁]", re.I)


def figures_named_in(paper_id: str, *texts: str) -> list[dict]:
    """Figures/tables the learner points to, so they are always included: by number ("Figure 3", "table 2.4", "图 3"),
    or by page when the message also talks about a figure ("the chart on page 3"; needed for uncaptioned figures)."""
    labels, pages = set(), set()
    for text in texts:
        text = text or ""
        for word, number in _FIGURE_REF.findall(text) + _FIGURE_REF_ZH.findall(text):
            labels.add(("Table" if word.lower().startswith("tab") or word == "表" else "Figure") + " " + number)
        if _FIGURE_WORD.search(text):
            pages.update(int(a or b) for a, b in _PAGE_REF.findall(text))
    if not labels and not pages:
        return []
    got = _collection().get(where={"$and": [{"paper_id": paper_id}, {"kind": "figure"}]}, include=["documents", "metadatas"])
    return [_hit(cid, text, meta, None) for cid, text, meta in zip(got["ids"], got["documents"], got["metadatas"])
            if meta.get("label") in labels or int(meta.get("page", 0)) in pages]


def count_chunks(paper_id: str) -> int:
    return len(_collection().get(where={"paper_id": paper_id}, include=[])["ids"])
