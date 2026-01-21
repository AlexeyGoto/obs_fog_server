from __future__ import annotations
import os, time, subprocess, shlex
from pathlib import Path
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from obs.app.settings import Settings
from obs.app.models import ClipJob, StreamSession, PC, User

# We reuse obs models by copying package at build time (see worker/Dockerfile)
settings = Settings.load()

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

def run(cmd: list[str]) -> None:
    subprocess.check_call(cmd)

def ffmpeg_concat_hls_to_mp4(hls_url: str, out_path: Path) -> None:
    # Try copy (no re-encode). If fails, fallback to re-encode veryfast.
    cmd = ["ffmpeg","-y","-hide_banner","-loglevel","error","-i",hls_url,"-t",str(settings.clip_seconds),"-c","copy",str(out_path)]
    try:
        run(cmd)
        return
    except Exception:
        # fallback
        cmd2 = ["ffmpeg","-y","-hide_banner","-loglevel","error","-i",hls_url,"-t",str(settings.clip_seconds),"-c:v","libx264","-preset","veryfast","-c:a","aac",str(out_path)]
        run(cmd2)

def send_telegram(chat_id: int, text: str, file_path: Path | None = None) -> None:
    import requests
    token = settings.telegram_bot_token
    if not token or not chat_id:
        return
    base = f"https://api.telegram.org/bot{token}"
    if file_path is None:
        requests.post(f"{base}/sendMessage", data={"chat_id": chat_id, "text": text}, timeout=30)
        return
    with open(file_path,"rb") as f:
        requests.post(f"{base}/sendVideo", data={"chat_id": chat_id, "caption": text}, files={"video": f}, timeout=180)

def main():
    videos_dir = Path("/data/videos")
    videos_dir.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            with SessionLocal() as db:
                job = db.scalar(select(ClipJob).where(ClipJob.status=="pending").order_by(ClipJob.id.asc()))
                if not job:
                    time.sleep(2)
                    continue
                job.status="processing"
                db.commit()

                sess = db.get(StreamSession, job.session_id)
                pc = db.get(PC, sess.pc_id) if sess else None
                user = db.get(User, pc.user_id) if pc else None

                if not sess or not pc or not user or not user.tg_chat_id:
                    job.status="failed"
                    job.error="Missing session/pc/user or user not linked to Telegram"
                    db.commit()
                    continue

                hls_url = f"{settings.app_base_url}/hls/live/{pc.stream_key}/index.m3u8"
                out = videos_dir / f"clip_session_{sess.id}.mp4"
                try:
                    ffmpeg_concat_hls_to_mp4(hls_url, out)
                    size = out.stat().st_size if out.exists() else 0
                    job.size_bytes = size
                    job.result_path = str(out)

                    if size > settings.max_telegram_bytes:
                        send_telegram(user.tg_chat_id, f"❗️Клип для {pc.name} (session {sess.id}) слишком большой ({size/1024/1024:.1f} MB) и не может быть отправлен ботом.")
                        job.status="too_big"
                    else:
                        send_telegram(user.tg_chat_id, f"✅ Клип для {pc.name} (session {sess.id})", out)
                        job.status="sent"

                    db.commit()
                except Exception as e:
                    job.status="failed"
                    job.error=str(e)
                    db.commit()
                finally:
                    if settings.auto_delete:
                        try:
                            if out.exists():
                                out.unlink()
                        except Exception:
                            pass
        except Exception:
            time.sleep(3)

if __name__ == "__main__":
    main()
