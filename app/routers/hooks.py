"""
RTMP hooks router for nginx-rtmp module callbacks.
"""
import logging
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import PlainTextResponse

from app.core.deps import DbSession
from app.models.pc import SessionStatus
from app.services.stream import StreamService
from app.services.telegram import TelegramService

router = APIRouter(prefix="/hook", tags=["RTMP Hooks"])
logger = logging.getLogger(__name__)


def extract_stream_key(
    name: str | None,
    key: str | None,
    tcurl: str | None,
) -> str | None:
    """
    Extract stream key from various sources.

    nginx-rtmp sends the key in different ways depending on client:
    - name: direct stream name
    - key: query parameter
    - tcurl: full URL with query string
    """
    # Try direct name first
    if name and len(name) > 10:
        return name

    # Try key parameter
    if key:
        return key

    # Try parsing tcurl
    if tcurl:
        try:
            parsed = urlparse(tcurl)
            params = parse_qs(parsed.query)
            if "key" in params:
                return params["key"][0]
            # Sometimes key is in path
            path_parts = parsed.path.strip("/").split("/")
            if len(path_parts) > 1:
                return path_parts[-1]
        except Exception:
            pass

    return name


@router.post(
    "/on_publish",
    response_class=PlainTextResponse,
    summary="RTMP on_publish hook",
)
async def on_publish(
    request: Request,
    db: DbSession,
    name: str | None = Form(None),
    key: str | None = Form(None),
    addr: str | None = Form(None),
    app: str | None = Form(None),
    tcurl: str | None = Form(None),
) -> PlainTextResponse:
    """
    Called by nginx-rtmp when a stream starts publishing.

    Validates the stream key and creates a new session.
    Returns 200 to allow stream, 403 to reject.
    """
    stream_key = extract_stream_key(name, key, tcurl)

    logger.info(f"on_publish: key={stream_key}, addr={addr}, app={app}")

    if not stream_key:
        logger.warning("on_publish: No stream key provided")
        return PlainTextResponse("No stream key", status_code=403)

    stream_service = StreamService(db)
    pc = await stream_service.get_pc_by_stream_key(stream_key)

    if not pc:
        logger.warning(f"on_publish: Invalid stream key: {stream_key[:8]}...")
        return PlainTextResponse("Invalid stream key", status_code=403)

    if not pc.is_active:
        logger.warning(f"on_publish: PC {pc.id} is disabled")
        return PlainTextResponse("PC is disabled", status_code=403)

    # Check user approval
    if not pc.user.is_approved:
        logger.warning(f"on_publish: User {pc.user_id} not approved")
        return PlainTextResponse("User not approved", status_code=403)

    if not pc.user.is_active:
        logger.warning(f"on_publish: User {pc.user_id} is disabled")
        return PlainTextResponse("User disabled", status_code=403)

    # Check trial expiration
    if pc.user.is_trial_expired:
        logger.warning(f"on_publish: User {pc.user_id} trial expired")
        return PlainTextResponse("Trial expired", status_code=403)

    # Check for existing live session
    existing = await stream_service.get_active_session(pc.id)
    if existing:
        logger.warning(f"on_publish: PC {pc.id} already has live session {existing.id}")
        # End the existing session
        await stream_service.end_session(existing, SessionStatus.ERROR, "Replaced by new stream")

    # Create new session
    session = await stream_service.start_session(pc)
    logger.info(f"on_publish: Created session {session.id} for PC {pc.id}")

    # Notify user via Telegram
    if pc.user.tg_chat_id:
        telegram = TelegramService()
        await telegram.notify_stream_started(pc.user.tg_chat_id, pc.name)

    return PlainTextResponse("OK", status_code=200)


@router.post(
    "/on_publish_done",
    response_class=PlainTextResponse,
    summary="RTMP on_publish_done hook",
)
async def on_publish_done(
    request: Request,
    db: DbSession,
    name: str | None = Form(None),
    key: str | None = Form(None),
    addr: str | None = Form(None),
    app: str | None = Form(None),
) -> PlainTextResponse:
    """
    Called by nginx-rtmp when a stream stops publishing.

    Ends the session and creates a clip job.
    """
    stream_key = extract_stream_key(name, key, None)

    logger.info(f"on_publish_done: key={stream_key}, addr={addr}")

    if not stream_key:
        return PlainTextResponse("OK", status_code=200)

    stream_service = StreamService(db)
    pc = await stream_service.get_pc_by_stream_key(stream_key)

    if not pc:
        return PlainTextResponse("OK", status_code=200)

    # Find active session
    session = await stream_service.get_active_session(pc.id)
    if not session:
        logger.warning(f"on_publish_done: No active session for PC {pc.id}")
        return PlainTextResponse("OK", status_code=200)

    # End session
    session = await stream_service.end_session(session, SessionStatus.DONE)
    logger.info(f"on_publish_done: Ended session {session.id}")

    # Create clip job
    clip_job = await stream_service.create_clip_job(session)
    logger.info(f"on_publish_done: Created clip job {clip_job.id}")

    # Notify user
    if pc.user.tg_chat_id:
        telegram = TelegramService()
        duration_minutes = 0
        if session.ended_at and session.started_at:
            duration_seconds = (session.ended_at - session.started_at).total_seconds()
            duration_minutes = int(duration_seconds / 60)
        await telegram.notify_stream_ended(
            pc.user.tg_chat_id,
            pc.name,
            duration_minutes,
        )

    return PlainTextResponse("OK", status_code=200)


@router.get(
    "/on_play",
    response_class=PlainTextResponse,
    summary="RTMP on_play hook",
)
async def on_play(
    addr: str | None = None,
    name: str | None = None,
) -> PlainTextResponse:
    """
    Called by nginx-rtmp when a viewer connects.
    Currently allows all viewers.
    """
    logger.info(f"on_play: addr={addr}, name={name}")
    return PlainTextResponse("OK", status_code=200)
