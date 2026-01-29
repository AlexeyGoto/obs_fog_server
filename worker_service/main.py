"""
OBS Fog Server - Worker Service

Background worker that processes clip jobs:
1. Polls database for pending clip jobs
2. Converts HLS stream to MP4 using FFmpeg
3. Sends clips to users via Telegram
4. Cleans up old clips
"""
import asyncio
import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models.pc import ClipJob, ClipStatus, PC, StreamSession
from app.models.user import User

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("worker")

# Configuration from environment
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://obsfog:devpassword@localhost:5432/obsfog_dev",
)
HLS_BASE_URL = os.getenv("HLS_BASE_URL", "http://nginx:8080/hls")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_MAX_MB = int(os.getenv("TELEGRAM_MAX_MB", "50"))
CLIP_SECONDS = int(os.getenv("CLIP_SECONDS", "420"))
CLIP_RETENTION_HOURS = int(os.getenv("CLIP_RETENTION_HOURS", "72"))
AUTO_DELETE_AFTER_SEND = os.getenv("AUTO_DELETE_AFTER_SEND", "false").lower() == "true"
VIDEOS_DIR = Path(os.getenv("VIDEOS_DIR", "/data/videos"))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "10"))
CLEANUP_INTERVAL = int(os.getenv("CLEANUP_INTERVAL", "600"))  # 10 minutes

# Database setup
engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_pending_jobs(db: AsyncSession) -> list[ClipJob]:
    """Get pending clip jobs from database."""
    result = await db.execute(
        select(ClipJob)
        .options(
            selectinload(ClipJob.session)
            .selectinload(StreamSession.pc)
            .selectinload(PC.user)
        )
        .where(ClipJob.status == ClipStatus.PENDING)
        .order_by(ClipJob.created_at.asc())
        .limit(5)
    )
    return list(result.scalars().all())


async def process_clip(db: AsyncSession, job: ClipJob) -> None:
    """Process a single clip job."""
    session = job.session
    pc = session.pc
    user = pc.user
    stream_key = pc.stream_key

    logger.info(f"Processing job {job.id} for session {session.id}")

    # Update status to processing
    job.status = ClipStatus.PROCESSING
    await db.commit()

    # Prepare paths
    hls_url = f"{HLS_BASE_URL}/{stream_key}/index.m3u8"
    output_path = VIDEOS_DIR / f"clip_session_{session.id}.mp4"

    try:
        # Run FFmpeg to convert HLS to MP4
        cmd = [
            "ffmpeg",
            "-y",
            "-i", hls_url,
            "-t", str(CLIP_SECONDS),
            "-c", "copy",
            "-bsf:a", "aac_adtstoasc",
            str(output_path),
        ]

        logger.info(f"Running FFmpeg: {' '.join(cmd)}")

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise RuntimeError(f"FFmpeg failed: {stderr.decode()}")

        # Get file size
        file_size = output_path.stat().st_size
        logger.info(f"Clip created: {output_path} ({file_size} bytes)")

        # Update job
        job.result_path = str(output_path)
        job.size_bytes = file_size
        job.status = ClipStatus.STORED

        # Send to Telegram if user has linked account
        if user.tg_chat_id and TELEGRAM_BOT_TOKEN:
            size_mb = file_size / (1024 * 1024)

            if size_mb <= TELEGRAM_MAX_MB:
                success = await send_telegram_video(
                    user.tg_chat_id,
                    output_path,
                    f"📹 Clip from {pc.name}",
                )
                if success:
                    job.status = ClipStatus.SENT
                    if AUTO_DELETE_AFTER_SEND:
                        output_path.unlink(missing_ok=True)
                        job.result_path = None
            else:
                job.status = ClipStatus.TOO_BIG
                # Notify user that file is too big
                await send_telegram_message(
                    user.tg_chat_id,
                    f"📹 Clip from {pc.name} is ready but too large "
                    f"({size_mb:.1f}MB) for Telegram. "
                    f"Download from your dashboard.",
                )

        await db.commit()
        logger.info(f"Job {job.id} completed with status {job.status}")

    except Exception as e:
        logger.error(f"Job {job.id} failed: {e}")
        job.status = ClipStatus.FAILED
        job.error = str(e)
        await db.commit()


async def send_telegram_video(
    chat_id: int,
    video_path: Path,
    caption: str,
) -> bool:
    """Send video to Telegram."""
    if not TELEGRAM_BOT_TOKEN:
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            with open(video_path, "rb") as f:
                response = await client.post(
                    url,
                    data={"chat_id": chat_id, "caption": caption},
                    files={"video": f},
                )

            if response.status_code == 200:
                data = response.json()
                return data.get("ok", False)

    except Exception as e:
        logger.error(f"Failed to send Telegram video: {e}")

    return False


async def send_telegram_message(chat_id: int, text: str) -> bool:
    """Send text message to Telegram."""
    if not TELEGRAM_BOT_TOKEN:
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            )
            return response.status_code == 200

    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")

    return False


async def cleanup_old_clips() -> None:
    """Delete clips older than retention period."""
    if not VIDEOS_DIR.exists():
        return

    cutoff = datetime.now() - timedelta(hours=CLIP_RETENTION_HOURS)
    deleted = 0

    for clip_file in VIDEOS_DIR.glob("clip_*.mp4"):
        try:
            if datetime.fromtimestamp(clip_file.stat().st_mtime) < cutoff:
                clip_file.unlink()
                deleted += 1
        except Exception as e:
            logger.error(f"Failed to delete {clip_file}: {e}")

    if deleted:
        logger.info(f"Cleaned up {deleted} old clips")


async def main_loop() -> None:
    """Main worker loop."""
    logger.info("Worker started")
    logger.info(f"Database: {DATABASE_URL}")
    logger.info(f"HLS URL: {HLS_BASE_URL}")
    logger.info(f"Videos dir: {VIDEOS_DIR}")

    # Ensure videos directory exists
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)

    last_cleanup = datetime.now()

    while True:
        try:
            async with async_session() as db:
                jobs = await get_pending_jobs(db)

                for job in jobs:
                    await process_clip(db, job)

            # Periodic cleanup
            if (datetime.now() - last_cleanup).total_seconds() > CLEANUP_INTERVAL:
                await cleanup_old_clips()
                last_cleanup = datetime.now()

        except Exception as e:
            logger.error(f"Worker error: {e}")

        await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main_loop())
