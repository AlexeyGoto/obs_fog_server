from __future__ import annotations

import secrets
import datetime as dt
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import select
from .db import get_db
from .models import User, PC, StreamSession
from .security import hash_password, verify_password, create_token, get_current_user_id, new_stream_key, COOKIE_NAME
from .settings import Settings
from starlette.templating import Jinja2Templates

settings = Settings.load()
templates = Jinja2Templates(directory="app/templates")
router = APIRouter()


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


def _utcnow() -> dt.datetime:
    return dt.datetime.utcnow()


def _get_user_or_login(request: Request, db: Session) -> User | None:
    try:
        uid = get_current_user_id(request)
    except Exception:
        return None
    return db.get(User, uid)


def _require_approved(user: User) -> bool:
    return (not settings.approval_required) or bool(user.is_approved)


@router.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    user = _get_user_or_login(request, db)
    if not user:
        return _redirect("/login")
    if not _require_approved(user):
        return _redirect("/pending")

    pcs = db.scalars(select(PC).where(PC.user_id == user.id).order_by(PC.id.desc())).all()
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user, "pcs": pcs, "app": "obs"})


@router.get("/pending", response_class=HTMLResponse)
def pending(request: Request, db: Session = Depends(get_db)):
    user = _get_user_or_login(request, db)
    if not user:
        return _redirect("/login")
    return templates.TemplateResponse(
        "pending.html",
        {
            "request": request,
            "user": user,
            "approval_required": settings.approval_required,
            "admin_hint": "Администратор должен одобрить регистрацию в Telegram.",
            "app": "obs",
        },
    )


@router.get("/register", response_class=HTMLResponse)
def register_form(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "app": "obs"})


@router.post("/register")
def register(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    email = email.strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        return templates.TemplateResponse("register.html", {"request": request, "error": "Email уже зарегистрирован", "app": "obs"})

    u = User(
        email=email,
        password_hash=hash_password(password),
        is_approved=(not settings.approval_required),
        approval_status=("approved" if (not settings.approval_required) else "pending"),
        approval_token=(secrets.token_urlsafe(24)[:32] if settings.approval_required else None),
        approval_requested_at=(_utcnow() if settings.approval_required else None),
    )
    db.add(u)
    db.commit()
    db.refresh(u)

    token = create_token(u.id)
    resp = _redirect("/pending" if settings.approval_required else "/")
    resp.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax")
    return resp


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "app": "obs"})


@router.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    email = email.strip().lower()
    u = db.scalar(select(User).where(User.email == email))
    if not u or not verify_password(password, u.password_hash):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Неверные учётные данные", "app": "obs"})

    token = create_token(u.id)
    resp = _redirect("/pending" if (settings.approval_required and not u.is_approved) else "/")
    resp.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax")
    return resp


@router.post("/logout")
def logout():
    resp = _redirect("/login")
    resp.delete_cookie(COOKIE_NAME)
    return resp


@router.get("/pcs/new", response_class=HTMLResponse)
def pc_new(request: Request, db: Session = Depends(get_db)):
    user = _get_user_or_login(request, db)
    if not user:
        return _redirect("/login")
    if not _require_approved(user):
        return _redirect("/pending")
    return templates.TemplateResponse("pc_new.html", {"request": request, "app": "obs"})


@router.post("/pcs/new")
def pc_create(request: Request, name: str = Form(...), db: Session = Depends(get_db)):
    user = _get_user_or_login(request, db)
    if not user:
        return _redirect("/login")
    if not _require_approved(user):
        return _redirect("/pending")

    pc = PC(user_id=user.id, name=name.strip(), stream_key=new_stream_key())
    db.add(pc)
    db.commit()
    db.refresh(pc)
    return _redirect(f"/pcs/{pc.id}")


@router.get("/pcs/{pc_id}", response_class=HTMLResponse)
def pc_detail(pc_id: int, request: Request, db: Session = Depends(get_db)):
    user = _get_user_or_login(request, db)
    if not user:
        return _redirect("/login")
    if not _require_approved(user):
        return _redirect("/pending")

    pc = db.get(PC, pc_id)
    if not pc or pc.user_id != user.id:
        return _redirect("/")

    hls_url = f"{settings.app_base_url}/hls/live/{pc.stream_key}/index.m3u8"
    sessions = db.scalars(
        select(StreamSession).where(StreamSession.pc_id == pc.id).order_by(StreamSession.id.desc()).limit(20)
    ).all()
    return templates.TemplateResponse(
        "pc_detail.html",
        {"request": request, "pc": pc, "hls_url": hls_url, "sessions": sessions, "app": "obs"},
    )
