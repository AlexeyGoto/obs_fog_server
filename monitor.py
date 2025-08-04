#!/usr/bin/env python3
import os, time, requests, datetime, subprocess
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN   = os.getenv('BOT_TOKEN')
CHAT_ID     = os.getenv('CHAT_ID')
STREAM_DIR  = os.getenv('STREAM_FOLDER', '/streams')
INTERVAL    = int(os.getenv('CHECK_INTERVAL', '30'))
MAX_SIZE_MB = 49  # Telegram ограничение — до 50MB

sent = set()

def human_time(ts):
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")

def send_file(p: Path, caption: str):
    if p.stat().st_size > MAX_SIZE_MB * 1024 * 1024:
        print(f"⚠️ Файл {p.name} слишком большой ({p.stat().st_size/1024/1024:.2f} MB)")
        return

    with open(p, 'rb') as f:
        data = {
            'chat_id': CHAT_ID,
            'caption': caption,
            'parse_mode': 'Markdown'
        }
        files = {'document': f}
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
            data=data, files=files
        )
        if r.status_code != 200:
            print(f"❌ Ошибка Telegram: {r.text}")
        else:
            print(f"✅ Отправлено: {p.name}")

def split_and_send(file: Path):
    print(f"📤 Обработка: {file.name}")
    try:
        cmd = [
            'ffmpeg', '-y', '-i', str(file),
            '-c', 'copy', '-f', 'segment',
            '-segment_time', '600', '-reset_timestamps', '1',
            str(file.parent / f"{file.stem}_%03d.flv")
        ]
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка ffmpeg: {e}")
        return

    parts = sorted(file.parent.glob(f"{file.stem}_*.flv"))
    for p in parts:
        caption = (
            f"🎥 *Stream:* `{file.stem}`\n"
            f"⏱ *Start:* {human_time(file.stat().st_ctime)}\n"
            f"⏲ *End:* {human_time(file.stat().st_mtime)}"
        )
        send_file(p, caption)
        p.unlink()

def main():
    print(f"📡 Мониторинг папки: {STREAM_DIR}")
    while True:
        for file in Path(STREAM_DIR).glob("*.flv"):
            file_id = str(file.resolve())
            if file_id in sent:
                continue
            if time.time() - file.stat().st_mtime < INTERVAL:
                continue
            split_and_send(file)
            sent.add(file_id)
        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
