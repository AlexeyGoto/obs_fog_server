from __future__ import annotations

import datetime as dt
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base


UTCNOW = lambda: dt.datetime.now(dt.timezone.utc)


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_slots: Mapped[int] = mapped_column(Integer, default=5, nullable=False)

    file_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    file_content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    file_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    file_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_encrypted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    file_updated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=UTCNOW, nullable=False)

    pcs: Mapped[list["PC"]] = relationship(back_populates="account")


class PC(Base):
    __tablename__ = "pcs"
    __table_args__ = (UniqueConstraint("name", name="uq_pcs_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    api_key: Mapped[str] = mapped_column(String(256), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    account: Mapped[Account | None] = relationship(back_populates="pcs")

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=UTCNOW, nullable=False)


class Lease(Base):
    __tablename__ = "leases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    pc_id: Mapped[int] = mapped_column(ForeignKey("pcs.id"), nullable=False)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)

    token: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=UTCNOW, nullable=False)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    released_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

    pc: Mapped[PC] = relationship()
    account: Mapped[Account] = relationship()
