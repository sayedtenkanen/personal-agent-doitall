"""
Extra tests for artifact utility functions and list/filter behavior.
"""

import pytest

from agent.core.artifacts import (
    Artifact,
    ArtifactKind,
    create_artifact,
    get_artifact_by_id,
    get_artifact_by_slug,
    get_current_version,
    get_version,
    list_artifacts,
    list_versions,
)
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


def test_get_artifact_by_id_and_slug_round_trip():
    with get_session() as session:
        created, version = create_artifact(
            session,
            kind=ArtifactKind.DOCUMENT,
            title="Playbook",
            slug="playbook",
            content="hello world",
        )
        found_by_id = get_artifact_by_id(session, created.id)
        found_by_slug = get_artifact_by_slug(session, ArtifactKind.DOCUMENT, "playbook")
        current = get_current_version(session, created)
        same_version = get_version(session, version.id)

    assert found_by_id is not None
    assert found_by_slug is not None
    assert found_by_id.id == created.id
    assert found_by_slug.slug == "playbook"
    assert current is not None
    assert current.semver == "1.0.0"
    assert same_version is not None
    assert same_version.id == version.id


def test_list_artifacts_filters_archived_by_default():
    with get_session() as session:
        a1, _ = create_artifact(
            session,
            kind=ArtifactKind.DOCUMENT,
            title="Visible",
            slug="visible",
            content="v",
        )
        a2, _ = create_artifact(
            session,
            kind=ArtifactKind.DOCUMENT,
            title="Archived",
            slug="archived",
            content="a",
        )
        archived_obj = get_artifact_by_id(session, a2.id)
        archived_obj.archived = True
        session.add(archived_obj)
        session.flush()

        active_docs = list_artifacts(session, kind=ArtifactKind.DOCUMENT)
        all_docs = list_artifacts(
            session,
            kind=ArtifactKind.DOCUMENT,
            include_archived=True,
        )

    active_slugs = {a.slug for a in active_docs}
    all_slugs = {a.slug for a in all_docs}
    assert a1.slug in active_slugs
    assert a2.slug not in active_slugs
    assert {a1.slug, a2.slug}.issubset(all_slugs)


def test_list_versions_returns_chronological_history():
    with get_session() as session:
        artifact, v1 = create_artifact(
            session,
            kind=ArtifactKind.DOCUMENT,
            title="History",
            slug="history",
            content="v1",
        )
        v2 = get_current_version(session, artifact)
        versions = list_versions(session, artifact.id)

    assert v2 is not None
    assert versions[0].id == v1.id
    assert versions[0].semver == "1.0.0"
