"""
Topic-link suggestion and confirmation workflow.

Only confirmed links are persisted as TopicLink records.
Pending suggestions carry a SuggestedLink record that expires unless acted on.

Relation types (kept minimal in MVP)
-------------------------------------
  relates_to   — general semantic relatedness
  supersedes   — this artifact replaces/updates another
  depends_on   — this artifact builds on another
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from agent.core.storage import Base


# ---------------------------------------------------------------------------
# ORM Models
# ---------------------------------------------------------------------------


class TopicLink(Base):
    """Confirmed, persisted relationship between two artifacts."""

    __tablename__ = "topic_links"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("artifacts.id", ondelete="CASCADE"), nullable=False
    )
    target_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("artifacts.id", ondelete="CASCADE"), nullable=False
    )
    relation: Mapped[str] = mapped_column(
        String(64), nullable=False, default="relates_to"
    )
    # Evidence used to auto-suggest this link (preserved for audit).
    evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint("source_id", "target_id", "relation", name="uq_link_triple"),
        Index("ix_link_source", "source_id"),
        Index("ix_link_target", "target_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<TopicLink {self.source_id[:8]}→{self.target_id[:8]} [{self.relation}]>"
        )


class SuggestedLink(Base):
    """Pending link suggestion awaiting user confirmation."""

    __tablename__ = "suggested_links"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("artifacts.id", ondelete="CASCADE"), nullable=False
    )
    target_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("artifacts.id", ondelete="CASCADE"), nullable=False
    )
    relation: Mapped[str] = mapped_column(
        String(64), nullable=False, default="relates_to"
    )
    confidence: Mapped[float] = mapped_column(default=0.0)
    evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending"
    )  # pending | confirmed | rejected
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:
        return (
            f"<SuggestedLink {self.source_id[:8]}→{self.target_id[:8]} "
            f"conf={self.confidence:.2f} status={self.status}>"
        )


# ---------------------------------------------------------------------------
# Business logic
# ---------------------------------------------------------------------------


def suggest_links(
    session,
    *,
    source_artifact_id: str,
    top_k: int = 5,
    model_name: str = "all-MiniLM-L6-v2",
) -> list[SuggestedLink]:
    """
    Generate link suggestions for *source_artifact_id* based on semantic
    similarity to other artifacts' current-version snapshots.

    Only creates suggestions that do not already have a confirmed TopicLink
    or an existing pending suggestion for the same triple.
    """
    from sqlalchemy import select
    from agent.core.artifacts import Artifact, ArtifactVersion, VersionSnapshot
    from agent.core.versioning import get_version_content
    import numpy as np

    # Load source content.
    source: Optional[Artifact] = session.execute(
        select(Artifact).where(Artifact.id == source_artifact_id)
    ).scalar_one_or_none()
    if source is None:
        return []

    source_content = get_version_content(session, source)
    if not source_content:
        return []

    # Gather all other non-archived artifacts.
    others: list[Artifact] = list(
        session.execute(
            select(Artifact).where(
                Artifact.id != source_artifact_id,
                Artifact.archived == False,  # noqa: E712
            )
        ).scalars()
    )
    if not others:
        return []

    # Score via semantic similarity.
    try:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(model_name)
    except ImportError:
        return []

    texts = [source_content] + [get_version_content(session, o) or "" for o in others]
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    source_vec = embeddings[0]
    similarities = [
        float(np.dot(source_vec, embeddings[i + 1])) for i in range(len(others))
    ]

    # Sort by similarity descending.
    ranked = sorted(zip(others, similarities), key=lambda x: x[1], reverse=True)

    # Build set of already-confirmed or already-pending triples.
    confirmed_pairs: set[tuple[str, str]] = set(
        session.execute(
            select(TopicLink.target_id).where(TopicLink.source_id == source_artifact_id)
        ).scalars()
    )
    pending_pairs: set[tuple[str, str]] = set(
        session.execute(
            select(SuggestedLink.target_id).where(
                SuggestedLink.source_id == source_artifact_id,
                SuggestedLink.status == "pending",
            )
        ).scalars()
    )

    suggestions: list[SuggestedLink] = []
    for artifact, score in ranked[:top_k]:
        if artifact.id in confirmed_pairs or artifact.id in pending_pairs:
            continue
        sug = SuggestedLink(
            source_id=source_artifact_id,
            target_id=artifact.id,
            relation="relates_to",
            confidence=score,
            evidence=f"Semantic similarity={score:.4f}",
        )
        session.add(sug)
        suggestions.append(sug)

    return suggestions


def confirm_suggestion(session, suggestion_id: str) -> Optional[TopicLink]:
    """
    Confirm a pending SuggestedLink and create the corresponding TopicLink.
    Returns the new TopicLink or None if not found / already actioned.
    Does NOT commit.
    """
    from sqlalchemy import select

    sug: Optional[SuggestedLink] = session.execute(
        select(SuggestedLink).where(SuggestedLink.id == suggestion_id)
    ).scalar_one_or_none()
    if sug is None or sug.status != "pending":
        return None

    sug.status = "confirmed"
    session.add(sug)

    link = TopicLink(
        source_id=sug.source_id,
        target_id=sug.target_id,
        relation=sug.relation,
        evidence=sug.evidence,
    )
    session.add(link)
    return link


def reject_suggestion(session, suggestion_id: str) -> bool:
    """Mark a SuggestedLink as rejected. Does NOT commit."""
    from sqlalchemy import select

    sug: Optional[SuggestedLink] = session.execute(
        select(SuggestedLink).where(SuggestedLink.id == suggestion_id)
    ).scalar_one_or_none()
    if sug is None or sug.status != "pending":
        return False
    sug.status = "rejected"
    session.add(sug)
    return True


def list_pending_suggestions(session) -> list[SuggestedLink]:
    from sqlalchemy import select

    return list(
        session.execute(
            select(SuggestedLink)
            .where(SuggestedLink.status == "pending")
            .order_by(SuggestedLink.confidence.desc())
        ).scalars()
    )


def list_confirmed_links(session, artifact_id: str) -> list[TopicLink]:
    from sqlalchemy import select, or_

    return list(
        session.execute(
            select(TopicLink).where(
                or_(
                    TopicLink.source_id == artifact_id,
                    TopicLink.target_id == artifact_id,
                )
            )
        ).scalars()
    )
