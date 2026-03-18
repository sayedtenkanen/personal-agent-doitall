"""
Artifact registry: ORM models and CRUD helpers.

Every piece of content the agent manages (document, memory entry, prompt/config)
is an Artifact.  Artifacts carry versioned snapshots so history is never lost.

Tables
------
artifacts        — one row per logical artifact (UUID, kind, title, current semver)
versions         — one row per version of an artifact (semver, changelog, timestamp)
version_snapshots — immutable content blob per version (stored as text + checksum)
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agent.core.storage import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ArtifactKind(str, Enum):
    DOCUMENT = "document"
    MEMORY = "memory"
    CONFIG = "config"


# ---------------------------------------------------------------------------
# ORM Models
# ---------------------------------------------------------------------------


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    # Slug / short name for CLI look-ups; must be unique within a kind.
    slug: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    current_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    archived: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    versions: Mapped[list["ArtifactVersion"]] = relationship(
        "ArtifactVersion", back_populates="artifact", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("kind", "slug", name="uq_artifact_kind_slug"),)

    def __repr__(self) -> str:
        return f"<Artifact {self.kind}:{self.slug} v{self.current_version}>"


class ArtifactVersion(Base):
    __tablename__ = "versions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    artifact_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("artifacts.id", ondelete="CASCADE"), nullable=False
    )
    semver: Mapped[str] = mapped_column(String(32), nullable=False)
    bump_kind: Mapped[Optional[str]] = mapped_column(
        String(8), nullable=True
    )  # major/minor/patch
    changelog: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    artifact: Mapped["Artifact"] = relationship("Artifact", back_populates="versions")
    snapshot: Mapped[Optional["VersionSnapshot"]] = relationship(
        "VersionSnapshot",
        back_populates="version",
        uselist=False,
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("artifact_id", "semver", name="uq_version_artifact_semver"),
        Index("ix_versions_artifact_id", "artifact_id"),
    )

    def __repr__(self) -> str:
        return f"<ArtifactVersion {self.artifact_id} @ {self.semver}>"


class VersionSnapshot(Base):
    __tablename__ = "version_snapshots"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("versions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(
        String(64), nullable=False, default="text/markdown"
    )
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    version: Mapped["ArtifactVersion"] = relationship(
        "ArtifactVersion", back_populates="snapshot"
    )

    def __repr__(self) -> str:
        return f"<VersionSnapshot version={self.version_id} sha256={self.sha256[:8]}>"


# ---------------------------------------------------------------------------
# CRUD helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def create_artifact(
    session,
    *,
    kind: ArtifactKind,
    title: str,
    slug: str,
    content: str,
    content_type: str = "text/markdown",
    changelog: str = "Initial version",
) -> tuple["Artifact", "ArtifactVersion"]:
    """
    Create a new artifact at v1.0.0 with an immutable snapshot.
    Returns (artifact, version).
    """
    artifact = Artifact(
        kind=kind.value,
        title=title,
        slug=slug,
        current_version="1.0.0",
    )
    session.add(artifact)
    session.flush()  # populate artifact.id

    version = ArtifactVersion(
        artifact_id=artifact.id,
        semver="1.0.0",
        bump_kind=None,
        changelog=changelog,
    )
    session.add(version)
    session.flush()

    snapshot = VersionSnapshot(
        version_id=version.id,
        content=content,
        content_type=content_type,
        sha256=_sha256(content),
    )
    session.add(snapshot)
    session.flush()  # populate version.snapshot back-reference

    return artifact, version


def get_artifact_by_slug(
    session, kind: ArtifactKind, slug: str
) -> Optional["Artifact"]:
    from sqlalchemy import select

    stmt = select(Artifact).where(Artifact.kind == kind.value, Artifact.slug == slug)
    return session.execute(stmt).scalar_one_or_none()


def get_artifact_by_id(session, artifact_id: str) -> Optional["Artifact"]:
    from sqlalchemy import select

    stmt = select(Artifact).where(Artifact.id == artifact_id)
    return session.execute(stmt).scalar_one_or_none()


def list_artifacts(
    session, kind: Optional[ArtifactKind] = None, include_archived: bool = False
):
    from sqlalchemy import select

    stmt = select(Artifact)
    if kind:
        stmt = stmt.where(Artifact.kind == kind.value)
    if not include_archived:
        stmt = stmt.where(Artifact.archived == False)  # noqa: E712
    stmt = stmt.order_by(Artifact.updated_at.desc())
    return list(session.execute(stmt).scalars())


def get_version(session, version_id: str) -> Optional["ArtifactVersion"]:
    from sqlalchemy import select

    return session.execute(
        select(ArtifactVersion).where(ArtifactVersion.id == version_id)
    ).scalar_one_or_none()


def get_current_version(session, artifact: "Artifact") -> Optional["ArtifactVersion"]:
    from sqlalchemy import select

    return session.execute(
        select(ArtifactVersion).where(
            ArtifactVersion.artifact_id == artifact.id,
            ArtifactVersion.semver == artifact.current_version,
        )
    ).scalar_one_or_none()


def list_versions(session, artifact_id: str) -> list["ArtifactVersion"]:
    from sqlalchemy import select

    return list(
        session.execute(
            select(ArtifactVersion)
            .where(ArtifactVersion.artifact_id == artifact_id)
            .order_by(ArtifactVersion.created_at.asc())
        ).scalars()
    )
