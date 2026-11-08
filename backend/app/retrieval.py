"""Chroma vector store. One persistent collection; every query is filtered to a single paper_id."""
from __future__ import annotations

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
    hits = []
    for chunk_id, text, meta, distance in zip(result["ids"][0], result["documents"][0],
                                              result["metadatas"][0], result["distances"][0]):
        hits.append({
            "chunk_id": chunk_id,
            "text": text,
            "page": int(meta["page"]),
            "page_label": str(meta.get("page_label", meta["page"])),
            "similarity": round(1 - float(distance), 4),
        })
    return hits


def count_chunks(paper_id: str) -> int:
    return len(_collection().get(where={"paper_id": paper_id}, include=[])["ids"])
