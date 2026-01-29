"""
Payment router for Telegram Wallet USDT transactions.
"""
import logging

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.core.config import settings
from app.core.deps import CurrentUser, DbSession
from app.schemas.common import MessageResponse
from app.schemas.payment import (
    InvoiceCreate,
    InvoiceResponse,
    PaymentListResponse,
    PaymentResponse,
    TelegramUpdate,
)
from app.services.payment import PaymentService
from app.services.telegram import TelegramService

router = APIRouter(prefix="/payments", tags=["Payments"])
logger = logging.getLogger(__name__)


@router.post(
    "/create-invoice",
    response_model=InvoiceResponse,
    summary="Create payment invoice",
)
async def create_invoice(
    data: InvoiceCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> InvoiceResponse:
    """
    Create a Telegram Wallet invoice for premium subscription.

    Returns an invoice URL that can be opened in Telegram for payment.
    """
    if not settings.telegram_bot_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment system not configured",
        )

    if not settings.telegram_wallet_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment provider not configured",
        )

    payment_service = PaymentService(db)

    try:
        payment, invoice_url = await payment_service.create_invoice(
            user=current_user,
            description=data.description,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return InvoiceResponse(
        payment_id=payment.id,
        invoice_link=invoice_url,
        amount=payment.amount,
        currency=payment.currency,
    )


@router.get(
    "",
    response_model=PaymentListResponse,
    summary="List user payments",
)
async def list_payments(
    current_user: CurrentUser,
    db: DbSession,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
) -> PaymentListResponse:
    """Get current user's payment history."""
    payment_service = PaymentService(db)
    payments, total = await payment_service.get_user_payments(
        current_user.id,
        page=page,
        per_page=per_page,
    )

    return PaymentListResponse(
        items=[PaymentResponse.model_validate(p) for p in payments],
        total=total,
    )


@router.get(
    "/{payment_id}",
    response_model=PaymentResponse,
    summary="Get payment details",
)
async def get_payment(
    payment_id: int,
    current_user: CurrentUser,
    db: DbSession,
) -> PaymentResponse:
    """Get details of a specific payment."""
    payment_service = PaymentService(db)
    payment = await payment_service.get_payment_by_id(payment_id)

    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found",
        )

    if payment.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return PaymentResponse.model_validate(payment)


@router.post(
    "/webhook/telegram",
    response_model=MessageResponse,
    summary="Telegram payment webhook",
)
async def telegram_webhook(
    request: Request,
    db: DbSession,
) -> MessageResponse:
    """
    Handle Telegram payment webhooks.

    - pre_checkout_query: Validates payment before processing
    - successful_payment: Processes completed payment
    """
    try:
        body = await request.json()
        update = TelegramUpdate.model_validate(body)
    except Exception as e:
        logger.error(f"Failed to parse Telegram webhook: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request body",
        )

    payment_service = PaymentService(db)
    telegram = TelegramService()

    # Handle pre-checkout query (validation)
    if update.pre_checkout_query:
        query = update.pre_checkout_query
        logger.info(f"Pre-checkout query: {query.id}, payload={query.invoice_payload}")

        await payment_service.verify_pre_checkout(
            pre_checkout_query_id=query.id,
            invoice_payload=query.invoice_payload,
            total_amount=query.total_amount,
            currency=query.currency,
        )

        return MessageResponse(message="Pre-checkout processed")

    # Handle successful payment
    if update.message and update.message.successful_payment:
        payment_info = update.message.successful_payment
        logger.info(
            f"Successful payment: charge_id={payment_info.telegram_payment_charge_id}"
        )

        payment = await payment_service.process_successful_payment(
            invoice_payload=payment_info.invoice_payload,
            telegram_payment_charge_id=payment_info.telegram_payment_charge_id,
            provider_payment_charge_id=payment_info.provider_payment_charge_id,
            total_amount=payment_info.total_amount,
            currency=payment_info.currency,
        )

        if payment:
            # Notify user
            chat_id = update.message.chat.get("id")
            if chat_id:
                await telegram.notify_premium_activated(
                    chat_id,
                    settings.premium_duration_days,
                )

        return MessageResponse(message="Payment processed")

    return MessageResponse(message="OK")


@router.get(
    "/premium/status",
    summary="Check premium status",
)
async def premium_status(
    current_user: CurrentUser,
) -> dict:
    """Check current user's premium subscription status."""
    return {
        "is_premium": current_user.is_premium,
        "role": current_user.role.value,
        "premium_until": (
            current_user.premium_until.isoformat()
            if current_user.premium_until
            else None
        ),
        "price_usdt": settings.premium_price_usdt,
        "duration_days": settings.premium_duration_days,
    }
