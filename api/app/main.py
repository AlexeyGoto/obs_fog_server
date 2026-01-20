from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from starlette.staticfiles import StaticFiles

from .db import Base, engine
from .routers import web, hooks, bot_api

static_dir = Path(__file__).parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

def create_app() -> FastAPI:
    app = FastAPI(title='OBS Fog Service')

    Base.metadata.create_all(bind=engine)

    app.mount('/static', StaticFiles(directory='app/static'), name='static')

    app.include_router(web.router)
    app.include_router(hooks.router)
    app.include_router(bot_api.router)

    return app


app = create_app()
