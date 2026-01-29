"""
Payment model for Telegram Wallet USDT transactions.
"""
import enum
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class PaymentStatus(str, enum.Enum):
    """Payment transaction status."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentType(str, enum.Enum):
    """Payment type/purpose."""

    PREMIUM = "premium"
    DONATION = "donation"


class Payment(BaseModel):
    """
    Payment transaction record.

    Tracks Telegram Wallet USDT payments for premium subscriptions.
    """

    __tablename__ = "payments"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # Payment details
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="USDT", nullable=False)
    payment_type: Mapped[PaymentType] = mapped_column(
        Enum(PaymentType), default=PaymentType.PREMIUM, nullable=False
    )
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus), default=PaymentStatus.PENDING, nullable=False, index=True
    )

    # Telegram payment info
    telegram_payment_charge_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True, index=True
    )
    provider_payment_charge_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    invoice_payload: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Timestamps
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Error tracking
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="payments")

    def __repr__(self) -> str:
        return f"<Payment {self.id} {self.amount} {self.currency} status={self.status}>"


# Import at bottom to avoid circular imports
from app.models.user import User  # noqa: E402, F401
