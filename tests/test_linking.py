"""
Tests for topic-link suggestion and confirmation workflow.
"""

import pytest
from agent.core.storage import init_db, get_session
from agent.core.artifacts import create_artifact, ArtifactKind
from agent.core.linking import (
    list_pending_suggestions,
    confirm_suggestion,
    reject_suggestion,
    list_confirmed_links,
    SuggestedLink,
    TopicLink,
)
from sqlalchemy import select


@pytest.fixture(autouse=True)
def _init(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_DATA_DIR", str(tmp_path))
    import agent.core.storage as storage
    import agent.core.config as config

    storage._engine = None
    storage._SessionLocal = None
    config.settings = config.Settings()
    init_db()


def _make_artifacts():
    with get_session() as session:
        a1, _ = create_artifact(
            session,
            kind=ArtifactKind.DOCUMENT,
            title="Onboarding",
            slug="onboarding",
            content="New employee onboarding process",
        )
        a2, _ = create_artifact(
            session,
            kind=ArtifactKind.DOCUMENT,
            title="HR Policy",
            slug="hr-policy",
            content="Human resources policies and procedures",
        )
        return a1.id, a2.id


def _make_suggestion(source_id: str, target_id: str):
    """Directly insert a SuggestedLink bypassing embedding model for unit tests."""
    with get_session() as session:
        sug = SuggestedLink(
            source_id=source_id,
            target_id=target_id,
            relation="relates_to",
            confidence=0.88,
            evidence="unit test",
        )
        session.add(sug)
    return sug.id


def test_pending_suggestion_appears_in_list():
    a1_id, a2_id = _make_artifacts()
    sug_id = _make_suggestion(a1_id, a2_id)

    with get_session() as session:
        pending = list_pending_suggestions(session)

    assert len(pending) == 1
    assert pending[0].id == sug_id


def test_confirm_suggestion_creates_link():
    a1_id, a2_id = _make_artifacts()
    sug_id = _make_suggestion(a1_id, a2_id)

    with get_session() as session:
        link = confirm_suggestion(session, sug_id)

    assert link is not None
    assert link.source_id == a1_id
    assert link.target_id == a2_id

    with get_session() as session:
        pending = list_pending_suggestions(session)
        links = list_confirmed_links(session, a1_id)

    assert len(pending) == 0
    assert len(links) == 1


def test_reject_suggestion_removes_from_pending():
    a1_id, a2_id = _make_artifacts()
    sug_id = _make_suggestion(a1_id, a2_id)

    with get_session() as session:
        ok = reject_suggestion(session, sug_id)

    assert ok

    with get_session() as session:
        pending = list_pending_suggestions(session)

    assert len(pending) == 0


def test_link_not_persisted_without_confirmation():
    a1_id, a2_id = _make_artifacts()
    _make_suggestion(a1_id, a2_id)

    with get_session() as session:
        links = list_confirmed_links(session, a1_id)

    # Must be empty — not confirmed.
    assert len(links) == 0
