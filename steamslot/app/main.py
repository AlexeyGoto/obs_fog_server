from __future__ import annotations

import datetime as dt
import hashlib
import secrets
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import FastAPI, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func, update, and_
from sqlalchemy.orm import Session

from .settings import Settings
from .db import make_engine, make_session_factory, Base
from .models import Account, PC, Lease
from .schemas import AcquireRequest, AcquireResponse, HeartbeatRequest, ReleaseRequest, SimpleOk
from .security import FernetBox, AdminSession, require_admin

settings = Settings.load()
app = FastAPI(title="Steam Slot Service", version="1.0.0", root_path=settings.root_path)

engine = make_engine(settings)
SessionLocal = make_session_factory(engine)

def print_admin_banner():
    # Не выводим пароль. Показываем пользователя и подсказку по дефолту.
    try:
        is_default = (settings.admin_user == 'admin' and settings.admin_pass == 'changeme')
    except Exception:
        is_default = False
    db_hint = settings.database_url.split('?')[0]
    print(f"[CFG] ADMIN_USER={settings.admin_user} (default_pass={'yes' if is_default else 'no'})")
    print(f"[CFG] DB={db_hint}")

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

fernet_box = FernetBox.from_env_key(settings.file_enc_key)

admin_session = AdminSession.from_env_key(settings.session_key, settings.session_ttl_seconds)
require_admin_dep = require_admin(settings, admin_session)


def db() -> Session:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@app.on_event("startup")
def _startup():
    Base.metadata.create_all(bind=engine)


@app.get("/healthz")
def healthz():
    return {"ok": True}


def _url(path: str) -> str:
    """
    Префиксует путь корневым префиксом приложения (root_path) для корректных redirect'ов за reverse proxy (/steamslot).
    """
    rp = (settings.root_path or "").rstrip("/")
    if not path.startswith("/"):
        path = "/" + path
    return f"{rp}{path}" if rp else path


@app.middleware("http")
async def _admin_cookie_middleware(request: Request, call_next):
    # Определяем админ-пользователя по cookie-сессии (или None)
    request.state.admin_user = admin_session.verify(request.cookies.get(settings.cookie_name, ""))

    # Редиректим на /login при заходе в админку без сессии
    p = request.url.path
    if p.startswith("/admin") and not request.state.admin_user:
        # Разрешаем страницу логина
        login_path = _url("/login")
        ext_next = _url(p)
        if request.url.query:
            ext_next = ext_next + "?" + request.url.query
        return RedirectResponse(url=f"{login_path}?next={quote(ext_next)}", status_code=303)

    return await call_next(request)


@app.get("/login", response_class=HTMLResponse, include_in_schema=False)
def login_form(request: Request, next: str | None = None):
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "title": "Вход", "next": next or _url("/admin"), "root_path": request.scope.get("root_path", "")},
    )


@app.post("/login", include_in_schema=False)
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form(default=""),
):
    username = username.strip()
    # Проверяем логин/пароль
    ok_user = secrets.compare_digest(username, settings.admin_user)
    ok_pass = secrets.compare_digest(password, settings.admin_pass)
    if not (ok_user and ok_pass):
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "title": "Вход",
                "error": "Неверный логин или пароль",
                "next": next or _url("/admin"),
                "root_path": request.scope.get("root_path", ""),
            },
            status_code=401,
        )

    token = admin_session.issue(username)
    resp = RedirectResponse(url=(next or _url("/admin")), status_code=303)
    resp.set_cookie(
        settings.cookie_name,
        token,
        httponly=True,
        samesite="lax",
        secure=bool(settings.cookie_secure),
        max_age=int(settings.session_ttl_seconds),
        path="/",
    )
    return resp


@app.get("/logout", include_in_schema=False)
def logout(request: Request):
    resp = RedirectResponse(url=_url("/login"), status_code=303)
    resp.delete_cookie(settings.cookie_name, path="/")
    return resp



def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def clamp_ttl(ttl: Optional[int]) -> int:
    if ttl is None:
        return settings.default_lease_ttl_seconds
    return max(30, min(int(ttl), settings.max_lease_ttl_seconds))


