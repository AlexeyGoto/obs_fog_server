from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ADMIN_ID = os.getenv("TELEGRAM_ADMIN_ID", "").strip()
API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000").rstrip("/")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8080").rstrip("/")

POLL_TIMEOUT = 30


def _admin_ok(user_id: int) -> bool:
    try:
        return int(ADMIN_ID) == int(user_id)
    except Exception:
        return False


def _tg(method: str, data: Dict[str, Any], files: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    r = requests.post(url, data=data, files=files, timeout=60)
    try:
        return r.json()
    except Exception:
        return {"ok": False, "description": r.text}


def send_message(chat_id: int, text: str) -> None:
    _tg("sendMessage", {"chat_id": chat_id, "text": text})


def api_get(path: str) -> Any:
    r = requests.get(f"{API_BASE_URL}{path}", timeout=20)
    r.raise_for_status()
    return r.json()


def api_post_json(path: str, payload: Dict[str, Any]) -> Any:
    r = requests.post(f"{API_BASE_URL}{path}", json=payload, timeout=20)
    r.raise_for_status()
    return r.json()


def _rtmp_url() -> str:
    # derive host from PUBLIC_BASE_URL
    try:
        p = urlparse(PUBLIC_BASE_URL)
        host = p.hostname or "localhost"
    except Exception:
        host = "localhost"
    return f"rtmp://{host}/live"


def _help_text() -> str:
    return (
        "Команды:\n"
        "/pcs — список ПК\n"
        "/pc <id> — настройки OBS для ПК + ссылка\n"
        "/streams — кто сейчас LIVE\n"
        "\nАдмин (только TELEGRAM_ADMIN_ID):\n"
        "/savevideos on|off\n"
        "/autodelete on|off\n"
        "/strictkeys on|off\n"
    )


def handle_command(chat_id: int, user_id: int, text: str) -> None:
    parts = text.strip().split()
    cmd = parts[0].split("@")[0].lower()
    args = parts[1:]

    if cmd in {"/start", "/help"}:
        send_message(chat_id, _help_text())
        return

    if cmd == "/pcs":
        pcs = api_get("/api/pcs")
        if not pcs:
            send_message(chat_id, "Пока нет ни одного ПК. Добавь в панели: " + PUBLIC_BASE_URL)
            return
        lines = ["ПК:"]
        for pc in pcs:
            status = "LIVE" if pc.get("is_live") else "OFF"
            lines.append(f"#{pc['id']} {pc['name']} — {status}")
        lines.append("\nПанель: " + PUBLIC_BASE_URL)
        send_message(chat_id, "\n".join(lines))
        return

    if cmd == "/streams":
        pcs = api_get("/api/pcs")
        live = [pc for pc in pcs if pc.get("is_live")]
        if not live:
            send_message(chat_id, "Сейчас никто не стримит (LIVE пуст).")
            return
        lines = ["LIVE сейчас:"]
        for pc in live:
            watch = f"{PUBLIC_BASE_URL}/pc/{pc['id']}"
            lines.append(f"#{pc['id']} {pc['name']} — {watch}")
        send_message(chat_id, "\n".join(lines))
        return

    if cmd == "/pc":
        if not args:
            send_message(chat_id, "Нужно так: /pc 12")
            return
        try:
            pc_id = int(args[0])
        except Exception:
            send_message(chat_id, "ID должен быть числом.")
            return
        pc = api_get(f"/api/pc/{pc_id}")
        rtmp = _rtmp_url()
        stream_key = pc.get("stream_key")
        page = f"{PUBLIC_BASE_URL}/pc/{pc_id}"
        hls = f"{PUBLIC_BASE_URL}/hls/{stream_key}/index.m3u8"
        msg = (
            f"ПК #{pc_id}: {pc.get('name')}\n"
            f"Server: {rtmp}\n"
            f"Stream Key: {stream_key}\n"
            f"Панель: {page}\n"
            f"HLS: {hls}"
        )
        send_message(chat_id, msg)
        return

    # --- admin toggles ---
    if cmd in {"/savevideos", "/autodelete", "/strictkeys"}:
        if not _admin_ok(user_id):
            send_message(chat_id, "Недостаточно прав (нужен TELEGRAM_ADMIN_ID).")
            return
        if not args or args[0].lower() not in {"on", "off"}:
            send_message(chat_id, "Нужно: on или off. Пример: /savevideos on")
            return
        value = "true" if args[0].lower() == "on" else "false"
        key = cmd.lstrip("/")
        if key == "savevideos":
            key = "save_videos"
        if key == "strictkeys":
            key = "strict_keys"
        api_post_json("/api/settings", {"key": key, "value": value})
        send_message(chat_id, f"Ок: {key} = {value}")
        return

    send_message(chat_id, "Не понял команду. /help")


def main() -> None:
    if not BOT_TOKEN:
        print("[FATAL] TELEGRAM_BOT_TOKEN is empty")
        while True:
            time.sleep(3600)

    offset = 0
    print("Bot started")
    while True:
        try:
            resp = requests.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
                params={"timeout": POLL_TIMEOUT, "offset": offset, "allowed_updates": ["message"]},
                timeout=POLL_TIMEOUT + 10,
            )
            js = resp.json()
            if not js.get("ok"):
                print("getUpdates not ok", js)
                time.sleep(2)
                continue
            for upd in js.get("result", []):
                offset = max(offset, int(upd.get("update_id", 0)) + 1)
                msg = upd.get("message") or {}
                text = msg.get("text") or ""
                chat = msg.get("chat") or {}
                user = msg.get("from") or {}
                if not text.startswith("/"):
                    continue
                chat_id = int(chat.get("id"))
                user_id = int(user.get("id"))
                try:
                    handle_command(chat_id, user_id, text)
                except Exception as e:
                    send_message(chat_id, f"Ошибка обработки: {e}")
        except Exception as e:
            print("poll error", e)
            time.sleep(2)


if __name__ == "__main__":
    main()
