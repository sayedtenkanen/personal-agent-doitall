"""
Conflict detection and resolution.

Flow
----
1. Every write carries a base_version_id (the version the caller read from).
2. If artifact.current_version != base semver → stale write → create conflict copy.
3. The conflict copy is a new Artifact with kind preserved, title prefixed CONFLICT,
   and slug = original_slug + "__conflict__" + short_uuid.
4. The caller/user must compare and explicitly merge or discard the conflict copy.

ORM model: ConflictRecord ties original artifact ↔ conflict copy artifact.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agent.core.artifacts import (
    Artifact,
    ArtifactKind,
    ArtifactVersion,
    VersionSnapshot,
    _sha256,
    get_current_version,
)
from agent.core.storage import Base


# ---------------------------------------------------------------------------
# ORM Model
# ---------------------------------------------------------------------------


class ConflictRecord(Base):
    __tablename__ = "conflicts"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    original_artifact_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("artifacts.id", ondelete="CASCADE"), nullable=False
    )
    conflict_artifact_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("artifacts.id", ondelete="CASCADE"), nullable=False
    )
    # The version the conflicting writer had as their base.
    base_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    resolved: Mapped[bool] = mapped_column(default=False)
    resolution_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:
        return (
            f"<ConflictRecord orig={self.original_artifact_id!r} "
            f"copy={self.conflict_artifact_id!r} resolved={self.resolved}>"
        )


# ---------------------------------------------------------------------------
# Business logic
# ---------------------------------------------------------------------------


class StaleWriteError(Exception):
    """Raised when a write targets an outdated base version."""


def check_and_record_conflict(
    session,
    *,
    artifact: Artifact,
    base_version_id: str,
    incoming_content: str,
    content_type: str = "text/markdown",
) -> ConflictRecord:
    """
    Called when a stale write is detected (caller already verified staleness).

    Creates a conflict artifact copy at v1.0.0 containing the incoming content,
    then creates a ConflictRecord linking original → conflict copy.

    Does NOT commit.
    """
    short_id = str(uuid.uuid4())[:8]
    conflict_slug = f"{artifact.slug}__conflict__{short_id}"
    conflict_title = f"CONFLICT: {artifact.title}"

    conflict_artifact = Artifact(
        kind=artifact.kind,
        title=conflict_title,
        slug=conflict_slug,
        current_version="1.0.0",
    )
    session.add(conflict_artifact)
    session.flush()

    conflict_version = ArtifactVersion(
        artifact_id=conflict_artifact.id,
        semver="1.0.0",
        bump_kind=None,
        changelog=f"Conflict copy from base_version={base_version_id}",
    )
    session.add(conflict_version)
    session.flush()

    snapshot = VersionSnapshot(
        version_id=conflict_version.id,
        content=incoming_content,
        content_type=content_type,
        sha256=_sha256(incoming_content),
    )
    session.add(snapshot)

    record = ConflictRecord(
        original_artifact_id=artifact.id,
        conflict_artifact_id=conflict_artifact.id,
        base_version_id=base_version_id,
    )
    session.add(record)

    return record


def resolve_conflict(
    session,
    *,
    conflict_record: ConflictRecord,
    resolution_note: str = "",
) -> None:
    """
    Mark a conflict as resolved. Does NOT delete the conflict copy artifact
    (retain for audit). Does NOT commit.
    """
    conflict_record.resolved = True
    conflict_record.resolution_note = resolution_note
    session.add(conflict_record)


def list_open_conflicts(session) -> list[ConflictRecord]:
    from sqlalchemy import select

    return list(
        session.execute(
            select(ConflictRecord).where(ConflictRecord.resolved == False)  # noqa: E712
        ).scalars()
    )


def is_stale(artifact: Artifact, base_version_id: str, session) -> bool:
    """
    Return True if base_version_id is not the current version of the artifact.
    """
    current = get_current_version(session, artifact)
    if current is None:
        return False
    return current.id != base_version_id