def cleanup_expired_leases(session: Session) -> int:
    now = utcnow()
    q = (
        update(Lease)
        .where(and_(Lease.released_at.is_(None), Lease.expires_at <= now))
        .values(released_at=now, status="expired", message="lease TTL expired")
    )
    res = session.execute(q)
    return int(res.rowcount or 0)


def require_pc(session: Session, pc_name: str, pc_key: str | None) -> PC:
    pc = session.execute(select(PC).where(PC.name == pc_name)).scalar_one_or_none()
    if pc is None or not pc.enabled:
        raise HTTPException(status_code=403, detail="Unknown or disabled PC")

    if settings.require_pc_key:
        if not pc_key:
            raise HTTPException(status_code=403, detail="Missing X-PC-KEY header")
        if not secrets.compare_digest(pc.api_key, pc_key):
            raise HTTPException(status_code=403, detail="Invalid PC key")

    return pc


def choose_account_for_pc(session: Session, pc: PC, requested_account_name: str | None) -> Account | None:
    now = utcnow()

    q = select(Account).where(Account.enabled.is_(True))

    if requested_account_name:
        q = q.where(Account.name == requested_account_name)

    if pc.account_id:
        q = q.where(Account.id == pc.account_id)

    active_cnt = (
        select(func.count(Lease.id))
        .where(
            and_(
                Lease.account_id == Account.id,
                Lease.released_at.is_(None),
                Lease.expires_at > now,
            )
        )
        .correlate(Account)
        .scalar_subquery()
    )

    q = q.where(active_cnt < Account.max_slots).order_by(Account.id.asc())

    if engine.dialect.name == "postgresql":
        q = q.with_for_update(skip_locked=True)

    return session.execute(q).scalar_one_or_none()


@app.post("/api/v1/lease/acquire", response_model=AcquireResponse)
def api_acquire(req: AcquireRequest, request: Request, session: Session = Depends(db)):
    pc_key = request.headers.get("X-PC-KEY")

    with session.begin():
        cleanup_expired_leases(session)
        pc = require_pc(session, req.pc_name, pc_key)
        ttl = clamp_ttl(req.ttl_seconds)
        now = utcnow()

        account = choose_account_for_pc(session, pc, req.account_name)
        if account is None:
            return AcquireResponse(ok=False, retry_after_seconds=30, message="No free slots right now")

        token = secrets.token_urlsafe(32)
        lease = Lease(
            pc_id=pc.id,
            account_id=account.id,
            token=token,
            created_at=now,
            expires_at=now + dt.timedelta(seconds=ttl),
            status="active",
        )
        session.add(lease)

    return AcquireResponse(ok=True, token=token, account_name=account.name, expires_at=lease.expires_at)


@app.post("/api/v1/lease/heartbeat", response_model=SimpleOk)
def api_heartbeat(req: HeartbeatRequest, request: Request, session: Session = Depends(db)):
    pc_key = request.headers.get("X-PC-KEY")

    with session.begin():
        cleanup_expired_leases(session)
        ttl = clamp_ttl(req.ttl_seconds)
        now = utcnow()

        lease = session.execute(select(Lease).where(Lease.token == req.token)).scalar_one_or_none()
        if lease is None:
            raise HTTPException(status_code=404, detail="Lease not found")

        pc = session.get(PC, lease.pc_id)
        if pc is None:
            raise HTTPException(status_code=404, detail="PC not found")

        if settings.require_pc_key:
            if not pc_key or not secrets.compare_digest(pc.api_key, pc_key):
                raise HTTPException(status_code=403, detail="Invalid PC key")

        if lease.released_at is not None or lease.expires_at <= now:
            raise HTTPException(status_code=409, detail="Lease is not active")

        lease.expires_at = now + dt.timedelta(seconds=ttl)
        lease.status = "active"

    return SimpleOk(ok=True)


