"""
PC, StreamSession, and ClipJob models for streaming management.
"""
import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class SessionStatus(str, enum.Enum):
    """Stream session status."""

    LIVE = "live"
    DONE = "done"
    ERROR = "error"


class ClipStatus(str, enum.Enum):
    """Clip job status."""

    PENDING = "pending"
    PROCESSING = "processing"
    SENT = "sent"
    STORED = "stored"
    TOO_BIG = "too_big"
    FAILED = "failed"


class PC(BaseModel):
    """
    PC/streaming source configuration.

    Represents a streaming source (OBS instance) that can push RTMP streams.
    Each PC has a unique stream key for authentication.
    """

    __tablename__ = "pcs"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    stream_key: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="pcs")
    sessions: Mapped[list["StreamSession"]] = relationship(
        "StreamSession", back_populates="pc", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<PC {self.name}>"


class StreamSession(BaseModel):
    """
    Individual streaming session.

    Created when a stream starts (on_publish hook) and updated when it ends.
    """

    __tablename__ = "stream_sessions"

    pc_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pcs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus), default=SessionStatus.LIVE, nullable=False
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    pc: Mapped["PC"] = relationship("PC", back_populates="sessions")
    clip_job: Mapped["ClipJob | None"] = relationship(
        "ClipJob", back_populates="session", uselist=False
    )

    def __repr__(self) -> str:
        return f"<StreamSession {self.id} status={self.status}>"


class ClipJob(BaseModel):
    """
    Background job for creating clip from HLS stream.

    Created when a stream session ends. Worker picks up pending jobs,
    converts HLS to MP4, and optionally sends to Telegram.
    """

    __tablename__ = "clip_jobs"

    session_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("stream_sessions.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    status: Mapped[ClipStatus] = mapped_column(
        Enum(ClipStatus), default=ClipStatus.PENDING, nullable=False, index=True
    )
    result_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Relationships
    session: Mapped["StreamSession"] = relationship(
        "StreamSession", back_populates="clip_job"
    )

    def __repr__(self) -> str:
        return f"<ClipJob {self.id} status={self.status}>"


# Import at bottom to avoid circular imports
from app.models.user import User  # noqa: E402, F401
