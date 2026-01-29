"""
OBS Fog Server - Telegram Bot Service

Handles:
- User account linking (/link command)
- Admin approval flow (inline buttons)
- Premium status notifications
- Stream notifications
"""
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models.user import ApprovalStatus, User

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("bot")

# Configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://obsfog:devpassword@localhost:5432/obsfog_dev",
)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ADMIN_ID = int(os.getenv("TELEGRAM_ADMIN_ID", "0"))
API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")
APPROVAL_REQUIRED = os.getenv("APPROVAL_REQUIRED", "false").lower() == "true"

# Database
engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    chat_id = update.effective_chat.id
    user = update.effective_user

    text = (
        f"👋 <b>Добро пожаловать в OBS Fog Server!</b>\n\n"
        f"Ваш Telegram ID: <code>{chat_id}</code>\n\n"
        f"<b>Команды:</b>\n"
        f"/link &lt;email&gt; - Привязать аккаунт\n"
        f"/status - Статус аккаунта\n"
        f"/help - Показать справку\n"
    )

    await update.message.reply_text(text, parse_mode="HTML")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    text = (
        "📚 <b>Справка OBS Fog Server</b>\n\n"
        "<b>Команды:</b>\n"
        "/start - Начать работу с ботом\n"
        "/link &lt;email&gt; - Привязать аккаунт\n"
        "/status - Проверить статус аккаунта\n"
        "/unlink - Отвязать Telegram\n\n"
        "<b>Как использовать:</b>\n"
        "1. Зарегистрируйтесь на сайте\n"
        "2. Используйте /link &lt;email&gt; для привязки\n"
        "3. Получайте уведомления о стримах здесь\n"
    )

    await update.message.reply_text(text, parse_mode="HTML")


async def cmd_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /link command to bind Telegram to account."""
    chat_id = update.effective_chat.id

    if not context.args:
        await update.message.reply_text(
            "❌ Использование: /link your-email@example.com",
            parse_mode="HTML",
        )
        return

    email = context.args[0].lower()

    async with async_session() as db:
        # Find user by email
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user:
            await update.message.reply_text(
                "❌ Аккаунт с таким email не найден.\n"
                "Сначала зарегистрируйтесь на сайте.",
                parse_mode="HTML",
            )
            return

        # Check if already linked to another account
        if user.tg_chat_id and user.tg_chat_id != chat_id:
            await update.message.reply_text(
                "⚠️ Этот email уже привязан к другому Telegram.",
                parse_mode="HTML",
            )
            return

        # Link account
        user.tg_chat_id = chat_id
        user.approval_requested_at = datetime.now(timezone.utc)

        # Handle approval
        if APPROVAL_REQUIRED and not user.is_approved:
            user.approval_status = ApprovalStatus.PENDING
            await db.commit()

            await update.message.reply_text(
                "✅ Аккаунт привязан!\n\n"
                "⏳ Ваш аккаунт ожидает одобрения администратора.\n"
                "Вы получите уведомление после одобрения.",
                parse_mode="HTML",
            )

            # Notify admin
            if TELEGRAM_ADMIN_ID:
                await send_approval_request(context.bot, user)
        else:
            if not user.is_approved:
                user.is_approved = True
                user.approval_status = ApprovalStatus.APPROVED

            await db.commit()

            await update.message.reply_text(
                "✅ Аккаунт успешно привязан!\n\n"
                "Теперь вы будете получать уведомления о стримах.",
                parse_mode="HTML",
            )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status command."""
    chat_id = update.effective_chat.id

    async with async_session() as db:
        result = await db.execute(select(User).where(User.tg_chat_id == chat_id))
        user = result.scalar_one_or_none()

        if not user:
            await update.message.reply_text(
                "❌ К этому Telegram не привязан аккаунт.\n"
                "Используйте /link &lt;email&gt; для привязки.",
                parse_mode="HTML",
            )
            return

        status_emoji = "✅" if user.is_approved else "⏳"
        status_text = "Одобрен" if user.is_approved else "Ожидает"
        premium_text = ""
        if user.is_premium:
            if user.premium_until:
                premium_text = f"\n⭐ Premium до: {user.premium_until.strftime('%d.%m.%Y')}"
            else:
                premium_text = "\n⭐ Premium: Активен"

        role_map = {"user": "Пользователь", "premium": "Premium", "admin": "Администратор"}
        role_text = role_map.get(user.role.value, user.role.value)

        text = (
            f"📊 <b>Статус аккаунта</b>\n\n"
            f"Email: <code>{user.email}</code>\n"
            f"Статус: {status_emoji} {status_text}\n"
            f"Тариф: {role_text}"
            f"{premium_text}"
        )

        await update.message.reply_text(text, parse_mode="HTML")


