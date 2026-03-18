"""
Extra tests for conflict helper branches and resolution workflow.
"""

import pytest
from sqlalchemy import select

from agent.core.artifacts import (
    Artifact,
    ArtifactKind,
    get_artifact_by_slug,
    get_current_version,
)
from agent.core.conflicts import (
    ConflictRecord,
    is_stale,
    list_open_conflicts,
    resolve_conflict,
)
from agent.core.documents import create_document, update_document
from agent.core.storage import get_session, init_db


@pytest.fixture(autouse=True)
def _init(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_DATA_DIR", str(tmp_path))
    import agent.core.storage as storage
    import agent.core.config as config

    storage._engine = None
    storage._SessionLocal = None
    config.settings = config.Settings()
    init_db()


def test_is_stale_false_for_current_base_version():
    with get_session() as session:
        create_document(session, title="Doc", slug="doc", content="v1")

    with get_session() as session:
        artifact = get_artifact_by_slug(session, ArtifactKind.DOCUMENT, "doc")
        current = get_current_version(session, artifact)
        stale = is_stale(artifact, current.id, session)

    assert stale is False


def test_is_stale_false_when_no_current_version():
    with get_session() as session:
        artifact = Artifact(
            kind=ArtifactKind.DOCUMENT.value,
            title="No version",
            slug="no-version",
            current_version=None,
        )
        session.add(artifact)
        session.flush()
        stale = is_stale(artifact, "base-id", session)

    assert stale is False


def test_resolve_conflict_marks_record_closed():
    with get_session() as session:
        create_document(session, title="Guide", slug="guide", content="v1")

    with get_session() as session:
        artifact = get_artifact_by_slug(session, ArtifactKind.DOCUMENT, "guide")
        v1_id = get_current_version(session, artifact).id

    with get_session() as session:
        update_document(
            session,
            slug="guide",
            new_content="v1.1",
            bump_kind="minor",
            changelog="advance",
            base_version_id=v1_id,
        )

    with get_session() as session:
        stale_result = update_document(
            session,
            slug="guide",
            new_content="stale write",
            bump_kind="patch",
            changelog="stale",
            base_version_id=v1_id,
        )
        assert stale_result.is_conflict is True

    with get_session() as session:
        open_conflicts = list_open_conflicts(session)
        assert len(open_conflicts) == 1
        resolve_conflict(
            session,
            conflict_record=open_conflicts[0],
            resolution_note="merged manually",
        )

    with get_session() as session:
        open_conflicts = list_open_conflicts(session)
        record = session.execute(select(ConflictRecord)).scalar_one()

    assert open_conflicts == []
    assert record.resolved is True
    assert record.resolution_note == "merged manually"
