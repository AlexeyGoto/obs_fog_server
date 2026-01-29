"""
Payment and Telegram Wallet schemas.
"""
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.payment import PaymentStatus, PaymentType


class PaymentCreate(BaseModel):
    """Schema for creating a payment."""

    amount: float = Field(..., gt=0, description="Payment amount")
    currency: str = Field(default="USDT", description="Payment currency")
    payment_type: PaymentType = Field(
        default=PaymentType.PREMIUM, description="Payment type"
    )


class PaymentResponse(BaseModel):
    """Payment response schema."""

    id: int
    user_id: int
    amount: float
    currency: str
    payment_type: PaymentType
    status: PaymentStatus
    telegram_payment_charge_id: str | None
    completed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PaymentListResponse(BaseModel):
    """List of payments."""

    items: list[PaymentResponse]
    total: int


# Telegram Wallet Invoice


class InvoiceCreate(BaseModel):
    """Request to create Telegram Wallet invoice."""

    description: str | None = Field(
        None, max_length=255, description="Payment description"
    )


class InvoiceResponse(BaseModel):
    """Telegram Wallet invoice response."""

    payment_id: int
    invoice_link: str
    amount: float
    currency: str
    expires_at: datetime | None = None


# Telegram Webhook Schemas


class TelegramPreCheckoutQuery(BaseModel):
    """Telegram pre-checkout query (for validation)."""

    id: str
    from_user: dict = Field(..., alias="from")
    currency: str
    total_amount: int
    invoice_payload: str

    model_config = {"populate_by_name": True}


class TelegramSuccessfulPayment(BaseModel):
    """Telegram successful payment notification."""

    currency: str
    total_amount: int
    invoice_payload: str
    telegram_payment_charge_id: str
    provider_payment_charge_id: str


class TelegramMessage(BaseModel):
    """Telegram message with payment info."""

    message_id: int
    from_user: dict = Field(..., alias="from")
    chat: dict
    date: int
    successful_payment: TelegramSuccessfulPayment | None = None

    model_config = {"populate_by_name": True}


class TelegramUpdate(BaseModel):
    """Telegram webhook update."""

    update_id: int
    message: TelegramMessage | None = None
    pre_checkout_query: TelegramPreCheckoutQuery | None = None
