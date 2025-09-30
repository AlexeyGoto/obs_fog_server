#!/bin/bash
# start_recorder.sh (COPY-ONLY, без перекодирования)
APP="$1"
STREAM="$2"

# Безопасное имя для ФС
SAFE_STREAM="$(printf '%s' "$STREAM" | tr -cd 'A-Za-z0-9._-')"
[ -n "$SAFE_STREAM" ] || SAFE_STREAM="stream_$(date +%s)"

RECROOT="/var/hls_rec"
STREAM_DIR="$RECROOT/$SAFE_STREAM"
PIDFILE="/var/run/rec-${SAFE_STREAM}.pid"
STARTFILE="/var/run/rec-${SAFE_STREAM}.start"
FFLOG="$STREAM_DIR/rec.log"

SEG_TIME=5     # длина сегмента, сек (очень советую поставить тут же в OBS Keyframe Interval = 2)
LIST_SIZE=60   # сколько сегментов хранить (последние 20)

mkdir -p "$STREAM_DIR"
chown www-data:www-data "$STREAM_DIR"
chmod 755 "$STREAM_DIR"
touch "$FFLOG"

# уже запущен?
if [ -f "$PIDFILE" ]; then
  PID=$(cat "$PIDFILE" 2>/dev/null)
  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    echo "$(date '+%F %T'): recorder already running for $STREAM (safe=$SAFE_STREAM) PID=$PID" >> "$FFLOG"
    exit 0
  else
    rm -f "$PIDFILE"
  fi
fi

# чистим старое
rm -f "$STREAM_DIR"/*.ts "$STREAM_DIR"/*.m3u8 2>/dev/null || true

# время старта (для подписи)
date +%s > "$STARTFILE"
chown www-data:www-data "$STARTFILE"

# HLS muxer, copy-only. ВАЖНО: для ровных сегментов в OBS выстави keyframe interval = SEG_TIME.
nohup ffmpeg -y -hide_banner -loglevel warning -nostats \
  -i "rtmp://127.0.0.1/$APP/$STREAM" \
  -c copy \
  -f hls \
  -hls_time "$SEG_TIME" \
  -hls_list_size "$LIST_SIZE" \
  -hls_flags delete_segments+split_by_time \
  -hls_segment_filename "$STREAM_DIR/${SAFE_STREAM}-%06d.ts" \
  "$STREAM_DIR/${SAFE_STREAM}.m3u8" >> "$FFLOG" 2>&1 &

echo $! > "$PIDFILE"
echo "$(date '+%F %T'): started recorder for $STREAM (safe=$SAFE_STREAM) PID=$(cat $PIDFILE)" >> "$FFLOG"
exit 0
