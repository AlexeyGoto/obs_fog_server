from __future__ import annotations

import os
from pathlib import Path
from fastapi import FastAPI
from starlette.staticfiles import StaticFiles
from .web import router as web_router
from .api_hooks import router as hook_router
from .db import init_db

def create_app() -> FastAPI:
    app = FastAPI(title="OBS Fog Service", version="3.0.0")

    # Ensure static dir exists (avoid Starlette crash)
    static_dir = Path(__file__).parent / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    init_db()
    app.include_router(web_router)
    app.include_router(hook_router, prefix="/hook", tags=["hooks"])
    return app

app = create_app()
