"""
User model with roles and approval system.
"""
import enum
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class UserRole(str, enum.Enum):
    """User role enumeration.

    TRIAL: 14-day trial, up to 3 PCs, no SteamSlot
    OBS: Paid, up to 3 PCs, no SteamSlot
    PREMIUM: Paid, unlimited PCs + SteamSlot
    ADMIN: Full access
    """

    TRIAL = "trial"
    OBS = "obs"
    PREMIUM = "premium"
    ADMIN = "admin"


class ApprovalStatus(str, enum.Enum):
    """User approval status."""

    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"


class User(BaseModel):
    """
    User model for authentication and authorization.

    Attributes:
        email: Unique email address for login
        password_hash: Bcrypt hashed password
        role: User role (user, premium, admin)
        is_active: Whether the account is enabled
        is_approved: Whether the account is approved (for approval gate)

        # Telegram integration
        tg_chat_id: Linked Telegram chat ID for notifications

        # Approval workflow
        approval_status: Current approval status
        approval_token: Token for approval process
        approval_requested_at: When approval was requested
        approval_decided_at: When approval was decided
        approval_decided_by: Who decided (admin ID)
        approval_note: Note from admin

        # Premium
        premium_until: Premium subscription expiration date
    """

    __tablename__ = "users"

    # Core authentication
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # Role and status
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole), default=UserRole.TRIAL, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Trial period (14 days from registration)
    trial_ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Telegram integration
    tg_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)

    # Approval workflow
    approval_status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus), default=ApprovalStatus.PENDING, nullable=False
    )
    approval_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approval_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approval_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approval_decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approval_decided_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    approval_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Premium subscription
    premium_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    pcs: Mapped[list["PC"]] = relationship(
        "PC", back_populates="user", cascade="all, delete-orphan"
    )
    payments: Mapped[list["Payment"]] = relationship(
        "Payment", back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def is_premium(self) -> bool:
        """Check if user has active premium subscription (unlimited PCs + SteamSlot)."""
        if self.role == UserRole.ADMIN:
            return True
        if self.role == UserRole.PREMIUM:
            if self.premium_until:
                now = datetime.now(timezone.utc)
                premium_end = self.premium_until
                if premium_end.tzinfo is None:
                    premium_end = premium_end.replace(tzinfo=timezone.utc)
                return premium_end > now
            return True  # Premium without expiration
        return False

    @property
    def is_trial_active(self) -> bool:
        """Check if trial period is still active."""
        if self.role != UserRole.TRIAL:
            return False
        if self.trial_ends_at:
            # Handle both timezone-aware and naive datetimes (SQLite vs PostgreSQL)
            now = datetime.now(timezone.utc)
            trial_end = self.trial_ends_at
            if trial_end.tzinfo is None:
                trial_end = trial_end.replace(tzinfo=timezone.utc)
            return trial_end > now
        return False

    @property
    def is_trial_expired(self) -> bool:
        """Check if trial has expired."""
        if self.role != UserRole.TRIAL:
            return False
        if self.trial_ends_at:
            # Handle both timezone-aware and naive datetimes (SQLite vs PostgreSQL)
            now = datetime.now(timezone.utc)
            trial_end = self.trial_ends_at
            if trial_end.tzinfo is None:
                trial_end = trial_end.replace(tzinfo=timezone.utc)
            return trial_end <= now
        return True  # No trial_ends_at means expired

    @property
    def max_pcs(self) -> int:
        """Maximum number of PCs allowed for this user."""
        if self.role in [UserRole.ADMIN, UserRole.PREMIUM]:
            return 999  # Unlimited
        # TRIAL and OBS: up to 3 PCs
        return 3

    @property
    def can_use_steamslot(self) -> bool:
        """Check if user can access SteamSlot feature."""
        return self.role in [UserRole.ADMIN, UserRole.PREMIUM]

    @property
    def subscription_status(self) -> str:
        """Human-readable subscription status."""
        if self.role == UserRole.ADMIN:
            return "Администратор"
        if self.role == UserRole.PREMIUM:
            if self.premium_until:
                return f"Premium до {self.premium_until.strftime('%d.%m.%Y')}"
            return "Premium"
        if self.role == UserRole.OBS:
            if self.premium_until:
                return f"OBS до {self.premium_until.strftime('%d.%m.%Y')}"
            return "OBS"
        if self.role == UserRole.TRIAL:
            if self.is_trial_active:
                trial_end = self.trial_ends_at
                if trial_end.tzinfo is None:
                    trial_end = trial_end.replace(tzinfo=timezone.utc)
                days_left = (trial_end - datetime.now(timezone.utc)).days
                return f"Пробный ({days_left} дн.)"
            return "Пробный истёк"
        return "Неизвестно"

    def __repr__(self) -> str:
        return f"<User {self.email}>"


# Import at bottom to avoid circular imports
from app.models.pc import PC  # noqa: E402
from app.models.payment import Payment  # noqa: E402
