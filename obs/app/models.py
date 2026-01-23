from __future__ import annotations

import datetime as dt
from sqlalchemy import String, Integer, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base


def utcnow() -> dt.datetime:
    return dt.datetime.utcnow()


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    tg_chat_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    # Одобрение через Telegram (production gate)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    approval_status: Mapped[str] = mapped_column(String(32), default="pending")  # pending/approved/denied
    approval_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approval_requested_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    approval_notified_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    approval_decided_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    approval_decided_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    approval_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    pcs: Mapped[list["PC"]] = relationship(back_populates="user")


class PC(Base):
    __tablename__ = "pcs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    stream_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    user: Mapped["User"] = relationship(back_populates="pcs")
    sessions: Mapped[list["StreamSession"]] = relationship(back_populates="pc", cascade="all,delete-orphan")


class StreamSession(Base):
    __tablename__ = "stream_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pc_id: Mapped[int] = mapped_column(ForeignKey("pcs.id"), index=True)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    ended_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="live")  # live, done, error
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    clip_job: Mapped["ClipJob | None"] = relationship(back_populates="session", uselist=False, cascade="all,delete-orphan")
    pc: Mapped["PC"] = relationship(back_populates="sessions")


class ClipJob(Base):
    __tablename__ = "clip_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("stream_sessions.id"), unique=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending, processing, sent, too_big, failed
    result_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    session: Mapped["StreamSession"] = relationship(back_populates="clip_job")
