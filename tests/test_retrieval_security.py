"""
Security-focused tests for retrieval error handling behavior.
"""

import logging

import numpy as np
import pytest

from agent.core.memory import add_memory
from agent.core.storage import _get_session_factory, get_session, init_db
from agent.core import retrieval


@pytest.fixture(autouse=True)
def _init(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_DATA_DIR", str(tmp_path))
    import agent.core.storage as storage
    import agent.core.config as config

    storage._engine = None
    storage._SessionLocal = None
    config.settings = config.Settings()
    init_db()


class _FakeModel:
    def encode(self, texts, normalize_embeddings=True, show_progress_bar=False):
        vectors = []
        for text in texts:
            if "alpha" in text.lower():
                vectors.append(np.array([1.0, 0.0], dtype=np.float32))
            else:
                vectors.append(np.array([0.0, 1.0], dtype=np.float32))
        return np.array(vectors, dtype=np.float32)


def test_search_survives_embedding_cache_flush_failure(monkeypatch, caplog):
    with get_session() as session:
        add_memory(session, text="alpha incident report", tags=["security"])
        add_memory(session, text="beta backlog item", tags=["ops"])

    factory = _get_session_factory()
    session = factory()

    def _fail_flush():
        raise RuntimeError("simulated flush failure")

    monkeypatch.setattr(session, "flush", _fail_flush)
    monkeypatch.setattr(retrieval, "_get_model", lambda _name: _FakeModel())

    with caplog.at_level(logging.WARNING):
        results = retrieval.search(session, "alpha", top_k=2)

    assert len(results) == 2
    assert results[0].rank == 1
    assert "Embedding cache flush failed" in caplog.text

    session.rollback()
    session.close()
