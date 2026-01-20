from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import requests
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, DateTime, Text, Boolean


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = 'jobs'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default='pending', index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    payload: Mapped[str] = mapped_column(Text)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class StreamSession(Base):
    __tablename__ = 'stream_sessions'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pc_id: Mapped[int] = mapped_column(Integer, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    clip_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    clip_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default='recording')
    message: Mapped[str | None] = mapped_column(Text, nullable=True)


class PC(Base):
    __tablename__ = 'pcs'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(120))
    stream_key: Mapped[str] = mapped_column(String(64), index=True)


class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    telegram_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    keep_clips: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_delete: Mapped[bool] = mapped_column(Boolean, default=True)
    max_telegram_mb: Mapped[int] = mapped_column(Integer, default=50)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    database_url: str = 'sqlite:////data/db/app.db'
    hls_base_url: str = 'http://nginx:8080/hls'

    telegram_bot_token: str = ''
    telegram_admin_id: str | None = None

    poll_seconds: int = 2
    job_lock_seconds: int = 300
    output_dir: str = '/data/videos'


S = Settings()


def _engine():
    connect_args = {}
    if S.database_url.startswith('sqlite'):
        connect_args = {'check_same_thread': False}
    return create_engine(S.database_url, pool_pre_ping=True, connect_args=connect_args)


def tg_call(method: str, payload: dict, files: dict | None = None) -> dict:
    if not S.telegram_bot_token:
        raise RuntimeError('TELEGRAM_BOT_TOKEN is not set')
    url = f"https://api.telegram.org/bot{S.telegram_bot_token}/{method}"
    r = requests.post(url, data=payload, files=files, timeout=120)
    try:
        return r.json()
    except Exception:
        return {'ok': False, 'status_code': r.status_code, 'text': r.text}


def tg_send_message(chat_id: str, text: str):
    tg_call('sendMessage', {'chat_id': chat_id, 'text': text})


def tg_send_video(chat_id: str, file_path: Path, caption: str):
    with file_path.open('rb') as f:
        tg_call('sendVideo', {'chat_id': chat_id, 'caption': caption}, files={'video': f})


def ffmpeg_clip(m3u8_url: str, out_mp4: Path) -> tuple[bool, str]:
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        'ffmpeg',
        '-y',
        '-hide_banner',
        '-loglevel', 'error',
        '-i', m3u8_url,
        '-c', 'copy',
        '-bsf:a', 'aac_adtstoasc',
        str(out_mp4),
    ]
    try:
        subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        return True, ''
    except subprocess.CalledProcessError as e:
        return False, (e.output or b'').decode('utf-8', errors='ignore')[-2000:]


def process_job(db: Session, job: Job):
    payload = json.loads(job.payload)
    session_id = int(payload['session_id'])

    sess = db.get(StreamSession, session_id)
    if not sess:
        job.status = 'done'
        job.last_error = 'session not found'
        db.commit()
        return

    pc = db.get(PC, sess.pc_id)
    if not pc:
        sess.status = 'failed'
        sess.message = 'PC не найден'
        job.status = 'done'
        job.last_error = 'pc not found'
        db.commit()
        return

    user = db.get(User, pc.user_id)
    if not user:
        sess.status = 'failed'
        sess.message = 'Пользователь не найден'
        job.status = 'done'
        job.last_error = 'user not found'
        db.commit()
        return

    if not user.keep_clips:
        sess.status = 'skipped'
        sess.message = 'Клип отключен настройками'
        job.status = 'done'
        db.commit()
        return

    m3u8_url = f"{S.hls_base_url}/live/{pc.stream_key}/index.m3u8"
    out_path = Path(S.output_dir) / f"session_{sess.id}_{pc.stream_key}.mp4"

    sess.status = 'processing'
    sess.message = f'Склеиваю HLS → MP4'
    db.commit()

    ok, err = ffmpeg_clip(m3u8_url, out_path)
    if not ok:
        sess.status = 'failed'
        sess.message = 'FFmpeg ошибка: не удалось собрать клип'
        job.status = 'done'
        job.last_error = err
        db.commit()
        if user.telegram_id:
            tg_send_message(user.telegram_id, f"{pc.name}: не удалось собрать клип (ffmpeg).")
        elif S.telegram_admin_id:
            tg_send_message(S.telegram_admin_id, f"{pc.name}: не удалось собрать клип (ffmpeg).")
        if out_path.exists() and user.auto_delete:
            try:
                out_path.unlink()
            except Exception:
                pass
        return

    size_bytes = out_path.stat().st_size if out_path.exists() else 0
    sess.clip_path = str(out_path)
    sess.clip_size_bytes = int(size_bytes)

    max_bytes = int(user.max_telegram_mb) * 1024 * 1024

    if not user.telegram_id:
        sess.status = 'ready'
        sess.message = 'Готово, но Telegram не привязан (/settings)'
        job.status = 'done'
        db.commit()
        if user.auto_delete:
            try:
                out_path.unlink()
            except Exception:
                pass
        return

    # Telegram limit logic: if too big -> notify only
    if size_bytes > max_bytes:
        sess.status = 'too_big'
        sess.message = f'Файл {size_bytes/1024/1024:.1f} МБ > лимита {user.max_telegram_mb} МБ. Отправка невозможна.'
        job.status = 'done'
        db.commit()
        tg_send_message(user.telegram_id, f"{pc.name}: клип слишком большой ({size_bytes/1024/1024:.1f} МБ), бот не может отправить. Настройте меньший битрейт/разрешение или сократите playlist_length.")
        if user.auto_delete:
            try:
                out_path.unlink()
            except Exception:
                pass
        return

    sess.status = 'sending'
    sess.message = 'Отправляю в Telegram'
    db.commit()

    caption = f"{pc.name} • последние ~7 минут"
    try:
        tg_send_video(user.telegram_id, out_path, caption)
        sess.status = 'sent'
        sess.message = 'Отправлено в Telegram'
        job.status = 'done'
        db.commit()
    except Exception as e:
        sess.status = 'failed'
        sess.message = 'Ошибка отправки в Telegram'
        job.status = 'done'
        job.last_error = repr(e)
        db.commit()
        try:
            tg_send_message(user.telegram_id, f"{pc.name}: ошибка отправки клипа в Telegram.")
        except Exception:
            pass
    finally:
        if user.auto_delete and out_path.exists():
            try:
                out_path.unlink()
            except Exception:
                pass


def main():
    engine = _engine()

    while True:
        time.sleep(S.poll_seconds)
        with Session(engine) as db:
            job = (
                db.query(Job)
                .filter(Job.status == 'pending')
                .filter(Job.type == 'process_session')
                .order_by(Job.id.asc())
                .first()
            )
            if not job:
                continue

            # lock
            job.status = 'processing'
            job.locked_at = datetime.utcnow()
            db.commit()

            try:
                process_job(db, job)
            except Exception as e:
                job.status = 'pending'
                job.last_error = repr(e)
                db.commit()


if __name__ == '__main__':
    main()
