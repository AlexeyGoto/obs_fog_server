from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from .settings import Settings

settings = Settings.load()
engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def _sqlite_has_column(conn, table: str, col: str) -> bool:
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    names = {r[1] for r in rows}  # (cid, name, type, notnull, dflt_value, pk)
    return col in names


def _ensure_schema() -> None:
    """Мягкая миграция без Alembic (для SQLite).

    В продакшне правильнее держать миграции, но для данного проекта делаем безопасное добавление колонок.
    """
    if engine.dialect.name != "sqlite":
        return

    with engine.begin() as conn:
        # users
        # Важно: SQLite позволяет ADD COLUMN только в конец таблицы.
        cols = [
            ("is_approved", "INTEGER NOT NULL DEFAULT 0"),
            ("approval_status", "TEXT NOT NULL DEFAULT 'pending'"),
            ("approval_token", "TEXT"),
            ("approval_requested_at", "DATETIME"),
            ("approval_notified_at", "DATETIME"),
            ("approval_decided_at", "DATETIME"),
            ("approval_decided_by", "TEXT"),
            ("approval_note", "TEXT"),
        ]
        for name, ddl in cols:
            if not _sqlite_has_column(conn, "users", name):
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {name} {ddl}"))
        # Обновим NULL на дефолт, если БД старая
        conn.execute(text("UPDATE users SET is_approved = COALESCE(is_approved, 0)"))
        conn.execute(text("UPDATE users SET approval_status = COALESCE(approval_status, 'pending')"))


def init_db() -> None:
    from . import models  # noqa

    Base.metadata.create_all(bind=engine)
    _ensure_schema()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
