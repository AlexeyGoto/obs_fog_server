from __future__ import annotations

import time
from typing import Any, Dict
from urllib.parse import urlparse

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .config import load_settings
from .db import (
    init_db,
    jobs_recent,
    job_create,
    live_streams,
    pc_by_stream_key,
    pc_create,
    pc_get,
    pc_list,
    setting_get,
    setting_set,
    settings_all,
    stream_set_live,
)

app = FastAPI(title="obs-rtmp-telegram")
templates = Jinja2Templates(directory="/app/app/templates")

CFG = load_settings()
init_db(CFG.database_path, CFG.default_save_videos, CFG.default_auto_delete, CFG.default_strict_keys)


def _now_human() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def _bool_from_str(val: str) -> bool:
    val = (val or "").strip().lower()
    return val in {"1", "true", "yes", "y", "on"}


def _settings_bools() -> Dict[str, bool]:
    raw = settings_all(CFG.database_path)
    return {
        "save_videos": _bool_from_str(raw.get("save_videos", "true")),
        "auto_delete": _bool_from_str(raw.get("auto_delete", "true")),
        "strict_keys": _bool_from_str(raw.get("strict_keys", "true")),
    }


def _rtmp_url(request: Request) -> str:
    # Prefer PUBLIC_BASE_URL, else derive from incoming host
    base = (CFG.public_base_url or "").strip()
    host = None
    if base:
        try:
            p = urlparse(base)
            host = p.hostname
        except Exception:
            host = None
    if not host:
        # request.url.hostname includes possible proxy host
        host = request.url.hostname
    if not host:
        host = "localhost"
    # Default RTMP port is 1935; usually omit
    return f"rtmp://{host}/live"


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    pcs = pc_list(CFG.database_path)
    jobs = jobs_recent(CFG.database_path, limit=30)
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "title": "Панель",
            "now_human": _now_human(),
            "pcs": pcs,
            "jobs": jobs,
            "settings": _settings_bools(),
        },
    )


@app.post("/pcs")
async def add_pc(name: str = Form(...)):
    pc_create(CFG.database_path, name)
    return RedirectResponse("/", status_code=303)


@app.get("/pc/{pc_id}", response_class=HTMLResponse)
async def pc_page(request: Request, pc_id: int):
    pc = pc_get(CFG.database_path, pc_id)
    if not pc:
        return PlainTextResponse("PC not found", status_code=404)

    hls_url = f"/hls/{pc['stream_key']}/index.m3u8"
    return templates.TemplateResponse(
        "pc.html",
        {
            "request": request,
            "title": f"ПК {pc_id}",
            "now_human": _now_human(),
            "pc": pc,
            "rtmp_url": _rtmp_url(request),
            "hls_url": hls_url,
        },
    )


@app.post("/settings")
async def update_settings(
    save_videos: str | None = Form(default=None),
    auto_delete: str | None = Form(default=None),
    strict_keys: str | None = Form(default=None),
):
    # checkboxes: present => on
    setting_set(CFG.database_path, "save_videos", "true" if save_videos is not None else "false")
    setting_set(CFG.database_path, "auto_delete", "true" if auto_delete is not None else "false")
    setting_set(CFG.database_path, "strict_keys", "true" if strict_keys is not None else "false")
    return RedirectResponse("/", status_code=303)


# -------- JSON API (for bot) --------

@app.get("/api/pcs")
async def api_pcs():
    return pc_list(CFG.database_path)


@app.get("/api/pc/{pc_id}")
async def api_pc(pc_id: int):
    pc = pc_get(CFG.database_path, pc_id)
    if not pc:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return pc


@app.get("/api/settings")
async def api_settings():
    return _settings_bools()


@app.post("/api/settings")
async def api_set_settings(payload: Dict[str, Any]):
    key = str(payload.get("key", "")).strip()
    value = str(payload.get("value", "")).strip().lower()
    if key not in {"save_videos", "auto_delete", "strict_keys"}:
        return JSONResponse({"error": "bad_key"}, status_code=400)
    if value not in {"true", "false"}:
        return JSONResponse({"error": "bad_value"}, status_code=400)
    setting_set(CFG.database_path, key, value)
    return {"ok": True, "key": key, "value": value}


@app.get("/api/live")
async def api_live():
    return {"live": live_streams(CFG.database_path)}


# -------- RTMP callbacks (nginx-rtmp) --------

@app.post("/hook/on_publish")
async def on_publish(request: Request):
    form = await request.form()
    stream_key = str(form.get("name") or "").strip()

    strict = _bool_from_str(setting_get(CFG.database_path, "strict_keys", "true"))
    if strict:
        pc = pc_by_stream_key(CFG.database_path, stream_key)
        if not pc:
            # Any non-2xx should reject publish
            return PlainTextResponse("forbidden", status_code=403)

    stream_set_live(CFG.database_path, stream_key, True)
    return PlainTextResponse("ok")


@app.post("/hook/on_publish_done")
async def on_publish_done(request: Request):
    form = await request.form()
    stream_key = str(form.get("name") or "").strip()

    stream_set_live(CFG.database_path, stream_key, False)

    save_videos = _bool_from_str(setting_get(CFG.database_path, "save_videos", "true"))
    if save_videos:
        job_create(CFG.database_path, stream_key, message="stream ended")

    return PlainTextResponse("ok")
