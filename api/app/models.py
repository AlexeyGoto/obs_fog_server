from __future__ import annotations

import secrets
from datetime import datetime

from sqlalchemy import String, Integer, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.utcnow()


class User(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    telegram_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    tg_link_code: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)

    keep_clips: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_delete: Mapped[bool] = mapped_column(Boolean, default=True)
    max_telegram_mb: Mapped[int] = mapped_column(Integer, default=50)

    pcs: Mapped[list['PC']] = relationship(back_populates='owner', cascade='all,delete-orphan')

    def ensure_tg_link_code(self) -> str:
        if not self.tg_link_code:
            self.tg_link_code = secrets.token_urlsafe(8)
        return self.tg_link_code


class PC(Base):
    __tablename__ = 'pcs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)

    name: Mapped[str] = mapped_column(String(120))
    stream_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    owner: Mapped[User] = relationship(back_populates='pcs')
    sessions: Mapped[list['StreamSession']] = relationship(back_populates='pc', cascade='all,delete-orphan')


class StreamSession(Base):
    __tablename__ = 'stream_sessions'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pc_id: Mapped[int] = mapped_column(ForeignKey('pcs.id', ondelete='CASCADE'), index=True)

    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    clip_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    clip_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[str] = mapped_column(String(32), default='recording')
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

    pc: Mapped[PC] = relationship(back_populates='sessions')


class Job(Base):
    __tablename__ = 'jobs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default='pending', index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    payload: Mapped[str] = mapped_column(Text)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
