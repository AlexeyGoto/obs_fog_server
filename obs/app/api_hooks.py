from __future__ import annotations

import datetime as dt
from urllib.parse import urlparse, parse_qs

from fastapi import APIRouter, Request, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from sqlalchemy import select

from .db import get_db
from .models import PC, StreamSession, User
from .settings import Settings

settings = Settings.load()
router = APIRouter()


def _first(*vals: str | None) -> str | None:
    for v in vals:
        if v is None:
            continue
        v = str(v).strip()
        if v != "":
            return v
    return None


async def _extract_stream_key(request: Request) -> str | None:
    q = request.query_params
    try:
        form = await request.form()
    except Exception:
        form = {}

    candidates = [
        _first(form.get("name"), q.get("name")),
        _first(form.get("key"), q.get("key")),
        _first(form.get("stream"), q.get("stream")),
    ]

    tcurl = _first(form.get("tcurl"), q.get("tcurl"))
    if tcurl:
        try:
            parsed = urlparse(tcurl)
            qs = parse_qs(parsed.query)
            candidates.append(_first(qs.get("name", [None])[0], qs.get("key", [None])[0], qs.get("stream", [None])[0]))
        except Exception:
            pass

    for c in candidates:
        if c:
            return c
    return None


def _utcnow() -> dt.datetime:
    return dt.datetime.utcnow()


@router.post("/on_publish")
async def on_publish(request: Request, db: Session = Depends(get_db)):
    key = await _extract_stream_key(request)
    if not key:
        return PlainTextResponse("missing stream key", status_code=403)

    pc = db.scalar(select(PC).where(PC.stream_key == key))
    if not pc:
        return PlainTextResponse("unknown stream key", status_code=403)

    if settings.approval_required:
        u = db.get(User, pc.user_id)
        if not u or not u.is_approved:
            return PlainTextResponse("user not approved", status_code=403)

    sess = StreamSession(pc_id=pc.id, started_at=_utcnow(), status="live")
    db.add(sess)
    db.commit()
    return PlainTextResponse("OK", status_code=200)


@router.post("/on_publish_done")
async def on_publish_done(request: Request, db: Session = Depends(get_db)):
    key = await _extract_stream_key(request)
    if not key:
        return PlainTextResponse("OK", status_code=200)

    pc = db.scalar(select(PC).where(PC.stream_key == key))
    if not pc:
        return PlainTextResponse("OK", status_code=200)

    sess = db.scalar(
        select(StreamSession)
        .where(StreamSession.pc_id == pc.id, StreamSession.ended_at.is_(None))
        .order_by(StreamSession.id.desc())
    )
    if sess:
        sess.ended_at = _utcnow()
        sess.status = "done"
        db.commit()

    return PlainTextResponse("OK", status_code=200)
