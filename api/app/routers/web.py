from __future__ import annotations

import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..auth import COOKIE_NAME, create_token, hash_password, require_user, verify_password
from ..db import get_db
from ..models import PC, User
from ..settings import settings

router = APIRouter()
templates = Jinja2Templates(directory='app/templates')


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url=url, status_code=303)


@router.get('/', response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    user = None
    try:
        user = require_user(request, db)
    except HTTPException:
        return _redirect('/login')

    pcs = db.query(PC).filter(PC.user_id == user.id).order_by(PC.id.desc()).all()

    return templates.TemplateResponse(
        'dashboard.html',
        {
            'request': request,
            'user': user,
            'pcs': pcs,
            'rtmp_url': f'rtmp://{request.url.hostname}:1935/live',
            'app_base_url': settings.app_base_url,
        },
    )


@router.get('/register', response_class=HTMLResponse)
def register_get(request: Request):
    return templates.TemplateResponse('register.html', {'request': request, 'error': None})


@router.post('/register')
def register_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    email = email.strip().lower()
    if len(password) < 6:
        return templates.TemplateResponse('register.html', {'request': request, 'error': 'Пароль слишком короткий (мин. 6).'}, status_code=400)

    if db.query(User).filter(User.email == email).first():
        return templates.TemplateResponse('register.html', {'request': request, 'error': 'Email уже зарегистрирован.'}, status_code=400)

    user = User(email=email, password_hash=hash_password(password))
    user.ensure_tg_link_code()
    db.add(user)
    db.commit()

    resp = _redirect('/')
    resp.set_cookie(COOKIE_NAME, create_token(user.id), httponly=True, samesite='lax')
    return resp


@router.get('/login', response_class=HTMLResponse)
def login_get(request: Request):
    return templates.TemplateResponse('login.html', {'request': request, 'error': None})


@router.post('/login')
def login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    email = email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse('login.html', {'request': request, 'error': 'Неверный email или пароль.'}, status_code=400)

    resp = _redirect('/')
    resp.set_cookie(COOKIE_NAME, create_token(user.id), httponly=True, samesite='lax')
    return resp


@router.get('/logout')
def logout():
    resp = _redirect('/login')
    resp.delete_cookie(COOKIE_NAME)
    return resp


def _gen_stream_key() -> str:
    # 22 chars URL-safe, good entropy
    return secrets.token_urlsafe(16)


@router.get('/pc/new', response_class=HTMLResponse)
def pc_new_get(request: Request, user: User = Depends(require_user)):
    return templates.TemplateResponse('pc_new.html', {'request': request, 'user': user, 'error': None})


@router.post('/pc/new')
def pc_new_post(
    request: Request,
    name: str = Form(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    name = name.strip()
    if not name:
        return templates.TemplateResponse('pc_new.html', {'request': request, 'user': user, 'error': 'Название не может быть пустым.'}, status_code=400)

    stream_key = _gen_stream_key()
    # ensure uniqueness
    while db.query(PC).filter(PC.stream_key == stream_key).first():
        stream_key = _gen_stream_key()

    pc = PC(user_id=user.id, name=name, stream_key=stream_key)
    db.add(pc)
    db.commit()

    return _redirect(f'/pc/{pc.id}')


@router.get('/pc/{pc_id}', response_class=HTMLResponse)
def pc_detail(request: Request, pc_id: int, user: User = Depends(require_user), db: Session = Depends(get_db)):
    pc = db.get(PC, pc_id)
    if not pc or pc.user_id != user.id:
        raise HTTPException(status_code=404, detail='PC not found')

    # HLS nested path: /data/hls/live/<stream_key>/index.m3u8 => /hls/live/<stream_key>/index.m3u8
    hls_url = f"{settings.app_base_url}/hls/live/{pc.stream_key}/index.m3u8"
    rtmp_url = f"rtmp://{request.url.hostname}:1935/live"

    sessions = list(reversed(pc.sessions))

    return templates.TemplateResponse(
        'pc_detail.html',
        {
            'request': request,
            'user': user,
            'pc': pc,
            'rtmp_url': rtmp_url,
            'hls_url': hls_url,
            'sessions': sessions[:50],
        },
    )


@router.post('/pc/{pc_id}/regen')
def pc_regen_key(pc_id: int, user: User = Depends(require_user), db: Session = Depends(get_db)):
    pc = db.get(PC, pc_id)
    if not pc or pc.user_id != user.id:
        raise HTTPException(status_code=404, detail='PC not found')

    new_key = _gen_stream_key()
    while db.query(PC).filter(PC.stream_key == new_key).first():
        new_key = _gen_stream_key()

    pc.stream_key = new_key
    db.commit()
    return _redirect(f'/pc/{pc.id}')


@router.get('/settings', response_class=HTMLResponse)
def settings_get(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    # refresh from db
    user = db.get(User, user.id)
    assert user is not None
    code = user.ensure_tg_link_code()
    db.commit()

    return templates.TemplateResponse(
        'settings.html',
        {
            'request': request,
            'user': user,
            'link_code': code,
        },
    )


@router.post('/settings')
def settings_post(
    keep_clips: str = Form('off'),
    auto_delete: str = Form('off'),
    max_telegram_mb: int = Form(50),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    user_db = db.get(User, user.id)
    assert user_db is not None

    user_db.keep_clips = keep_clips == 'on'
    user_db.auto_delete = auto_delete == 'on'
    user_db.max_telegram_mb = max(1, min(int(max_telegram_mb), 2000))

    db.commit()
    return _redirect('/settings')
