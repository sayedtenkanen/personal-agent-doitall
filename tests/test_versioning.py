"""
Tests for the SemVer engine.
"""

import pytest
from agent.core.versioning import parse_semver, next_semver, bump_version
from agent.core.storage import init_db, get_session
from agent.core.artifacts import create_artifact, ArtifactKind, get_artifact_by_slug


@pytest.fixture(autouse=True)
def _init(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_DATA_DIR", str(tmp_path))
    # Reset singletons so each test gets a fresh DB.
    import agent.core.storage as storage
    import agent.core.config as config

    storage._engine = None
    storage._SessionLocal = None
    config.settings = config.Settings()
    init_db()


def test_parse_semver():
    assert parse_semver("1.2.3") == (1, 2, 3)
    assert parse_semver("0.0.0") == (0, 0, 0)


def test_parse_semver_invalid():
    with pytest.raises(ValueError):
        parse_semver("1.2")
    with pytest.raises(ValueError):
        parse_semver("a.b.c")


def test_next_semver_patch():
    assert next_semver("1.2.3", "patch") == "1.2.4"


def test_next_semver_minor():
    assert next_semver("1.2.3", "minor") == "1.3.0"


def test_next_semver_major():
    assert next_semver("1.2.3", "major") == "2.0.0"


def test_bump_version_advances_current():
    with get_session() as session:
        artifact, v1 = create_artifact(
            session,
            kind=ArtifactKind.DOCUMENT,
            title="Test Doc",
            slug="test-doc",
            content="v1 content",
        )
        v2 = bump_version(
            session,
            artifact=artifact,
            new_content="v2 content",
            bump_kind="minor",
            changelog="Added section",
        )

    assert v2.semver == "1.1.0"
    assert artifact.current_version == "1.1.0"


def test_bump_version_snapshot_immutable():
    with get_session() as session:
        artifact, v1 = create_artifact(
            session,
            kind=ArtifactKind.DOCUMENT,
            title="Immutable Test",
            slug="immutable-test",
            content="original",
        )
        v1_snap_content = v1.snapshot.content
        assert v1_snap_content == "original"

        v2 = bump_version(
            session,
            artifact=artifact,
            new_content="updated",
            bump_kind="patch",
            changelog="Fix typo",
        )
        # v1 snapshot must still hold original content.
        assert v1.snapshot.content == "original"
        assert v2.snapshot.content == "updated"
