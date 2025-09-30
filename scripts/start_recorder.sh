#!/usr/bin/env bash
# Лёгкий рекордер: RTMP -> HLS в /var/hls_rec/<key>/, без перекодирования
set -e

APP="$1"; STREAM="$2"
SAFE_STREAM="$(printf '%s' "$STREAM" | tr -cd 'A-Za-z0-9._-')"; [ -n "$SAFE_STREAM" ] || SAFE_STREAM="stream_$(date +%s)"

# Управление длительностью и «кольцом» через ENV:
SEG_TIME="${REC_SEG_TIME:-5}"          # длина сегмента, сек (советую выставить такой же Keyframe Interval в OBS)
BUFFER_SEC="${REC_BUFFER_SEC:-300}"    # сколько секунд хранить (по умолчанию 5 минут)
LIST_SIZE="$(( BUFFER_SEC / SEG_TIME ))"

DIR="/var/hls_rec/${SAFE_STREAM}"
PID="/var/run/rec-${SAFE_STREAM}.pid"
START="/var/run/rec-${SAFE_STREAM}.start"
LOG="$DIR/rec.log"

mkdir -p "$DIR"
: > "$LOG"
date +%s > "$START"

# уже идёт?
if [ -f "$PID" ] && kill -0 "$(cat "$PID" 2>/dev/null)" 2>/dev/null; then
  echo "$(date '+%F %T'): recorder already running for $SAFE_STREAM" >> "$LOG"
  exit 0
fi
rm -f "$PID" 2>/dev/null || true
rm -f "$DIR"/*.ts "$DIR"/*.m3u8 2>/dev/null || true

# copy-only HLS
nohup ffmpeg -hide_banner -loglevel warning -nostats \
  -i "rtmp://127.0.0.1/$APP/$STREAM" \
  -c copy \
  -f hls \
  -hls_time "$SEG_TIME" \
  -hls_list_size "$LIST_SIZE" \
  -hls_flags delete_segments+split_by_time \
  -hls_segment_filename "$DIR/${SAFE_STREAM}-%06d.ts" \
  "$DIR/${SAFE_STREAM}.m3u8" >> "$LOG" 2>&1 &

echo $! > "$PID"
echo "$(date '+%F %T'): started ($SAFE_STREAM) seg=${SEG_TIME}s, list=${LIST_SIZE}" >> "$LOG"
