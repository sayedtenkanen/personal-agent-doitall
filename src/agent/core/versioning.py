"""
Semantic versioning engine.

Rules
-----
- Every artifact starts at 1.0.0.
- Bumps are: MAJOR (breaking meaning change), MINOR (new info), PATCH (fix/typo).
- Bump kind is always chosen explicitly by the user via CLI/web prompt.
- Each new version gets an immutable VersionSnapshot.
- current_version on the Artifact always points to the latest accepted version.

Public API
----------
bump_version(session, artifact, new_content, bump_kind, changelog) -> ArtifactVersion
parse_semver(v) -> (major, minor, patch)
next_semver(v, bump_kind) -> str
"""

from __future__ import annotations

import hashlib
import re
from typing import Literal

from agent.core.artifacts import (
    Artifact,
    ArtifactVersion,
    VersionSnapshot,
    _sha256,
    get_current_version,
)

BumpKind = Literal["major", "minor", "patch"]

_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def parse_semver(v: str) -> tuple[int, int, int]:
    """Parse 'MAJOR.MINOR.PATCH' string into an integer triple."""
    m = _SEMVER_RE.match(v)
    if not m:
        raise ValueError(f"Invalid semver string: {v!r}")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def next_semver(current: str, bump_kind: BumpKind) -> str:
    """Return the next semver string given a bump kind."""
    major, minor, patch = parse_semver(current)
    if bump_kind == "major":
        return f"{major + 1}.0.0"
    if bump_kind == "minor":
        return f"{major}.{minor + 1}.0"
    # patch
    return f"{major}.{minor}.{patch + 1}"


def bump_version(
    session,
    *,
    artifact: Artifact,
    new_content: str,
    bump_kind: BumpKind,
    changelog: str,
    content_type: str = "text/markdown",
) -> ArtifactVersion:
    """
    Create a new ArtifactVersion + VersionSnapshot and advance artifact.current_version.

    Does NOT commit — caller manages the transaction.
    """
    if artifact.current_version is None:
        raise ValueError(
            f"Artifact {artifact.id!r} has no current version to bump from."
        )

    new_semver = next_semver(artifact.current_version, bump_kind)

    version = ArtifactVersion(
        artifact_id=artifact.id,
        semver=new_semver,
        bump_kind=bump_kind,
        changelog=changelog,
    )
    session.add(version)
    session.flush()

    snapshot = VersionSnapshot(
        version_id=version.id,
        content=new_content,
        content_type=content_type,
        sha256=_sha256(new_content),
    )
    session.add(snapshot)
    session.flush()  # populate version.snapshot back-reference

    # Advance the current-version pointer.
    artifact.current_version = new_semver
    session.add(artifact)

    return version


def get_version_content(
    session, artifact: Artifact, semver: str | None = None
) -> str | None:
    """
    Return the snapshot content for *semver* (default: current_version).
    Returns None if the version or snapshot does not exist.
    """
    from sqlalchemy import select
    from agent.core.artifacts import ArtifactVersion, VersionSnapshot

    target = semver or artifact.current_version
    if target is None:
        return None

    row = session.execute(
        select(VersionSnapshot)
        .join(ArtifactVersion, VersionSnapshot.version_id == ArtifactVersion.id)
        .where(
            ArtifactVersion.artifact_id == artifact.id,
            ArtifactVersion.semver == target,
        )
    ).scalar_one_or_none()

    return row.content if row else None
