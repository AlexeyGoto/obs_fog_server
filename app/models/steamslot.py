"""
SteamSlot models for account and lease management.
"""
import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class LeaseStatus(str, enum.Enum):
    """Steam account lease status."""

    ACTIVE = "active"
    RELEASED = "released"
    EXPIRED = "expired"


class SteamAccount(BaseModel):
    """
    Steam account for slot assignment.

    Contains encrypted Steam credentials/files that can be leased to PCs.
    """

    __tablename__ = "steam_accounts"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_slots: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Encrypted file storage (SteamGuard, etc.)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    file_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    file_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_encrypted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    file_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    leases: Mapped[list["SteamLease"]] = relationship(
        "SteamLease", back_populates="account", cascade="all, delete-orphan"
    )

    @property
    def active_lease_count(self) -> int:
        """Count of active leases for this account."""
        return len([l for l in self.leases if l.status == LeaseStatus.ACTIVE])

    @property
    def available_slots(self) -> int:
        """Number of available slots."""
        return max(0, self.max_slots - self.active_lease_count)

    def __repr__(self) -> str:
        return f"<SteamAccount {self.name}>"


class SteamLease(BaseModel):
    """
    Steam account lease to a PC.

    Represents a temporary assignment of a Steam account to a streaming PC.
    """

    __tablename__ = "steam_leases"

    account_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("steam_accounts.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    pc_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("pcs.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    # Lease details
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[LeaseStatus] = mapped_column(
        Enum(LeaseStatus), default=LeaseStatus.ACTIVE, nullable=False, index=True
    )
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    account: Mapped["SteamAccount"] = relationship(
        "SteamAccount", back_populates="leases"
    )
    pc: Mapped["PC"] = relationship("PC")

    def __repr__(self) -> str:
        return f"<SteamLease {self.id} status={self.status}>"


# Import at bottom to avoid circular imports
from app.models.pc import PC  # noqa: E402, F401