@app.post("/api/v1/lease/release", response_model=SimpleOk)
def api_release(req: ReleaseRequest, request: Request, session: Session = Depends(db)):
    pc_key = request.headers.get("X-PC-KEY")

    with session.begin():
        cleanup_expired_leases(session)
        now = utcnow()

        lease = session.execute(select(Lease).where(Lease.token == req.token)).scalar_one_or_none()
        if lease is None:
            raise HTTPException(status_code=404, detail="Lease not found")

        pc = session.get(PC, lease.pc_id)
        if pc is None:
            raise HTTPException(status_code=404, detail="PC not found")

        if settings.require_pc_key:
            if not pc_key or not secrets.compare_digest(pc.api_key, pc_key):
                raise HTTPException(status_code=403, detail="Invalid PC key")

        if lease.released_at is not None:
            return SimpleOk(ok=True, message="Already released")

        lease.released_at = now
        lease.status = req.status or "released"
        lease.message = req.message

    return SimpleOk(ok=True)


@app.get("/api/v1/loginusers")
def api_download_loginusers(token: str, request: Request, session: Session = Depends(db)):
    pc_key = request.headers.get("X-PC-KEY")

    with session.begin():
        cleanup_expired_leases(session)
        now = utcnow()

        lease = session.execute(select(Lease).where(Lease.token == token)).scalar_one_or_none()
        if lease is None:
            raise HTTPException(status_code=404, detail="Lease not found")

        if lease.released_at is not None or lease.expires_at <= now:
            raise HTTPException(status_code=409, detail="Lease is not active")

        pc = session.get(PC, lease.pc_id)
        if pc is None:
            raise HTTPException(status_code=404, detail="PC not found")

        if settings.require_pc_key:
            if not pc_key or not secrets.compare_digest(pc.api_key, pc_key):
                raise HTTPException(status_code=403, detail="Invalid PC key")

        acc = session.get(Account, lease.account_id)
        if acc is None or not acc.enabled:
            raise HTTPException(status_code=404, detail="Account not found/disabled")

        if not acc.file_data:
            raise HTTPException(status_code=404, detail="loginusers file not uploaded for this account")

        data = acc.file_data
        if acc.file_encrypted:
            if not fernet_box:
                raise HTTPException(status_code=500, detail="Encrypted file but FILE_ENC_KEY not configured")
            data = fernet_box.decrypt(data)

        filename = acc.file_name or "loginusers.vdf"
        ctype = acc.file_content_type or "application/octet-stream"

    return StreamingResponse(
        iter([data]),
        media_type=ctype,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(_url("/admin"), status_code=303)


@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, _user=Depends(require_admin_dep), session: Session = Depends(db)):
    now = utcnow()
    with session.begin():
        cleanup_expired_leases(session)

        accounts_total = session.execute(select(func.count(Account.id))).scalar_one()
        accounts_enabled = session.execute(select(func.count(Account.id)).where(Account.enabled.is_(True))).scalar_one()
        pcs_total = session.execute(select(func.count(PC.id))).scalar_one()
        pcs_enabled = session.execute(select(func.count(PC.id)).where(PC.enabled.is_(True))).scalar_one()
        active_leases = session.execute(
            select(func.count(Lease.id)).where(and_(Lease.released_at.is_(None), Lease.expires_at > now))
        ).scalar_one()

        rows = session.execute(
            select(Lease, PC.name, Account.name)
            .join(PC, PC.id == Lease.pc_id)
            .join(Account, Account.id == Lease.account_id)
            .order_by(Lease.id.desc())
            .limit(30)
        ).all()

    leases_view = []
    for l, pc_name, acc_name in rows:
        leases_view.append(
            {
                "pc_name": pc_name,
                "account_name": acc_name,
                "created_at": l.created_at,
                "expires_at": l.expires_at,
                "released_at": l.released_at,
            }
        )

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "title": "Дашборд",
            "stats": {
                "accounts_total": accounts_total,
                "accounts_enabled": accounts_enabled,
                "pcs_total": pcs_total,
                "pcs_enabled": pcs_enabled,
                "active_leases": active_leases,
            },
            "leases": leases_view,
            "root_path": request.scope.get("root_path",""),
            "admin_user": getattr(request.state,"admin_user", None),
        },
    )


