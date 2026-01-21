from __future__ import annotations
import datetime as dt
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select
from .db import get_db
from .models import PC, StreamSession, ClipJob
from .settings import Settings

settings = Settings.load()
router = APIRouter()

def _extract_stream_key(request: Request) -> str | None:
    # nginx-rtmp sends form or query params; for simplicity we read query
    # Common vars: name, app, tcurl
    return (request.query_params.get("name") or request.query_params.get("stream") or "").strip() or None

@router.post("/on_publish")
async def on_publish(request: Request, db: Session = Depends(get_db)):
    key = _extract_stream_key(request)
    if not key:
        raise HTTPException(status_code=400, detail="missing stream key")
    pc = db.scalar(select(PC).where(PC.stream_key==key))
    if not pc or not pc.is_active:
        raise HTTPException(status_code=403, detail="invalid key")
    sess = StreamSession(pc_id=pc.id, status="live", started_at=dt.datetime.utcnow())
    db.add(sess); db.commit()
    return {"ok": True}

@router.post("/on_publish_done")
async def on_publish_done(request: Request, db: Session = Depends(get_db)):
    key = _extract_stream_key(request)
    if not key:
        raise HTTPException(status_code=400, detail="missing stream key")
    pc = db.scalar(select(PC).where(PC.stream_key==key))
    if not pc:
        raise HTTPException(status_code=404, detail="pc not found")
    sess = db.scalar(select(StreamSession).where(StreamSession.pc_id==pc.id).where(StreamSession.status=="live").order_by(StreamSession.id.desc()))
    if sess:
        sess.status="done"
        sess.ended_at=dt.datetime.utcnow()
        # create job
        job = ClipJob(session_id=sess.id, status="pending")
        db.add(job)
        db.commit()
    return {"ok": True}
