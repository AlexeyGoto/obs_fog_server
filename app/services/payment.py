"""
Payment service for Telegram Wallet USDT transactions.
"""
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.payment import Payment, PaymentStatus, PaymentType
from app.models.user import User
from app.services.user import UserService


class PaymentService:
    """Payment processing service for Telegram Wallet."""

    TELEGRAM_API_BASE = "https://api.telegram.org"

    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_service = UserService(db)

    async def create_invoice(
        self,
        user: User,
        amount: float | None = None,
        payment_type: PaymentType = PaymentType.PREMIUM,
        description: str | None = None,
    ) -> tuple[Payment, str]:
        """
        Create a payment invoice via Telegram Wallet.

        Args:
            user: User making the payment
            amount: Payment amount (defaults to premium_price_usdt)
            payment_type: Type of payment
            description: Optional description

        Returns:
            Tuple of (Payment record, invoice URL)
        """
        if not settings.telegram_bot_token:
            raise ValueError("Telegram bot token not configured")

        if not settings.telegram_wallet_token:
            raise ValueError("Telegram Wallet token not configured")

        if amount is None:
            amount = settings.premium_price_usdt

        # Generate unique payload for this payment
        payload = f"premium_{user.id}_{secrets.token_hex(8)}"

        if description is None:
            description = f"OBS Fog Server Premium - {settings.premium_duration_days} days"

        # Create payment record
        payment = Payment(
            user_id=user.id,
            amount=amount,
            currency="USDT",
            payment_type=payment_type,
            status=PaymentStatus.PENDING,
            invoice_payload=payload,
        )
        self.db.add(payment)
        await self.db.commit()
        await self.db.refresh(payment)

        # Create Telegram invoice link
        # Amount in smallest units (for USDT on TON, typically 6 decimals)
        total_amount = int(amount * 1_000_000)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.TELEGRAM_API_BASE}/bot{settings.telegram_bot_token}/createInvoiceLink",
                json={
                    "title": "Premium Subscription",
                    "description": description,
                    "payload": payload,
                    "provider_token": settings.telegram_wallet_token,
                    "currency": "USDT",
                    "prices": [
                        {
                            "label": f"Premium {settings.premium_duration_days} days",
                            "amount": total_amount,
                        }
                    ],
                },
            )

            if response.status_code != 200:
                payment.status = PaymentStatus.FAILED
                payment.error_message = f"Failed to create invoice: {response.text}"
                await self.db.commit()
                raise ValueError(f"Failed to create invoice: {response.text}")

            data = response.json()
            if not data.get("ok"):
                payment.status = PaymentStatus.FAILED
                payment.error_message = data.get("description", "Unknown error")
                await self.db.commit()
                raise ValueError(data.get("description", "Unknown error"))

            invoice_url = data["result"]

        return payment, invoice_url

    async def process_successful_payment(
        self,
        invoice_payload: str,
        telegram_payment_charge_id: str,
        provider_payment_charge_id: str,
        total_amount: int,
        currency: str,
    ) -> Payment | None:
        """
        Process a successful payment webhook from Telegram.

        Args:
            invoice_payload: Original payload from invoice
            telegram_payment_charge_id: Telegram's payment ID
            provider_payment_charge_id: Provider's payment ID
            total_amount: Amount in smallest units
            currency: Currency code

        Returns:
            Updated Payment or None if not found
        """
        # Find payment by payload
        result = await self.db.execute(
            select(Payment)
            .where(Payment.invoice_payload == invoice_payload)
            .where(Payment.status == PaymentStatus.PENDING)
        )
        payment = result.scalar_one_or_none()

        if not payment:
            return None

        # Verify amount matches (with some tolerance for rounding)
        expected_amount = int(payment.amount * 1_000_000)
        if abs(total_amount - expected_amount) > 1000:  # Allow small variance
            payment.status = PaymentStatus.FAILED
            payment.error_message = f"Amount mismatch: expected {expected_amount}, got {total_amount}"
            await self.db.commit()
            return payment

        # Update payment record
        payment.status = PaymentStatus.COMPLETED
        payment.telegram_payment_charge_id = telegram_payment_charge_id
        payment.provider_payment_charge_id = provider_payment_charge_id
        payment.completed_at = datetime.now(timezone.utc)

        # Grant premium to user
        if payment.payment_type == PaymentType.PREMIUM:
            user = await self.user_service.get_by_id(payment.user_id)
            if user:
                await self.user_service.grant_premium(
                    user, days=settings.premium_duration_days
                )

        await self.db.commit()
        await self.db.refresh(payment)

        return payment

    async def verify_pre_checkout(
        self,
        pre_checkout_query_id: str,
        invoice_payload: str,
        total_amount: int,
        currency: str,
    ) -> bool:
        """
        Verify pre-checkout query and answer it.

        Args:
            pre_checkout_query_id: Query ID from Telegram
            invoice_payload: Payload to verify
            total_amount: Amount to verify
            currency: Currency to verify

        Returns:
            True if approved, False otherwise
        """
        # Find pending payment
        result = await self.db.execute(
            select(Payment)
            .where(Payment.invoice_payload == invoice_payload)
            .where(Payment.status == PaymentStatus.PENDING)
        )
        payment = result.scalar_one_or_none()

        ok = True
        error_message = None

        if not payment:
            ok = False
            error_message = "Payment not found"
        elif currency != "USDT":
            ok = False
            error_message = "Invalid currency"

        # Answer pre-checkout query
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{self.TELEGRAM_API_BASE}/bot{settings.telegram_bot_token}/answerPreCheckoutQuery",
                json={
                    "pre_checkout_query_id": pre_checkout_query_id,
                    "ok": ok,
                    "error_message": error_message,
                },
            )

        return ok

    async def get_payment_by_id(self, payment_id: int) -> Payment | None:
        """Get payment by ID."""
        result = await self.db.execute(
            select(Payment).where(Payment.id == payment_id)
        )
        return result.scalar_one_or_none()

    async def get_user_payments(
        self,
        user_id: int,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[Payment], int]:
        """Get user's payment history."""
        query = select(Payment).where(Payment.user_id == user_id)

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_query)).scalar() or 0

        # Get paginated results
        offset = (page - 1) * per_page
        query = query.order_by(Payment.created_at.desc()).offset(offset).limit(per_page)
        result = await self.db.execute(query)

        return list(result.scalars().all()), total

    @staticmethod
    def verify_telegram_hash(data: dict, bot_token: str) -> bool:
        """
        Verify Telegram webhook data hash.

        Args:
            data: Data dict with 'hash' field
            bot_token: Bot token for verification

        Returns:
            True if hash is valid
        """
        received_hash = data.pop("hash", None)
        if not received_hash:
            return False

        # Sort and create data check string
        data_check_arr = [f"{k}={v}" for k, v in sorted(data.items())]
        data_check_string = "\n".join(data_check_arr)

        # Create secret key from bot token
        secret_key = hashlib.sha256(bot_token.encode()).digest()

        # Calculate expected hash
        expected_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(received_hash, expected_hash)