async def cmd_unlink(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /unlink command."""
    chat_id = update.effective_chat.id

    async with async_session() as db:
        result = await db.execute(select(User).where(User.tg_chat_id == chat_id))
        user = result.scalar_one_or_none()

        if not user:
            await update.message.reply_text(
                "❌ К этому Telegram не привязан аккаунт.",
                parse_mode="HTML",
            )
            return

        user.tg_chat_id = None
        await db.commit()

        await update.message.reply_text(
            "✅ Аккаунт отвязан. Вы больше не будете получать уведомления.",
            parse_mode="HTML",
        )


async def send_approval_request(bot, user: User) -> None:
    """Send approval request to admin."""
    if not TELEGRAM_ADMIN_ID:
        return

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{user.id}"),
            InlineKeyboardButton("⛔ Отклонить", callback_data=f"deny_{user.id}"),
        ]
    ])

    text = (
        f"🆕 <b>Новая регистрация</b>\n\n"
        f"Email: <code>{user.email}</code>\n"
        f"User ID: {user.id}\n"
        f"Telegram ID: {user.tg_chat_id}\n\n"
        f"Одобрить или отклонить?"
    )

    try:
        await bot.send_message(
            TELEGRAM_ADMIN_ID,
            text,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    except Exception as e:
        logger.error(f"Failed to send approval request: {e}")


async def callback_approval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle approval/denial button clicks."""
    query = update.callback_query
    admin_id = query.from_user.id

    # Verify admin
    if admin_id != TELEGRAM_ADMIN_ID:
        await query.answer("Нет доступа.", show_alert=True)
        return

    data = query.data
    action, user_id = data.split("_", 1)
    user_id = int(user_id)

    async with async_session() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            await query.answer("Пользователь не найден.", show_alert=True)
            return

        if action == "approve":
            user.is_approved = True
            user.approval_status = ApprovalStatus.APPROVED
            user.approval_decided_at = datetime.now(timezone.utc)
            user.approval_decided_by = admin_id
            await db.commit()

            await query.answer("Одобрено!")

            # Update message
            await query.edit_message_text(
                f"✅ <b>Одобрено</b>\n\n"
                f"Email: <code>{user.email}</code>\n"
                f"User ID: {user.id}",
                parse_mode="HTML",
            )

            # Notify user
            if user.tg_chat_id:
                try:
                    await context.bot.send_message(
                        user.tg_chat_id,
                        "✅ <b>Аккаунт одобрен!</b>\n\n"
                        "Ваш аккаунт одобрен. Можете начинать стримить!\n"
                        "Перейдите в панель управления для настройки ПК.",
                        parse_mode="HTML",
                    )
                except Exception as e:
                    logger.error(f"Failed to notify user: {e}")

        elif action == "deny":
            user.is_approved = False
            user.approval_status = ApprovalStatus.DENIED
            user.approval_decided_at = datetime.now(timezone.utc)
            user.approval_decided_by = admin_id
            await db.commit()

            await query.answer("Отклонено.")

            # Update message
            await query.edit_message_text(
                f"⛔ <b>Отклонено</b>\n\n"
                f"Email: <code>{user.email}</code>\n"
                f"User ID: {user.id}",
                parse_mode="HTML",
            )

            # Notify user
            if user.tg_chat_id:
                try:
                    await context.bot.send_message(
                        user.tg_chat_id,
                        "⛔ <b>Аккаунт отклонён</b>\n\n"
                        "Ваша регистрация была отклонена.",
                        parse_mode="HTML",
                    )
                except Exception as e:
                    logger.error(f"Failed to notify user: {e}")


async def check_pending_approvals(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Periodic job to check for pending approvals."""
    if not TELEGRAM_ADMIN_ID or not APPROVAL_REQUIRED:
        return

    async with async_session() as db:
        result = await db.execute(
            select(User)
            .where(User.approval_status == ApprovalStatus.PENDING)
            .where(User.tg_chat_id.isnot(None))
            .where(User.approval_notified_at.is_(None))
        )
        users = result.scalars().all()

        for user in users:
            await send_approval_request(context.bot, user)
            user.approval_notified_at = datetime.now(timezone.utc)

        if users:
            await db.commit()
            logger.info(f"Sent {len(users)} approval requests")


def main() -> None:
    """Start the bot."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set!")
        return

    logger.info("Starting bot...")
    logger.info(f"Admin ID: {TELEGRAM_ADMIN_ID}")
    logger.info(f"Approval required: {APPROVAL_REQUIRED}")

    # Create application
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Add handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("link", cmd_link))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("unlink", cmd_unlink))
    app.add_handler(CallbackQueryHandler(callback_approval, pattern=r"^(approve|deny)_"))

    # Add periodic job for checking pending approvals
    if APPROVAL_REQUIRED and TELEGRAM_ADMIN_ID:
        app.job_queue.run_repeating(check_pending_approvals, interval=60, first=10)

    # Run bot
    logger.info("Bot started, polling for updates...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
