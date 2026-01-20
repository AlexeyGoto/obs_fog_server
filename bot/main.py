from __future__ import annotations

import os
import time
from dataclasses import dataclass

import requests
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    telegram_bot_token: str = ''
    api_base_url: str = 'http://api:8000'
    bot_api_token: str = 'change_me'

    poll_timeout: int = 25


S = Settings()


def tg_method(method: str, params: dict | None = None) -> dict:
    url = f"https://api.telegram.org/bot{S.telegram_bot_token}/{method}"
    r = requests.post(url, json=params or {}, timeout=60)
    try:
        return r.json()
    except Exception:
        return {'ok': False, 'status_code': r.status_code, 'text': r.text}


def send_message(chat_id: str, text: str):
    tg_method('sendMessage', {'chat_id': chat_id, 'text': text})


def api_get(path: str, params: dict) -> dict:
    url = f"{S.api_base_url}{path}"
    r = requests.get(url, params=params, headers={'X-Bot-Token': S.bot_api_token}, timeout=30)
    if r.status_code >= 400:
        return {'error': r.text, 'status_code': r.status_code}
    return r.json()


def api_post(path: str, payload: dict) -> dict:
    url = f"{S.api_base_url}{path}"
    r = requests.post(url, json=payload, headers={'X-Bot-Token': S.bot_api_token}, timeout=30)
    if r.status_code >= 400:
        return {'error': r.text, 'status_code': r.status_code}
    return r.json()


HELP = (
    "Команды:\n"
    "/link CODE — привязать Telegram к аккаунту (CODE смотри на сайте /settings)\n"
    "/pcs — список твоих ПК\n"
    "/obs PC_ID — настройки OBS (RTMP + key)\n"
    "/live PC_ID — ссылка на live просмотр\n"
)


def handle_message(msg: dict):
    chat = msg.get('chat', {})
    chat_id = str(chat.get('id'))
    text = (msg.get('text') or '').strip()
    if not text:
        return

    parts = text.split()
    cmd = parts[0].lower()

    if cmd in ('/start', '/help'):
        send_message(chat_id, HELP)
        return

    if cmd == '/link':
        if len(parts) < 2:
            send_message(chat_id, 'Использование: /link CODE (CODE смотри на сайте /settings)')
            return
        code = parts[1].strip()
        res = api_post('/bot/link', {'code': code, 'telegram_id': chat_id})
        if res.get('ok'):
            send_message(chat_id, f"Готово! Аккаунт {res.get('email')} привязан.")
        else:
            send_message(chat_id, 'Не получилось привязать. Проверь CODE или создай новый в настройках.')
        return

    if cmd == '/pcs':
        res = api_get('/bot/pcs', {'telegram_id': chat_id})
        if 'pcs' not in res:
            send_message(chat_id, 'Telegram не привязан. Открой сайт → /settings → /link CODE.')
            return
        pcs = res['pcs']
        if not pcs:
            send_message(chat_id, 'У тебя нет ПК. Добавь на сайте.')
            return
        lines = ['Твои ПК:']
        for p in pcs:
            lines.append(f"{p['id']}: {p['name']}")
        send_message(chat_id, '\n'.join(lines))
        return

    if cmd == '/obs':
        if len(parts) < 2 or not parts[1].isdigit():
            send_message(chat_id, 'Использование: /obs PC_ID')
            return
        pc_id = int(parts[1])
        res = api_get('/bot/obs', {'telegram_id': chat_id, 'pc_id': pc_id})
        if 'server' not in res:
            send_message(chat_id, 'Не найдено. Проверь PC_ID или привязку Telegram.')
            return
        send_message(chat_id, f"OBS настройки для {res['pc_name']} (ID {res['pc_id']}):\nServer: {res['server']}\nKey: {res['key']}")
        return

    if cmd == '/live':
        if len(parts) < 2 or not parts[1].isdigit():
            send_message(chat_id, 'Использование: /live PC_ID')
            return
        pc_id = int(parts[1])
        res = api_get('/bot/live', {'telegram_id': chat_id, 'pc_id': pc_id})
        if 'url' not in res:
            send_message(chat_id, 'Не найдено. Проверь PC_ID или привязку Telegram.')
            return
        send_message(chat_id, f"Live {res['pc_name']} (ID {res['pc_id']}):\n{res['url']}\nHLS: {res['hls']}")
        return

    send_message(chat_id, 'Не понял команду. /help')


def main():
    if not S.telegram_bot_token:
        raise SystemExit('TELEGRAM_BOT_TOKEN is not set')

    offset = 0
    while True:
        try:
            res = requests.get(
                f"https://api.telegram.org/bot{S.telegram_bot_token}/getUpdates",
                params={'timeout': S.poll_timeout, 'offset': offset},
                timeout=S.poll_timeout + 10,
            ).json()

            if not res.get('ok'):
                time.sleep(2)
                continue

            for upd in res.get('result', []):
                offset = max(offset, int(upd.get('update_id', 0)) + 1)
                msg = upd.get('message') or upd.get('edited_message')
                if msg:
                    handle_message(msg)
        except Exception:
            time.sleep(2)


if __name__ == '__main__':
    main()
