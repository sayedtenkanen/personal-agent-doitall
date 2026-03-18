"""
Hybrid retrieval: BM25 (lexical) + sentence-transformers (semantic).

Strategy
--------
1. Build a BM25 index over all active memory entries (in-process, no persistence).
2. Compute cosine-similarity scores using a local embedding model.
3. Fuse scores with Reciprocal Rank Fusion (RRF) and return ranked candidates.

Embedding model is loaded lazily; first call triggers the download/cache.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from agent.core.memory import MemoryEntry, list_memory


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class SearchResult:
    entry: MemoryEntry
    bm25_score: float
    semantic_score: float
    rrf_score: float
    rank: int


# ---------------------------------------------------------------------------
# Lazy model loading
# ---------------------------------------------------------------------------

_model = None


def _get_model(model_name: str):
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer

            _model = SentenceTransformer(model_name)
        except ImportError:
            raise ImportError(
                "sentence-transformers is required for semantic search. "
                "Install it with: pip install sentence-transformers"
            )
    return _model


def _tokenize(text: str) -> list[str]:
    """Simple whitespace+punctuation tokenizer shared by BM25 indexing."""
    return re.findall(r"\w+", text.lower())


# ---------------------------------------------------------------------------
# Embedding helpers
# ---------------------------------------------------------------------------


def _embed(model, texts: list[str]) -> np.ndarray:
    return model.encode(texts, normalize_embeddings=True, show_progress_bar=False)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity for already-normalized vectors."""
    return float(np.dot(a, b))


def _store_embedding(session, entry: MemoryEntry, vector: np.ndarray) -> None:
    entry.embedding = " ".join(f"{v:.6f}" for v in vector.tolist())
    session.add(entry)


def _load_embedding(entry: MemoryEntry) -> Optional[np.ndarray]:
    if not entry.embedding:
        return None
    return np.array([float(x) for x in entry.embedding.split()], dtype=np.float32)


# ---------------------------------------------------------------------------
# RRF fusion
# ---------------------------------------------------------------------------


def _rrf(ranks: list[list[int]], k: int = 60) -> list[float]:
    """Reciprocal Rank Fusion across multiple ranked lists (same length)."""
    n = len(ranks[0])
    scores = [0.0] * n
    for rank_list in ranks:
        for pos, idx in enumerate(rank_list):
            scores[idx] += 1.0 / (k + pos + 1)
    return scores


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def search(
    session,
    query: str,
    *,
    top_k: int = 10,
    model_name: str = "all-MiniLM-L6-v2",
) -> list[SearchResult]:
    """
    Search memory entries using hybrid BM25 + semantic retrieval.

    Returns up to *top_k* results sorted by RRF score descending.
    """
    from rank_bm25 import BM25Okapi

    entries = list_memory(session)
    if not entries:
        return []

    # -- BM25 pass ----------------------------------------------------------
    tokenized_corpus = [_tokenize(e.text) for e in entries]
    bm25 = BM25Okapi(tokenized_corpus)
    bm25_scores = bm25.get_scores(_tokenize(query))
    bm25_rank_order = list(np.argsort(bm25_scores)[::-1])

    # -- Semantic pass -------------------------------------------------------
    model = _get_model(model_name)
    query_vec = _embed(model, [query])[0]

    # Re-use cached embeddings; compute missing ones.
    needs_embed = [i for i, e in enumerate(entries) if not e.embedding]
    if needs_embed:
        texts = [entries[i].text for i in needs_embed]
        vecs = _embed(model, texts)
        for i, vec in zip(needs_embed, vecs):
            _store_embedding(session, entries[i], vec)
        try:
            session.flush()
        except Exception:
            pass  # best-effort caching; retrieval still works from in-memory vecs

    sem_scores = []
    for i, e in enumerate(entries):
        vec = _load_embedding(e)
        if vec is None:
            # entry was just embedded above but session may not have flushed
            idx_in_needs = needs_embed.index(i) if i in needs_embed else -1
            if idx_in_needs >= 0:
                vec = _embed(model, [e.text])[0]
            else:
                vec = np.zeros(query_vec.shape, dtype=np.float32)
        sem_scores.append(_cosine(query_vec, vec))

    sem_scores_arr = np.array(sem_scores)
    sem_rank_order = list(np.argsort(sem_scores_arr)[::-1])

    # Build index→rank mapping for RRF
    n = len(entries)
    bm25_positional = [0] * n
    sem_positional = [0] * n
    for rank, idx in enumerate(bm25_rank_order):
        bm25_positional[idx] = rank
    for rank, idx in enumerate(sem_rank_order):
        sem_positional[idx] = rank

    rrf_scores = _rrf([bm25_rank_order, sem_rank_order])

    results: list[SearchResult] = [
        SearchResult(
            entry=entries[i],
            bm25_score=float(bm25_scores[i]),
            semantic_score=float(sem_scores_arr[i]),
            rrf_score=rrf_scores[i],
            rank=0,
        )
        for i in range(n)
    ]

    results.sort(key=lambda r: r.rrf_score, reverse=True)
    for rank, r in enumerate(results[:top_k], start=1):
        r.rank = rank

    return results[:top_k]
