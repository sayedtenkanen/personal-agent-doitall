"""
Extra document service tests for import/list/read edge cases.
"""

from pathlib import Path

import pytest

from agent.core.artifacts import ArtifactKind, get_artifact_by_slug, get_current_version
from agent.core.documents import (
    create_document,
    get_document_content,
    get_document_history,
    import_external_document,
    list_documents,
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


def test_import_external_document_uses_defaults_when_missing_optional_fields():
    fake_path = Path("Team Handbook (Draft).pdf")

    with get_session() as session:
        result = import_external_document(session, file_path=fake_path)

    assert result.artifact.slug == "team-handbook-draft"
    assert result.version.semver == "1.0.0"

    with get_session() as session:
        imported = get_artifact_by_slug(
            session,
            ArtifactKind.DOCUMENT,
            "team-handbook-draft",
        )
        content = get_document_content(session, "team-handbook-draft", "1.0.0")

    assert imported is not None
    assert content is not None
    assert "Imported:" in content


def test_get_document_content_and_history_for_missing_slug():
    with get_session() as session:
        assert get_document_content(session, "missing") is None
        assert get_document_history(session, "missing") == []


def test_list_documents_include_archived_toggle():
    with get_session() as session:
        create_document(session, title="A", slug="a", content="one")
        create_document(session, title="B", slug="b", content="two")

        to_archive = get_artifact_by_slug(session, ArtifactKind.DOCUMENT, "b")
        to_archive.archived = True
        session.add(to_archive)
        session.flush()

        active_docs = list_documents(session)
        all_docs = list_documents(session, include_archived=True)

    active_slugs = {doc.slug for doc in active_docs}
    all_slugs = {doc.slug for doc in all_docs}
    assert "a" in active_slugs
    assert "b" not in active_slugs
    assert "b" in all_slugs
