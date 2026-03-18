"""
Chat session storage: ORM models and CRUD helpers.

Tables
------
chat_sessions   — one row per conversation (title, timestamps)
chat_messages   — one row per message (role: user|assistant|system, content)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agent.core.storage import Base


# ---------------------------------------------------------------------------
# ORM Models
# ---------------------------------------------------------------------------


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False, default="New Chat")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    messages: Mapped[list["ChatMessage"]] = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )

    def __repr__(self) -> str:
        return f"<ChatSession {self.id[:8]} {self.title!r}>"


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # user|assistant|system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    session: Mapped["ChatSession"] = relationship(
        "ChatSession", back_populates="messages"
    )

    __table_args__ = (Index("ix_chat_messages_session_id", "session_id"),)

    def __repr__(self) -> str:
        return f"<ChatMessage {self.role} session={self.session_id[:8]}>"


# ---------------------------------------------------------------------------
# CRUD helpers
# ---------------------------------------------------------------------------


def create_session(db, *, title: str = "New Chat") -> ChatSession:
    """Create a new chat session. Does NOT commit."""
    chat_session = ChatSession(title=title)
    db.add(chat_session)
    db.flush()
    return chat_session


def add_message(db, *, session_id: str, role: str, content: str) -> ChatMessage:
    """Append a message to a session. Does NOT commit."""
    msg = ChatMessage(session_id=session_id, role=role, content=content)
    db.add(msg)
    db.flush()
    return msg


def list_sessions(db) -> list[ChatSession]:
    from sqlalchemy import select

    return list(
        db.execute(
            select(ChatSession).order_by(ChatSession.updated_at.desc())
        ).scalars()
    )


def get_session_by_id(db, session_id: str) -> Optional[ChatSession]:
    from sqlalchemy import select

    return db.execute(
        select(ChatSession).where(ChatSession.id == session_id)
    ).scalar_one_or_none()


def get_messages(db, session_id: str) -> list[ChatMessage]:
    from sqlalchemy import select

    return list(
        db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at)
        ).scalars()
    )


def delete_session(db, session_id: str) -> bool:
    """Delete a session and all its messages. Does NOT commit."""
    from sqlalchemy import select

    session = db.execute(
        select(ChatSession).where(ChatSession.id == session_id)
    ).scalar_one_or_none()
    if session is None:
        return False
    db.delete(session)
    return True
