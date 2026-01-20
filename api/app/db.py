from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from .settings import settings


class Base(DeclarativeBase):
    pass


def create_engine_from_url(url: str):
    connect_args = {}
    if url.startswith('sqlite'):
        connect_args = {'check_same_thread': False}
    return create_engine(url, pool_pre_ping=True, connect_args=connect_args)


engine = create_engine_from_url(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