@app.get("/admin/accounts", response_class=HTMLResponse)
def admin_accounts(request: Request, _user=Depends(require_admin_dep), session: Session = Depends(db)):
    accounts = session.execute(select(Account).order_by(Account.id.asc())).scalars().all()
    return templates.TemplateResponse("accounts.html", {"request": request, "title": "Аккаунты", "accounts": accounts, "root_path": request.scope.get("root_path",""), "admin_user": getattr(request.state,"admin_user", None) })


@app.post("/admin/accounts")
def admin_accounts_create(
    name: str = Form(...),
    max_slots: int = Form(...),
    _user=Depends(require_admin_dep),
    session: Session = Depends(db),
):
    with session.begin():
        session.add(Account(name=name.strip(), max_slots=int(max_slots), enabled=True))
    return RedirectResponse(_url("/admin/accounts"), status_code=303)


@app.get("/admin/accounts/{account_id}", response_class=HTMLResponse)
def admin_account_detail(account_id: int, request: Request, _user=Depends(require_admin_dep), session: Session = Depends(db)):
    a = session.get(Account, account_id)
    if not a:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("account_detail.html", {"request": request, "title": f"Аккаунт {a.name}", "a": a, "root_path": request.scope.get("root_path",""), "admin_user": getattr(request.state,"admin_user", None) })


@app.post("/admin/accounts/{account_id}/update")
def admin_account_update(
    account_id: int,
    name: str = Form(...),
    max_slots: int = Form(...),
    enabled: str = Form(...),
    _user=Depends(require_admin_dep),
    session: Session = Depends(db),
):
    with session.begin():
        a = session.get(Account, account_id)
        if not a:
            raise HTTPException(status_code=404)
        a.name = name.strip()
        a.max_slots = int(max_slots)
        a.enabled = enabled == "1"
    return RedirectResponse(f"/admin/accounts/{account_id}", status_code=303)


@app.post("/admin/accounts/{account_id}/upload")
def admin_account_upload_file(
    account_id: int,
    encrypt: str = Form("1"),
    file: UploadFile = File(...),
    _user=Depends(require_admin_dep),
    session: Session = Depends(db),
):
    raw = file.file.read()
    sha = hashlib.sha256(raw).hexdigest()

    do_encrypt = (encrypt == "1") and (fernet_box is not None)
    stored = fernet_box.encrypt(raw) if do_encrypt else raw

    with session.begin():
        a = session.get(Account, account_id)
        if not a:
            raise HTTPException(status_code=404)
        a.file_name = file.filename or "loginusers.vdf"
        a.file_content_type = file.content_type or "application/octet-stream"
        a.file_data = stored
        a.file_sha256 = sha
        a.file_encrypted = bool(do_encrypt)
        a.file_updated_at = utcnow()

    return RedirectResponse(f"/admin/accounts/{account_id}", status_code=303)


@app.post("/admin/accounts/{account_id}/delete_file")
def admin_account_delete_file(
    account_id: int,
    _user=Depends(require_admin_dep),
    session: Session = Depends(db),
):
    with session.begin():
        a = session.get(Account, account_id)
        if not a:
            raise HTTPException(status_code=404)
        a.file_name = None
        a.file_content_type = None
        a.file_data = None
        a.file_sha256 = None
        a.file_encrypted = False
        a.file_updated_at = utcnow()
    return RedirectResponse(f"/admin/accounts/{account_id}", status_code=303)


