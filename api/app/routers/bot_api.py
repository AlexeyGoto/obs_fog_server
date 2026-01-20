from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from urllib.parse import urlparse
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import PC, User
from ..settings import settings

router = APIRouter(prefix='/bot', tags=['bot'])


def _check_bot(request: Request):
    token = request.headers.get('X-Bot-Token') or ''
    if token != settings.bot_api_token:
        raise HTTPException(status_code=401, detail='bad bot token')


@router.post('/link')
async def link(request: Request, db: Session = Depends(get_db)):
    _check_bot(request)
    data = await request.json()
    code = (data.get('code') or '').strip()
    telegram_id = str(data.get('telegram_id') or '').strip()
    if not code or not telegram_id:
        raise HTTPException(status_code=400, detail='code and telegram_id required')

    user = db.query(User).filter(User.tg_link_code == code).first()
    if not user:
        raise HTTPException(status_code=404, detail='code not found')

    user.telegram_id = telegram_id
    # rotate code after successful link
    user.tg_link_code = None
    user.ensure_tg_link_code()
    db.commit()

    return {'ok': True, 'email': user.email}


@router.get('/pcs')
async def pcs(request: Request, telegram_id: str, db: Session = Depends(get_db)):
    _check_bot(request)
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user:
        raise HTTPException(status_code=404, detail='user not linked')

    pcs = db.query(PC).filter(PC.user_id == user.id).order_by(PC.id.desc()).all()
    return {'pcs': [{'id': p.id, 'name': p.name, 'stream_key': p.stream_key} for p in pcs]}


@router.get('/obs')
async def obs(request: Request, telegram_id: str, pc_id: int, db: Session = Depends(get_db)):
    _check_bot(request)
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user:
        raise HTTPException(status_code=404, detail='user not linked')

    pc = db.get(PC, pc_id)
    if not pc or pc.user_id != user.id:
        raise HTTPException(status_code=404, detail='pc not found')

    parsed = urlparse(settings.app_base_url)
    host = parsed.hostname or '127.0.0.1'

    return {
        'server': f'rtmp://{host}:1935/live',
        'key': pc.stream_key,
        'pc_name': pc.name,
        'pc_id': pc.id,
    }


@router.get('/live')
async def live(request: Request, telegram_id: str, pc_id: int, db: Session = Depends(get_db)):
    _check_bot(request)
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user:
        raise HTTPException(status_code=404, detail='user not linked')

    pc = db.get(PC, pc_id)
    if not pc or pc.user_id != user.id:
        raise HTTPException(status_code=404, detail='pc not found')

    return {
        'url': f'{settings.app_base_url}/pc/{pc.id}',
        'hls': f'{settings.app_base_url}/hls/live/{pc.stream_key}/index.m3u8',
        'pc_name': pc.name,
        'pc_id': pc.id,
    }
