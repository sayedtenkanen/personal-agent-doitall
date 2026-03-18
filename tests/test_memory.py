"""
Tests for memory ingestion and BM25-only retrieval fallback.
"""

import pytest
from agent.core.storage import init_db, get_session
from agent.core.memory import add_memory, list_memory, archive_memory


@pytest.fixture(autouse=True)
def _init(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_DATA_DIR", str(tmp_path))
    import agent.core.storage as storage
    import agent.core.config as config

    storage._engine = None
    storage._SessionLocal = None
    config.settings = config.Settings()
    init_db()


def test_add_and_list_memory():
    with get_session() as session:
        e = add_memory(
            session, text="Discussed onboarding with Alice", tags=["onboarding", "hr"]
        )

    with get_session() as session:
        entries = list_memory(session)

    assert len(entries) == 1
    assert entries[0].text == "Discussed onboarding with Alice"
    assert "onboarding" in entries[0].tag_list()


def test_archive_hides_entry():
    with get_session() as session:
        e = add_memory(session, text="Old note")
        eid = e.id

    with get_session() as session:
        archive_memory(session, eid)

    with get_session() as session:
        entries = list_memory(session, include_archived=False)
        all_entries = list_memory(session, include_archived=True)

    assert len(entries) == 0
    assert len(all_entries) == 1


def test_memory_retention_indefinite():
    """Archive flag never deletes — retrievable with include_archived=True."""
    with get_session() as session:
        e = add_memory(session, text="Very old memory")
        eid = e.id
        archive_memory(session, eid)

    with get_session() as session:
        all_entries = list_memory(session, include_archived=True)

    assert any(x.id == eid for x in all_entries)
