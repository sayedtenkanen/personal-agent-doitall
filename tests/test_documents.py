"""
Tests for document lifecycle service including conflict detection.
"""

import pytest
from agent.core.storage import init_db, get_session
from agent.core.documents import (
    create_document,
    update_document,
    get_document_content,
    get_document_history,
)
from agent.core.artifacts import get_artifact_by_slug, ArtifactKind, get_current_version
from agent.core.conflicts import list_open_conflicts


@pytest.fixture(autouse=True)
def _init(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_DATA_DIR", str(tmp_path))
    import agent.core.storage as storage
    import agent.core.config as config

    storage._engine = None
    storage._SessionLocal = None
    config.settings = config.Settings()
    init_db()


def _create_onboarding():
    with get_session() as session:
        result = create_document(
            session,
            title="Onboarding Guide",
            slug="onboarding",
            content="# Welcome\n\nPlease read this guide.",
            changelog="Initial version",
        )
    return result


def test_create_document():
    result = _create_onboarding()
    assert result.version.semver == "1.0.0"
    assert result.artifact.slug == "onboarding"


def test_create_duplicate_slug_raises():
    _create_onboarding()
    with pytest.raises(ValueError, match="already exists"):
        with get_session() as session:
            create_document(session, title="Dup", slug="onboarding", content="x")


def test_update_document_minor_bump():
    _create_onboarding()

    with get_session() as session:
        artifact = get_artifact_by_slug(session, ArtifactKind.DOCUMENT, "onboarding")
        current_ver = get_current_version(session, artifact)
        base_id = current_ver.id

    with get_session() as session:
        result = update_document(
            session,
            slug="onboarding",
            new_content="# Welcome\n\nUpdated with buddy system info.",
            bump_kind="minor",
            changelog="Added buddy system section",
            base_version_id=base_id,
        )

    assert not result.is_conflict
    assert result.version.semver == "1.1.0"


def test_update_document_with_stale_base_creates_conflict():
    _create_onboarding()

    # First, get v1.0.0 base id.
    with get_session() as session:
        artifact = get_artifact_by_slug(session, ArtifactKind.DOCUMENT, "onboarding")
        v1_ver = get_current_version(session, artifact)
        v1_id = v1_ver.id

    # Advance to v1.1.0 legitimately.
    with get_session() as session:
        update_document(
            session,
            slug="onboarding",
            new_content="# Welcome v1.1",
            bump_kind="minor",
            changelog="First update",
            base_version_id=v1_id,
        )

    # Now attempt a stale write using old v1.0.0 base.
    with get_session() as session:
        result = update_document(
            session,
            slug="onboarding",
            new_content="# Welcome — concurrent edit",
            bump_kind="patch",
            changelog="Concurrent edit",
            base_version_id=v1_id,
        )

    assert result.is_conflict
    assert result.conflict_record is not None

    with get_session() as session:
        open_conflicts = list_open_conflicts(session)
    assert len(open_conflicts) == 1


def test_document_history_grows():
    _create_onboarding()

    with get_session() as session:
        artifact = get_artifact_by_slug(session, ArtifactKind.DOCUMENT, "onboarding")
        base_id = get_current_version(session, artifact).id

    with get_session() as session:
        update_document(
            session,
            slug="onboarding",
            new_content="v2",
            bump_kind="minor",
            changelog="v1.1",
            base_version_id=base_id,
        )

    with get_session() as session:
        versions = get_document_history(session, "onboarding")

    assert len(versions) == 2
    assert versions[0].semver == "1.0.0"
    assert versions[1].semver == "1.1.0"


def test_get_document_content_by_version():
    _create_onboarding()

    with get_session() as session:
        artifact = get_artifact_by_slug(session, ArtifactKind.DOCUMENT, "onboarding")
        base_id = get_current_version(session, artifact).id

    with get_session() as session:
        update_document(
            session,
            slug="onboarding",
            new_content="v2 content",
            bump_kind="minor",
            changelog="v1.1",
            base_version_id=base_id,
        )

    with get_session() as session:
        v1_content = get_document_content(session, "onboarding", "1.0.0")
        v2_content = get_document_content(session, "onboarding", "1.1.0")

    assert "Welcome" in v1_content
    assert v2_content == "v2 content"
