from __future__ import annotations
import os, time
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from obs.app.settings import Settings
from obs.app.models import User, PC
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

settings = Settings.load()
engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Это OBS Fog Bot.\nКоманды:\n/link <email>\n/pcs\n/obs <pc_id>\n/live <pc_id>")

async def link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Использование: /link <email>")
        return
    email = context.args[0].strip().lower()
    chat_id = update.effective_chat.id
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.email==email))
        if not u:
            await update.message.reply_text("Не найден пользователь с таким email. Зарегистрируйся на сайте.")
            return
        u.tg_chat_id = int(chat_id)
        db.commit()
    await update.message.reply_text("✅ Telegram привязан. Теперь клипы будут приходить сюда.")

async def pcs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.tg_chat_id==int(chat_id)))
        if not u:
            await update.message.reply_text("Сначала привяжи аккаунт: /link <email>")
            return
        pcs = db.scalars(select(PC).where(PC.user_id==u.id).order_by(PC.id.asc())).all()
    if not pcs:
        await update.message.reply_text("ПК пока нет.")
        return
    lines = ["Ваши ПК:"]
    for pc in pcs:
        lines.append(f"- {pc.id}: {pc.name}")
    await update.message.reply_text("\n".join(lines))

async def obs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text("Использование: /obs <pc_id>")
        return
    pc_id = int(context.args[0])
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.tg_chat_id==int(chat_id)))
        if not u:
            await update.message.reply_text("Сначала привяжи аккаунт: /link <email>")
            return
        pc = db.get(PC, pc_id)
        if not pc or pc.user_id != u.id:
            await update.message.reply_text("ПК не найден.")
            return
    await update.message.reply_text(
        f"OBS настройки для {pc.name}:\nServer: rtmp://{settings.app_base_url.split('://')[1].split('/')[0].split(':')[0]}:1935/live\nKey: {pc.stream_key}"
    )

async def live(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text("Использование: /live <pc_id>")
        return
    pc_id = int(context.args[0])
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.tg_chat_id==int(chat_id)))
        if not u:
            await update.message.reply_text("Сначала привяжи аккаунт: /link <email>")
            return
        pc = db.get(PC, pc_id)
        if not pc or pc.user_id != u.id:
            await update.message.reply_text("ПК не найден.")
            return
    url = f"{settings.app_base_url}/pcs/{pc.id}"
    await update.message.reply_text(f"Открыть live: {url}")

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
    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
