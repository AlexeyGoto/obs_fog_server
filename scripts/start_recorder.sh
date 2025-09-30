#!/usr/bin/env bash
# Запускается при старте стрима: /app/start_recorder.sh <KEY>
set -euo pipefail
KEY="$1"

SEG_TIME="${SEG_TIME:-5}"
LIST_SIZE="${RECORD_SEGMENTS:-84}"   # сколько сегментов держать (7 мин)

SAFE_KEY="$(printf '%s' "$KEY" | tr -cd 'A-Za-z0-9._-')"
[ -n "$SAFE_KEY" ] || SAFE_KEY="stream_$(date +%s)"

DIR="/var/hls_rec/${SAFE_KEY}"
PID="/var/run/rec-${SAFE_KEY}.pid"
START="/var/run/rec-${SAFE_KEY}.start"
LOG="$DIR/rec.log"

trim_log_if_big(){ [ -f "$LOG" ] || return 0; local sz; sz=$(stat -c%s "$LOG" 2>/dev/null||echo 0); [ "$sz" -ge $((10*1024*1024)) ] && : > "$LOG" || true; }

mkdir -p "$DIR"
chown -R nginx:nginx "$DIR"
: > "$LOG"
date +%s > "$START"

# если уже висит — выходим
if [ -f "$PID" ]; then
  P=$(cat "$PID" 2>/dev/null || true)
  if [ -n "${P:-}" ] && kill -0 "$P" 2>/dev/null; then
    echo "$(date '+%F %T') recorder already running for $SAFE_KEY (PID=$P)" >> "$LOG"
    exit 0
  else
    rm -f "$PID"
  fi
fi

# чистим старое
rm -f "$DIR"/*.ts "$DIR"/*.m3u8" 2>/dev/null || true

# ffmpeg пишем HLS-кольцо (copy-only — минимум CPU)
# NB: запускаем в фоне, PID сохраняем — stop-скрипт сам завершит процесс
nohup ffmpeg -hide_banner -loglevel warning -nostats \
  -i "rtmp://127.0.0.1:1935/live/${KEY}" \
  -c copy \
  -f hls \
  -hls_time "$SEG_TIME" \
  -hls_list_size "$LIST_SIZE" \
  -hls_flags delete_segments+split_by_time \
  -hls_segment_filename "$DIR/${SAFE_KEY}-%06d.ts" \
  "$DIR/${SAFE_KEY}.m3u8" >> "$LOG" 2>&1 &

echo $! > "$PID"
echo "$(date '+%F %T') started recorder for $SAFE_KEY (PID=$(cat "$PID"))" >> "$LOG"
trim_log_if_big
exit 0
