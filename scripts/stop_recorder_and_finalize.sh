#!/usr/bin/env bash
# Склейка последних N сегментов (видео-только), отправка в Telegram, уборка
set -e

APP="$1"; STREAM="$2"
SAFE_STREAM="$(printf '%s' "$STREAM" | tr -cd 'A-Za-z0-9._-')"; [ -n "$SAFE_STREAM" ] || SAFE_STREAM="stream_unknown"

BOT_TOKEN="${BOT_TOKEN:-}"; CHAT_ID="${CHAT_ID:-}"

DIR="/var/hls_rec/${SAFE_STREAM}"
PID="/var/run/rec-${SAFE_STREAM}.pid"
START="/var/run/rec-${SAFE_STREAM}.start"
LOG="$DIR/rec.log"
OUT="/tmp/videos"; mkdir -p "$OUT"

# Эти переменные должны совпадать со start_recorder (по умолчанию 5 минут)
SEG_TIME="${REC_SEG_TIME:-5}"
BUFFER_SEC="${REC_BUFFER_SEC:-300}"
SEG_CNT="$(( BUFFER_SEC / SEG_TIME ))"

MAX_TG=$((50*1024*1024))

touch "$LOG"

# останов ffmpeg
if [ -f "$PID" ]; then
  P=$(cat "$PID" 2>/dev/null || echo ""); [ -n "$P" ] && kill -INT "$P" 2>/dev/null || true
  sleep 1; kill -0 "$P" 2>/dev/null && kill -9 "$P" 2>/dev/null || true
  rm -f "$PID"
fi

# кандидаты
CANDS=$(ls -1 "$DIR"/"${SAFE_STREAM}-"*.ts 2>/dev/null | sort -V | tail -n "$SEG_CNT") || true
[ -z "${CANDS:-}" ] && echo "$(date '+%F %T'): no segments" >> "$LOG" && exit 0

# подождём, пока последний сегмент допишется
LAST=$(echo "$CANDS" | tail -n1)
for i in {1..10}; do
  s1=$(stat -c%s "$LAST" 2>/dev/null || echo 0); sleep 0.5
  s2=$(stat -c%s "$LAST" 2>/dev/null || echo 0)
  [ "$s1" -eq "$s2" ] && [ "$s2" -gt 0 ] && break
done

# стейдж и фильтр «есть видео»
STAGE=$(mktemp -d)
i=0
for f in $CANDS; do
  ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of csv=p=0 "$f" >/dev/null 2>&1 || continue
  i=$((i+1)); printf -v FN "%06d.ts" "$i"
  ln "$f" "$STAGE/$FN" 2>/dev/null || cp -p "$f" "$STAGE/$FN"
done
[ "$i" -eq 0 ] && echo "$(date '+%F %T'): only audio segments" >> "$LOG" && rm -rf "$STAGE" && exit 0

LIST="$STAGE/concat.txt"; : > "$LIST"
for f in $(ls -1 "$STAGE"/*.ts | sort -V); do echo "file '$f'" >> "$LIST"; done

FIRST=$(ls -1 "$STAGE"/*.ts | sort -V | head -n1)
LASTS=$(ls -1 "$STAGE"/*.ts | sort -V | tail -n1)

if [ -f "$START" ]; then
  START_FMT=$(date -d "@$(cat "$START")" +"%d.%m.%Y %H.%M.%S" 2>/dev/null || date -r "$FIRST" +"%d.%m.%Y %H.%M.%S")
else
  START_FMT=$(date -r "$FIRST" +"%d.%m.%Y %H.%M.%S")
fi
END_FMT=$(date -r "$LASTS" +"%d.%m.%Y %H.%M.%S")

OUTF="$OUT/${SAFE_STREAM}_$(date +%F_%H-%M-%S).mp4"
CAP="ПК: ${STREAM}\nВремя начала: ${START_FMT}\nВремя окончания: ${END_FMT}"

# сборка видео-только
ffmpeg -hide_banner -loglevel error -nostats \
  -f concat -safe 0 -i "$LIST" \
  -map 0:v:0 -an -fflags +genpts -c:v copy -movflags +faststart \
  "$OUTF" >> "$LOG" 2>&1 || true

if [ -f "$OUTF" ] && [ -n "$BOT_TOKEN" ] && [ -n "$CHAT_ID" ]; then
  SIZE=$(stat -c%s "$OUTF")
  if [ "$SIZE" -le "$MAX_TG" ]; then
    curl -s -F chat_id="$CHAT_ID" -F caption="$CAP" -F "video=@$OUTF" "https://api.telegram.org/bot${BOT_TOKEN}/sendVideo" >/dev/null 2>&1 || true
  else
    curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" --data-urlencode chat_id="$CHAT_ID" --data-urlencode text="$CAP"$'\n'"Файл >50 МБ" >/dev/null 2>&1 || true
  fi
fi

# уборка
rm -rf "$STAGE" "$OUTF" 2>/dev/null || true
rm -f "$DIR"/*.ts "$DIR"/*.m3u8 2>/dev/null || true
[ -f "$START" ] && rm -f "$START" || true
rmdir --ignore-fail-on-non-empty "$DIR" 2>/dev/null || true
