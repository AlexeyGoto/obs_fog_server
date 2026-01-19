from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import tempfile
import time
from contextlib import contextmanager
from typing import Dict, List, Optional, Tuple

import requests

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except Exception:  # pragma: no cover
    psycopg2 = None  # type: ignore
    RealDictCursor = None  # type: ignore


DATABASE_PATH = os.getenv("DATABASE_PATH", "/data/db/app.db")

# Postgres (optional): either DATABASE_URL or POSTGRESQL_* split variables
DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip()
POSTGRESQL_HOST = (os.getenv("POSTGRESQL_HOST") or "").strip()
POSTGRESQL_PORT = (os.getenv("POSTGRESQL_PORT") or "5432").strip()
POSTGRESQL_USER = (os.getenv("POSTGRESQL_USER") or "").strip()
POSTGRESQL_PASSWORD = (os.getenv("POSTGRESQL_PASSWORD") or "").strip()
POSTGRESQL_DBNAME = (os.getenv("POSTGRESQL_DBNAME") or "").strip()

if DATABASE_URL:
    DB_REF = DATABASE_URL
elif POSTGRESQL_HOST and POSTGRESQL_USER and POSTGRESQL_DBNAME:
    DB_REF = f"host={POSTGRESQL_HOST} port={POSTGRESQL_PORT} dbname={POSTGRESQL_DBNAME} user={POSTGRESQL_USER} password={POSTGRESQL_PASSWORD}"
else:
    DB_REF = DATABASE_PATH
DATA_DIR = os.getenv("DATA_DIR", "/data")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ADMIN_ID = os.getenv("TELEGRAM_ADMIN_ID", "").strip()

TELEGRAM_LIMIT_BYTES = 50 * 1024 * 1024
POLL_SECONDS = float(os.getenv("WORKER_POLL_SECONDS", "2"))


def _now_ts() -> int:
    return int(time.time())


def _is_postgres(db_ref: str) -> bool:
    ref = (db_ref or "").strip().lower()
    if not ref:
        return False
    if ref.startswith("postgres://") or ref.startswith("postgresql://"):
        return True
    if "host=" in ref and "dbname=" in ref:
        return True
    return False


def _sqlite_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def _pg_conn():
    if psycopg2 is None:
        raise RuntimeError("psycopg2 is not installed")
    conn = psycopg2.connect(DB_REF)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _ensure_schema() -> None:
    # api normally creates schema; worker does this as a safety net
    if not _is_postgres(DB_REF):
        return
    with _pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS pcs (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    stream_key TEXT NOT NULL UNIQUE,
                    created_at BIGINT NOT NULL
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS streams (
                    stream_key TEXT PRIMARY KEY,
                    is_live BOOLEAN NOT NULL,
                    last_publish_at BIGINT,
                    last_unpublish_at BIGINT
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id SERIAL PRIMARY KEY,
                    stream_key TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at BIGINT NOT NULL,
                    updated_at BIGINT NOT NULL,
                    message TEXT,
                    output_path TEXT
                );
                """
            )


def _setting_bool(key: str, default: bool) -> bool:
    try:
        if _is_postgres(DB_REF):
            with _pg_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT value FROM settings WHERE key=%s", (key,))
                    row = cur.fetchone()
                    if not row:
                        return default
                    val = str(row["value"]).strip().lower()
                    return val in {"1", "true", "yes", "y", "on"}

        conn = _sqlite_conn()
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        conn.close()
        if not row:
            return default
        val = str(row["value"]).strip().lower()
        return val in {"1", "true", "yes", "y", "on"}
    except Exception:
        return default


def _claim_next_job() -> Optional[Dict]:
    if _is_postgres(DB_REF):
        with _pg_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    WITH cte AS (
                        SELECT id FROM jobs
                        WHERE status='queued'
                        ORDER BY id ASC
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    )
                    UPDATE jobs
                    SET status='running', updated_at=%s
                    FROM cte
                    WHERE jobs.id = cte.id
                    RETURNING jobs.*
                    """,
                    (_now_ts(),),
                )
                row = cur.fetchone()
                return dict(row) if row else None

    conn = _sqlite_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY id ASC LIMIT 1").fetchone()
        if not row:
            conn.execute("COMMIT")
            return None
        job_id = int(row["id"])
        cur = conn.execute(
            "UPDATE jobs SET status='running', updated_at=? WHERE id=? AND status='queued'",
            (_now_ts(), job_id),
        )
        conn.execute("COMMIT")
        if cur.rowcount != 1:
            return None
        row2 = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row2) if row2 else None
    finally:
        conn.close()


