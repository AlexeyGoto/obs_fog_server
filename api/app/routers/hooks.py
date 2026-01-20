from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Job, PC, StreamSession, User

router = APIRouter(prefix='/hook', tags=['hooks'])


def _get_form_value(body: bytes, key: str) -> str | None:
    """nginx-rtmp sends application/x-www-form-urlencoded by default."""
    try:
        text = body.decode('utf-8', errors='ignore')
    except Exception:
        return None
    parts = text.split('&')
    for p in parts:
        if not p:
            continue
        if '=' not in p:
            continue
        k, v = p.split('=', 1)
        if k == key:
            # plus is space in form encoding; we don't really need decode fully
            return v.replace('+', ' ')
    return None


@router.post('/on_publish', response_class=PlainTextResponse)
async def on_publish(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    # expected: name=live&...&key=<stream_key> and/or "name" is app? "name" can be stream name
    stream = _get_form_value(body, 'name') or _get_form_value(body, 'stream')
    # NGINX-RTMP uses "name" as stream name by default; here it's the stream key in URL rtmp://..../live/<name>
    stream_key = stream

    if not stream_key:
        raise HTTPException(status_code=400, detail='missing stream key')

    pc = db.query(PC).filter(PC.stream_key == stream_key).first()
    if not pc:
        # deny unknown keys
        raise HTTPException(status_code=403, detail='unknown stream key')

    # create new session (or reuse an active one)
    active = (
        db.query(StreamSession)
        .filter(StreamSession.pc_id == pc.id)
        .filter(StreamSession.ended_at.is_(None))
        .order_by(StreamSession.id.desc())
        .first()
    )
    if not active:
        active = StreamSession(pc_id=pc.id, status='recording')
        db.add(active)
        db.commit()

    return PlainTextResponse('OK')


@router.post('/on_publish_done', response_class=PlainTextResponse)
async def on_publish_done(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    stream = _get_form_value(body, 'name') or _get_form_value(body, 'stream')
    stream_key = stream

    if not stream_key:
        return PlainTextResponse('OK')

    pc = db.query(PC).filter(PC.stream_key == stream_key).first()
    if not pc:
        return PlainTextResponse('OK')

    # find active session
    sess = (
        db.query(StreamSession)
        .filter(StreamSession.pc_id == pc.id)
        .filter(StreamSession.ended_at.is_(None))
        .order_by(StreamSession.id.desc())
        .first()
    )
    if not sess:
        return PlainTextResponse('OK')

    sess.ended_at = datetime.utcnow()
    sess.status = 'queued'
    sess.message = 'Ожидает обработки (склейка + Telegram)'
    db.commit()

    # enqueue job
    payload = json.dumps({'session_id': sess.id})
    job = Job(type='process_session', status='pending', payload=payload)
    db.add(job)
    db.commit()

    return PlainTextResponse('OK')
