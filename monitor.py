#!/usr/bin/env python3
import os, time, requests, datetime, subprocess
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
CHAT_ID   = os.getenv('CHAT_ID')
STREAM_DIR= os.getenv('STREAM_FOLDER','/streams')
INTERVAL  = int(os.getenv('CHECK_INTERVAL','30'))

sent = set()

def split_and_send(file: Path):
    cmd = [
      'ffmpeg','-i',str(file),
      '-c','copy','-f','segment',
      '-segment_time','600','-reset_timestamps','1',
      str(file.parent/f"{file.stem}_%03d.flv")
    ]
    subprocess.run(cmd, check=True)
    parts = sorted(file.parent.glob(f"{file.stem}_*.flv"))
    for p in parts:
        with open(p,'rb') as f:
            caption = (
              f"🎥 Stream `{file.stem}`\n"
              f"⏱ Start: {datetime.datetime.fromtimestamp(file.stat().st_ctime)}\n"
              f"⏲ End:   {datetime.datetime.fromtimestamp(file.stat().st_mtime)}"
            )
            data = {'chat_id':CHAT_ID,'caption':caption,'parse_mode':'Markdown'}
            files = {'video':f}
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo",
                          data=data, files=files)
        p.unlink()

def main():
    while True:
        for file in Path(STREAM_DIR).glob("*.flv"):
            if file in sent: continue
            if time.time()-file.stat().st_mtime < INTERVAL: continue
            split_and_send(file)
            sent.add(file)
        time.sleep(INTERVAL)

if __name__=="__main__":
    main()