def _job_update(job_id: int, status: str, message: str = "", output_path: Optional[str] = None) -> None:
    if _is_postgres(DB_REF):
        with _pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE jobs SET status=%s, updated_at=%s, message=%s, output_path=%s WHERE id=%s",
                    (status, _now_ts(), message, output_path, job_id),
                )
        return

    conn = _sqlite_conn()
    try:
        conn.execute(
            "UPDATE jobs SET status=?, updated_at=?, message=?, output_path=? WHERE id=?",
            (status, _now_ts(), message, output_path, job_id),
        )
        conn.commit()
    finally:
        conn.close()


def _tg_send_message(text: str) -> None:
    if not BOT_TOKEN or not ADMIN_ID:
        print("[WARN] TELEGRAM_BOT_TOKEN/TELEGRAM_ADMIN_ID not set; skip sendMessage")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": ADMIN_ID, "text": text},
            timeout=20,
        )
    except Exception as e:
        print(f"[WARN] sendMessage failed: {e}")


def _tg_send_video(path: str, caption: str) -> bool:
    if not BOT_TOKEN or not ADMIN_ID:
        print("[WARN] TELEGRAM_BOT_TOKEN/TELEGRAM_ADMIN_ID not set; skip sendVideo")
        return False
    try:
        with open(path, "rb") as f:
            resp = requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo",
                data={"chat_id": ADMIN_ID, "caption": caption},
                files={"video": f},
                timeout=120,
            )
        try:
            js = resp.json()
        except Exception:
            js = {}
        ok = bool(js.get("ok"))
        if not ok:
            print(f"[WARN] sendVideo not ok: status={resp.status_code} body={resp.text[:400]}")
        return ok
    except Exception as e:
        print(f"[WARN] sendVideo failed: {e}")
        return False


def _wait_file_settle(path: str, tries: int = 20, sleep_s: float = 0.5) -> None:
    last = -1
    for _ in range(tries):
        if not os.path.exists(path):
            time.sleep(sleep_s)
            continue
        sz = os.path.getsize(path)
        if sz > 0 and sz == last:
            return
        last = sz
        time.sleep(sleep_s)


