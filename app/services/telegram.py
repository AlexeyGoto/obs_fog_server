"""
Telegram notification service.
"""
import httpx

from app.core.config import settings


class TelegramService:
    """Service for sending Telegram notifications."""

    API_BASE = "https://api.telegram.org"

    def __init__(self, bot_token: str | None = None):
        self.bot_token = bot_token or settings.telegram_bot_token

    async def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: str = "HTML",
        reply_markup: dict | None = None,
    ) -> dict | None:
        """
        Send a text message to a Telegram chat.

        Args:
            chat_id: Target chat ID
            text: Message text
            parse_mode: Parse mode (HTML or Markdown)
            reply_markup: Optional inline keyboard

        Returns:
            Response data or None on error
        """
        if not self.bot_token:
            return None

        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }

        if reply_markup:
            payload["reply_markup"] = reply_markup

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.API_BASE}/bot{self.bot_token}/sendMessage",
                    json=payload,
                    timeout=10.0,
                )

                if response.status_code == 200:
                    data = response.json()
                    if data.get("ok"):
                        return data["result"]
            except httpx.RequestError:
                pass

        return None

    async def send_video(
        self,
        chat_id: int,
        video_path: str,
        caption: str | None = None,
    ) -> dict | None:
        """
        Send a video file to a Telegram chat.

        Args:
            chat_id: Target chat ID
            video_path: Path to video file
            caption: Optional caption

        Returns:
            Response data or None on error
        """
        if not self.bot_token:
            return None

        async with httpx.AsyncClient() as client:
            try:
                with open(video_path, "rb") as f:
                    files = {"video": f}
                    data = {"chat_id": chat_id}
                    if caption:
                        data["caption"] = caption

                    response = await client.post(
                        f"{self.API_BASE}/bot{self.bot_token}/sendVideo",
                        data=data,
                        files=files,
                        timeout=120.0,
                    )

                    if response.status_code == 200:
                        result = response.json()
                        if result.get("ok"):
                            return result["result"]
            except (httpx.RequestError, FileNotFoundError):
                pass

        return None

    async def send_approval_request(
        self,
        admin_chat_id: int,
        user_email: str,
        user_id: int,
    ) -> dict | None:
        """
        Send user approval request to admin with inline buttons.

        Args:
            admin_chat_id: Admin's Telegram chat ID
            user_email: User's email
            user_id: User's database ID

        Returns:
            Response data or None on error
        """
        text = (
            f"🆕 <b>New User Registration</b>\n\n"
            f"Email: <code>{user_email}</code>\n"
            f"User ID: {user_id}\n\n"
            f"Approve or deny this user?"
        )

        reply_markup = {
            "inline_keyboard": [
                [
                    {
                        "text": "✅ Approve",
                        "callback_data": f"approve_{user_id}",
                    },
                    {
                        "text": "⛔ Deny",
                        "callback_data": f"deny_{user_id}",
                    },
                ]
            ]
        }

        return await self.send_message(
            admin_chat_id,
            text,
            reply_markup=reply_markup,
        )

    async def notify_user_approved(self, chat_id: int) -> dict | None:
        """Notify user that their account was approved."""
        text = (
            "✅ <b>Account Approved!</b>\n\n"
            "Your account has been approved. You can now start streaming!\n\n"
            "Go to your dashboard to set up your PC."
        )
        return await self.send_message(chat_id, text)

    async def notify_user_denied(
        self,
        chat_id: int,
        reason: str | None = None,
    ) -> dict | None:
        """Notify user that their account was denied."""
        text = "⛔ <b>Account Denied</b>\n\n"
        if reason:
            text += f"Reason: {reason}"
        else:
            text += "Your account registration has been denied."
        return await self.send_message(chat_id, text)

    async def notify_stream_started(
        self,
        chat_id: int,
        pc_name: str,
    ) -> dict | None:
        """Notify user that their stream started."""
        text = f"🔴 <b>Stream Started</b>\n\nPC: {pc_name}"
        return await self.send_message(chat_id, text)

    async def notify_stream_ended(
        self,
        chat_id: int,
        pc_name: str,
        duration_minutes: int,
    ) -> dict | None:
        """Notify user that their stream ended."""
        text = (
            f"⏹ <b>Stream Ended</b>\n\n"
            f"PC: {pc_name}\n"
            f"Duration: {duration_minutes} minutes\n\n"
            f"Clip is being processed..."
        )
        return await self.send_message(chat_id, text)

    async def notify_premium_activated(
        self,
        chat_id: int,
        days: int,
    ) -> dict | None:
        """Notify user that premium was activated."""
        text = (
            f"⭐ <b>Premium Activated!</b>\n\n"
            f"Your premium subscription is now active for {days} days.\n\n"
            f"Enjoy all premium features!"
        )
        return await self.send_message(chat_id, text)

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: str | None = None,
        show_alert: bool = False,
    ) -> bool:
        """Answer a callback query (button press)."""
        if not self.bot_token:
            return False

        payload = {
            "callback_query_id": callback_query_id,
            "show_alert": show_alert,
        }
        if text:
            payload["text"] = text

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.API_BASE}/bot{self.bot_token}/answerCallbackQuery",
                    json=payload,
                    timeout=10.0,
                )
                return response.status_code == 200
            except httpx.RequestError:
                return False

    async def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        parse_mode: str = "HTML",
    ) -> dict | None:
        """Edit an existing message."""
        if not self.bot_token:
            return None

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.API_BASE}/bot{self.bot_token}/editMessageText",
                    json={
                        "chat_id": chat_id,
                        "message_id": message_id,
                        "text": text,
                        "parse_mode": parse_mode,
                    },
                    timeout=10.0,
                )

                if response.status_code == 200:
                    data = response.json()
                    if data.get("ok"):
                        return data["result"]
            except httpx.RequestError:
                pass

        return None
