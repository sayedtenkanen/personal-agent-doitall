"""
Tests for topic-link suggestion and confirmation workflow.
"""

import sys
import types

import pytest
from agent.core.storage import init_db, get_session
from agent.core.artifacts import create_artifact, ArtifactKind
from agent.core.linking import (
    list_pending_suggestions,
    confirm_suggestion,
    reject_suggestion,
    list_confirmed_links,
    suggest_links,
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


def test_confirm_suggestion_returns_none_for_missing_or_actioned():
    a1_id, a2_id = _make_artifacts()
    sug_id = _make_suggestion(a1_id, a2_id)

    with get_session() as session:
        assert confirm_suggestion(session, "missing-id") is None

    with get_session() as session:
        ok = reject_suggestion(session, sug_id)
        assert ok is True

    with get_session() as session:
        assert confirm_suggestion(session, sug_id) is None


def test_reject_suggestion_returns_false_for_missing_or_actioned():
    a1_id, a2_id = _make_artifacts()
    sug_id = _make_suggestion(a1_id, a2_id)

    with get_session() as session:
        link = confirm_suggestion(session, sug_id)
        assert link is not None

    with get_session() as session:
        assert reject_suggestion(session, "missing-id") is False
        assert reject_suggestion(session, sug_id) is False


def test_suggest_links_returns_empty_for_unknown_source():
    with get_session() as session:
        suggestions = suggest_links(session, source_artifact_id="missing-id")
    assert suggestions == []


def test_suggest_links_creates_new_pending_with_mocked_model(monkeypatch):
    class _FakeSentenceTransformer:
        def __init__(self, _model_name):
            pass

        def encode(self, texts, normalize_embeddings=True, show_progress_bar=False):
            # Source ranks highest with "best", then "mid", then "low".
            vectors = []
            for text in texts:
                if "source" in text:
                    vectors.append([1.0, 0.0])
                elif "best" in text:
                    vectors.append([0.9, 0.1])
                elif "mid" in text:
                    vectors.append([0.6, 0.4])
                else:
                    vectors.append([0.1, 0.9])
            return vectors

    fake_module = types.SimpleNamespace(SentenceTransformer=_FakeSentenceTransformer)
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    with get_session() as session:
        source, _ = create_artifact(
            session,
            kind=ArtifactKind.DOCUMENT,
            title="Source",
            slug="source",
            content="source text",
        )
        best, _ = create_artifact(
            session,
            kind=ArtifactKind.DOCUMENT,
            title="Best",
            slug="best",
            content="best match",
        )
        mid, _ = create_artifact(
            session,
            kind=ArtifactKind.DOCUMENT,
            title="Mid",
            slug="mid",
            content="mid match",
        )
        low, _ = create_artifact(
            session,
            kind=ArtifactKind.DOCUMENT,
            title="Low",
            slug="low",
            content="low match",
        )

        # Existing confirmed and pending pairs should be skipped.
        session.add(
            TopicLink(
                source_id=source.id,
                target_id=best.id,
                relation="relates_to",
                evidence="seed",
            )
        )
        session.add(
            SuggestedLink(
                source_id=source.id,
                target_id=mid.id,
                relation="relates_to",
                confidence=0.5,
                evidence="seed pending",
                status="pending",
            )
        )
        session.flush()

        suggestions = suggest_links(session, source_artifact_id=source.id, top_k=5)

    assert len(suggestions) == 1
    assert suggestions[0].target_id == low.id
    assert suggestions[0].status == "pending"
