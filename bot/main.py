\
from __future__ import annotations

import os
import time
import datetime as dt

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from obs.app.settings import Settings
from obs.app.models import User, PC

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler

settings = Settings.load()
engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def _utcnow() -> dt.datetime:
    return dt.datetime.utcnow()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Это OBS Fog Bot.\n\n"
        "Команды:\n"
        "/link <email> — привязать Telegram к аккаунту\n"
        "/pcs — список ваших ПК\n"
        "/obs <pc_id> — настройки OBS\n"
        "/live <pc_id> — ссылка на страницу live"
    )


async def link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Использование: /link <email>")
        return
    email = context.args[0].strip().lower()
    chat_id = update.effective_chat.id
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.email == email))
        if not u:
            await update.message.reply_text("Не найден пользователь с таким email. Зарегистрируйся на сайте.")
            return
        u.tg_chat_id = int(chat_id)
        db.commit()
        status = "✅ Telegram привязан."
        if settings.approval_required and not u.is_approved:
            status += " Аккаунт ожидает одобрения администратором."
    await update.message.reply_text(status)


async def pcs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.tg_chat_id == int(chat_id)))
        if not u:
            await update.message.reply_text("Сначала привяжи аккаунт: /link <email>")
            return
        pcs_list = db.scalars(select(PC).where(PC.user_id == u.id).order_by(PC.id.asc())).all()
    if not pcs_list:
        await update.message.reply_text("ПК пока нет.")
        return
    lines = ["Ваши ПК:"]
    for pc in pcs_list:
        lines.append(f"- {pc.id}: {pc.name}")
    await update.message.reply_text("\n".join(lines))


async def obs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text("Использование: /obs <pc_id>")
        return
    pc_id = int(context.args[0])
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.tg_chat_id == int(chat_id)))
        if not u:
            await update.message.reply_text("Сначала привяжи аккаунт: /link <email>")
            return
        if settings.approval_required and not u.is_approved:
            await update.message.reply_text("Аккаунт ещё не одобрен администратором.")
            return
        pc = db.get(PC, pc_id)
        if not pc or pc.user_id != u.id:
            await update.message.reply_text("ПК не найден.")
            return

    host = settings.app_base_url.split("://", 1)[-1].split("/", 1)[0]
    host = host.split(":", 1)[0]  # без порта web
    await update.message.reply_text(
        f"OBS настройки для {pc.name}:\n"
        f"Server: rtmp://{host}:1935/live\n"
        f"Key: {pc.stream_key}"
    )


async def live(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text("Использование: /live <pc_id>")
        return
    pc_id = int(context.args[0])
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.tg_chat_id == int(chat_id)))
        if not u:
            await update.message.reply_text("Сначала привяжи аккаунт: /link <email>")
            return
        if settings.approval_required and not u.is_approved:
            await update.message.reply_text("Аккаунт ещё не одобрен администратором.")
            return
        pc = db.get(PC, pc_id)
        if not pc or pc.user_id != u.id:
            await update.message.reply_text("ПК не найден.")
            return
    url = f"{settings.app_base_url}/pcs/{pc.id}"
    await update.message.reply_text(f"Открыть live: {url}")


async def _approval_job(context: ContextTypes.DEFAULT_TYPE):
    if not settings.approval_required:
        return
    admin_id = settings.telegram_admin_id
    if not admin_id:
        return

    with SessionLocal() as db:
        pending_users = db.scalars(
            select(User)
            .where(User.approval_status == "pending")
            .where(User.approval_notified_at.is_(None))
            .order_by(User.id.asc())
            .limit(10)
        ).all()

        for u in pending_users:
            if not u.approval_token:
                u.approval_token = os.urandom(16).hex()
                u.approval_requested_at = _utcnow()

            kb = InlineKeyboardMarkup(
                [[
                    InlineKeyboardButton("✅ Одобрить", callback_data=f"approve:{u.approval_token}"),
                    InlineKeyboardButton("⛔ Отклонить", callback_data=f"deny:{u.approval_token}"),
                ]]
            )
            text = (
                "Новая регистрация требует одобрения:\n"
                f"Email: {u.email}\n"
                f"UserID: {u.id}\n"
                f"Создан: {u.created_at}\n"
                f"TG привязан: {'да' if u.tg_chat_id else 'нет'}"
            )
            try:
                await context.bot.send_message(chat_id=int(admin_id), text=text, reply_markup=kb)
                u.approval_notified_at = _utcnow()
                db.commit()
            except Exception as e:
                db.rollback()
                print("Approval notify error:", e)
                break


async def _approval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    if ":" not in data:
        return
    action, token = data.split(":", 1)
    action = action.strip()
    token = token.strip()
    if action not in {"approve", "deny"} or not token:
        return

    admin_id = settings.telegram_admin_id
    if admin_id and update.effective_chat and int(update.effective_chat.id) != int(admin_id):
        await q.edit_message_text("Недостаточно прав.")
        return

    now = _utcnow()
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.approval_token == token))
        if not u:
            await q.edit_message_text("Заявка не найдена (возможно, уже обработана).")
            return

        if action == "approve":
            u.is_approved = True
            u.approval_status = "approved"
            u.approval_decided_at = now
            u.approval_decided_by = f"tg:{update.effective_user.id if update.effective_user else 'admin'}"
            db.commit()
            await q.edit_message_text(f"✅ Одобрено: {u.email} (id={u.id})")
            if u.tg_chat_id:
                try:
                    await context.bot.send_message(chat_id=int(u.tg_chat_id), text="✅ Ваш аккаунт одобрен. Можете пользоваться сервисом.")
                except Exception:
                    pass
        else:
            u.is_approved = False
            u.approval_status = "denied"
            u.approval_decided_at = now
            u.approval_decided_by = f"tg:{update.effective_user.id if update.effective_user else 'admin'}"
            db.commit()
            await q.edit_message_text(f"⛔ Отклонено: {u.email} (id={u.id})")
            if u.tg_chat_id:
                try:
                    await context.bot.send_message(chat_id=int(u.tg_chat_id), text="⛔ Регистрация отклонена администратором.")
                except Exception:
                    pass


def main():
    token = settings.telegram_bot_token
    if not token:
        print("TELEGRAM_BOT_TOKEN is empty; bot disabled.")
        while True:
            time.sleep(60)

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("link", link))
    app.add_handler(CommandHandler("pcs", pcs))
    app.add_handler(CommandHandler("obs", obs))
    app.add_handler(CommandHandler("live", live))

    app.add_handler(CallbackQueryHandler(_approval_callback))

    app.job_queue.run_repeating(_approval_job, interval=10, first=5)

    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