def _parse_m3u8_segments(m3u8_path: str) -> List[str]:
    segs: List[str] = []
    base_dir = os.path.dirname(m3u8_path)
    with open(m3u8_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # typically something like 123.ts or stream-000001.ts
            seg_path = line
            if not os.path.isabs(seg_path):
                seg_path = os.path.join(base_dir, seg_path)
            segs.append(seg_path)
    return segs


def _build_mp4_from_hls(stream_key: str) -> Tuple[str, int]:
    hls_dir = os.path.join(DATA_DIR, "hls", stream_key)
    m3u8_path = os.path.join(hls_dir, "index.m3u8")

    # wait playlist
    for _ in range(60):
        if os.path.exists(m3u8_path):
            break
        time.sleep(0.5)
    if not os.path.exists(m3u8_path):
        raise RuntimeError("HLS playlist not found")

    # settle last segment
    segs = _parse_m3u8_segments(m3u8_path)
    if not segs:
        raise RuntimeError("No HLS segments")
    _wait_file_settle(segs[-1], tries=30, sleep_s=0.4)

    # stage to ordered list
    stage_dir = tempfile.mkdtemp(prefix=f"stage_{stream_key}_")
    try:
        list_path = os.path.join(stage_dir, "concat_list.txt")
        with open(list_path, "w", encoding="utf-8") as lf:
            idx = 0
            for seg in segs:
                if not os.path.exists(seg):
                    continue
                if os.path.getsize(seg) <= 0:
                    continue
                idx += 1
                target = os.path.join(stage_dir, f"{idx:06d}.ts")
                try:
                    os.link(seg, target)
                except Exception:
                    shutil.copy2(seg, target)
                lf.write(f"file '{target}'\n")

        if os.path.getsize(list_path) <= 0:
            raise RuntimeError("No valid segments to concat")

        os.makedirs(os.path.join(DATA_DIR, "out"), exist_ok=True)
        out_path = os.path.join(DATA_DIR, "out", f"{stream_key}_{time.strftime('%Y%m%d_%H%M%S')}.mp4")

        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostats",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            list_path,
            "-c",
            "copy",
            "-bsf:a",
            "aac_adtstoasc",
            "-movflags",
            "+faststart",
            out_path,
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg concat failed: {proc.stdout[-800:]}")
        if not os.path.exists(out_path) or os.path.getsize(out_path) <= 0:
            raise RuntimeError("Output mp4 not created")
        size = os.path.getsize(out_path)
        return out_path, size
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)


def _cleanup_stream_folder(stream_key: str) -> None:
    hls_dir = os.path.join(DATA_DIR, "hls", stream_key)
    shutil.rmtree(hls_dir, ignore_errors=True)


def _format_size(n: int) -> str:
    mb = n / (1024 * 1024)
    return f"{mb:.2f} MB"


def handle_job(job: Dict) -> None:
    job_id = int(job["id"])
    stream_key = str(job["stream_key"])
    print(f"[JOB {job_id}] stream_key={stream_key} start")

    auto_delete = _setting_bool("auto_delete", True)

    try:
        out_path, size = _build_mp4_from_hls(stream_key)
        caption = f"ПК stream_key: {stream_key}\nПоследние 7 минут (если был поток)"

        if size > TELEGRAM_LIMIT_BYTES:
            msg = (
                f"ПК: {stream_key}\n"
                f"Запись собрана, но размер {_format_size(size)} > 50 MB. "
                "Telegram Bot API не позволяет отправить такой файл. Видео не отправлено."
            )
            _tg_send_message(msg)
            _job_update(job_id, "failed", message=f"too_large ({size} bytes)", output_path=out_path)
            if auto_delete:
                try:
                    os.remove(out_path)
                except Exception:
                    pass
            _cleanup_stream_folder(stream_key)
            print(f"[JOB {job_id}] too large; notified")
            return

        ok = _tg_send_video(out_path, caption)
        if ok:
            _job_update(job_id, "done", message=f"sent ({size} bytes)", output_path=out_path)
            print(f"[JOB {job_id}] sent ok")
        else:
            _tg_send_message(f"ПК: {stream_key}\nНе удалось отправить видео в Telegram (ошибка Bot API).")
            _job_update(job_id, "failed", message="send_failed", output_path=out_path)

        if auto_delete:
            try:
                os.remove(out_path)
            except Exception:
                pass
        _cleanup_stream_folder(stream_key)

    except Exception as e:
        _tg_send_message(f"ПК: {stream_key}\nОшибка сборки/отправки видео: {e}")
        _job_update(job_id, "failed", message=str(e)[:500], output_path=None)
        # Если сборка не удалась, всё равно чистим сегменты, чтобы не жрать диск
        _cleanup_stream_folder(stream_key)
        print(f"[JOB {job_id}] failed: {e}")


def main() -> None:
    _ensure_schema()
    print(f"Worker started (db={'postgres' if _is_postgres(DB_REF) else 'sqlite'})")
    while True:
        job = _claim_next_job()
        if not job:
            time.sleep(POLL_SECONDS)
            continue
        handle_job(job)


if __name__ == "__main__":
    main()