@app.get("/admin/accounts/{account_id}/download")
def admin_account_download_file(
    account_id: int,
    _user=Depends(require_admin_dep),
    session: Session = Depends(db),
):
    a = session.get(Account, account_id)
    if not a or not a.file_data:
        raise HTTPException(status_code=404)

    data = a.file_data
    if a.file_encrypted:
        if not fernet_box:
            raise HTTPException(status_code=500, detail="Encrypted, but FILE_ENC_KEY not set")
        data = fernet_box.decrypt(data)

    filename = a.file_name or "loginusers.vdf"
    ctype = a.file_content_type or "application/octet-stream"

    return StreamingResponse(iter([data]), media_type=ctype, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/admin/pcs", response_class=HTMLResponse)
def admin_pcs(request: Request, _user=Depends(require_admin_dep), session: Session = Depends(db)):
    pcs = session.execute(select(PC).order_by(PC.id.asc())).scalars().all()
    accounts = session.execute(select(Account).order_by(Account.id.asc())).scalars().all()
    acc_map = {a.id: a.name for a in accounts}

    pcs_view = []
    for p in pcs:
        pcs_view.append(
            {
                "id": p.id,
                "name": p.name,
                "enabled": p.enabled,
                "account_name": acc_map.get(p.account_id),
                "api_key": p.api_key,
            }
        )

    return templates.TemplateResponse("pcs.html", {"request": request, "title": "ПК", "pcs": pcs_view, "accounts": accounts, "root_path": request.scope.get("root_path",""), "admin_user": getattr(request.state,"admin_user", None) })


@app.post("/admin/pcs")
def admin_pcs_create(
    name: str = Form(...),
    account_id: str = Form(""),
    api_key: str = Form(""),
    enabled: str = Form("1"),
    _user=Depends(require_admin_dep),
    session: Session = Depends(db),
):
    key = api_key.strip() or ("PC-" + secrets.token_urlsafe(18))
    acc_id = int(account_id) if account_id.strip() else None

    with session.begin():
        session.add(PC(name=name.strip(), enabled=(enabled == "1"), api_key=key, account_id=acc_id))

    return RedirectResponse(_url("/admin/pcs"), status_code=303)


@app.get("/admin/pcs/{pc_id}", response_class=HTMLResponse)
def admin_pc_detail(pc_id: int, request: Request, _user=Depends(require_admin_dep), session: Session = Depends(db)):
    p = session.get(PC, pc_id)
    if not p:
        raise HTTPException(status_code=404)
    accounts = session.execute(select(Account).order_by(Account.id.asc())).scalars().all()
    return templates.TemplateResponse("pc_detail.html", {"request": request, "title": f"ПК {p.name}", "p": p, "accounts": accounts, "root_path": request.scope.get("root_path",""), "admin_user": getattr(request.state,"admin_user", None) })


@app.post("/admin/pcs/{pc_id}/update")
def admin_pc_update(
    pc_id: int,
    name: str = Form(...),
    enabled: str = Form(...),
    api_key: str = Form(...),
    account_id: str = Form(""),
    notes: str = Form(""),
    _user=Depends(require_admin_dep),
    session: Session = Depends(db),
):
    acc_id = int(account_id) if account_id.strip() else None
    with session.begin():
        p = session.get(PC, pc_id)
        if not p:
            raise HTTPException(status_code=404)
        p.name = name.strip()
        p.enabled = enabled == "1"
        p.api_key = api_key.strip()
        p.account_id = acc_id
        p.notes = notes.strip() or None
    return RedirectResponse(f"/admin/pcs/{pc_id}", status_code=303)


@app.get("/admin/leases", response_class=HTMLResponse)
def admin_leases(request: Request, _user=Depends(require_admin_dep), session: Session = Depends(db)):
    with session.begin():
        cleanup_expired_leases(session)
        rows = session.execute(
            select(Lease, PC.name, Account.name)
            .join(PC, PC.id == Lease.pc_id)
            .join(Account, Account.id == Lease.account_id)
            .order_by(Lease.id.desc())
            .limit(100)
        ).all()

    leases = []
    for l, pc_name, acc_name in rows:
        leases.append(
            {
                "id": l.id,
                "pc_name": pc_name,
                "account_name": acc_name,
                "created_at": l.created_at,
                "expires_at": l.expires_at,
                "released_at": l.released_at,
                "status": l.status,
            }
        )

    return templates.TemplateResponse("leases.html", {"request": request, "title": "Слоты", "leases": leases, "root_path": request.scope.get("root_path",""), "admin_user": getattr(request.state,"admin_user", None) })


@app.post("/admin/leases/{lease_id}/revoke")
def admin_revoke_lease(lease_id: int, _user=Depends(require_admin_dep), session: Session = Depends(db)):
    with session.begin():
        l = session.get(Lease, lease_id)
        if not l:
            raise HTTPException(status_code=404)
        if l.released_at is None:
            l.released_at = utcnow()
            l.status = "revoked"
            l.message = "revoked by admin"
    return RedirectResponse(_url("/admin/leases"), status_code=303)
