"""
Memory ingestion and episodic storage.

Memory entries are stored indefinitely (archive flag only, no hard deletes).
Each entry captures:
  - raw text (the episode or extracted fact)
  - normalized tags (list stored as comma-separated string)
  - entity references (people, projects, topics — comma-separated)
  - optional link to a related artifact

Embeddings are computed lazily on first retrieval pass and cached in the DB.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agent.core.storage import Base


# ---------------------------------------------------------------------------
# ORM Model
# ---------------------------------------------------------------------------


class MemoryEntry(Base):
    __tablename__ = "memory_entries"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    entities: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    # Serialised float list (space-separated) — populated lazily.
    embedding: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Optional back-reference to an artifact this memory came from.
    source_artifact_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True, index=True
    )
    archived: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (Index("ix_memory_archived", "archived"),)

    def tag_list(self) -> list[str]:
        return [t.strip() for t in self.tags.split(",") if t.strip()]

    def entity_list(self) -> list[str]:
        return [e.strip() for e in self.entities.split(",") if e.strip()]

    def __repr__(self) -> str:
        return f"<MemoryEntry {self.id[:8]} tags={self.tags!r}>"


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def add_memory(
    session,
    *,
    text: str,
    tags: list[str] | None = None,
    entities: list[str] | None = None,
    source_artifact_id: str | None = None,
) -> MemoryEntry:
    """
    Persist a new memory entry. Does NOT commit.
    Embedding is left empty here; computed lazily by the retrieval layer.
    """
    entry = MemoryEntry(
        text=text,
        tags=",".join(tags or []),
        entities=",".join(entities or []),
        source_artifact_id=source_artifact_id,
    )
    session.add(entry)
    session.flush()  # populate entry.id from DB default
    return entry


def list_memory(
    session,
    include_archived: bool = False,
    limit: int = 500,
) -> list[MemoryEntry]:
    from sqlalchemy import select

    stmt = select(MemoryEntry)
    if not include_archived:
        stmt = stmt.where(MemoryEntry.archived == False)  # noqa: E712
    stmt = stmt.order_by(MemoryEntry.created_at.desc()).limit(limit)
    return list(session.execute(stmt).scalars())


def archive_memory(session, entry_id: str) -> bool:
    from sqlalchemy import select

    entry = session.execute(
        select(MemoryEntry).where(MemoryEntry.id == entry_id)
    ).scalar_one_or_none()
    if entry is None:
        return False
    entry.archived = True
    session.add(entry)
    return True
