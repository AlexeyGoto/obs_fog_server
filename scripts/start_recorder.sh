#!/usr/bin/env bash
# Запускается из nginx-rtmp: exec_publish  /usr/local/bin/start_recorder.sh $app $name
set -euo pipefail

APP="$1"
STREAM="$2"

# Безопасное имя на ФС
SAFE_STREAM="$(printf '%s' "$STREAM" | tr -cd 'A-Za-z0-9._-')"
[[ -n "$SAFE_STREAM" ]] || SAFE_STREAM="stream_$(date +%s)"

# Папка с HLS-сегментами отдельного рекордера
RECROOT="/var/hls_rec"
STREAM_DIR="$RECROOT/$SAFE_STREAM"

PIDFILE="/var/run/rec-${SAFE_STREAM}.pid"
STARTFILE="/var/run/rec-${SAFE_STREAM}.start"
FFLOG="$STREAM_DIR/rec.log"

# --- управление размером окна записи по ENV ---
: "${RECORDER_WINDOW_SECONDS:=300}"   # последние 5 минут (по умолчанию)
: "${HLS_SEGMENT_SECONDS:=2}"         # длительность сегмента
LIST_SIZE=$(( RECORDER_WINDOW_SECONDS / HLS_SEGMENT_SECONDS ))
[[ $LIST_SIZE -lt 5 ]] && LIST_SIZE=5
# ----------------------------------------------

MAX_LOG_BYTES=$((10*1024*1024))
trim_log(){ local f="$1"; [[ -f "$f" ]] || return 0; local s; s=$(stat -c%s "$f" 2>/dev/null || echo 0); [[ $s -ge $MAX_LOG_BYTES ]] && : > "$f" || true; }
log(){ echo "$(date '+%F %T') [start] $*" >> "$FFLOG"; trim_log "$FFLOG"; }

mkdir -p "$STREAM_DIR"
: > "$FFLOG"

# Уже запущен?
if [[ -f "$PIDFILE" ]]; then
  PID=$(cat "$PIDFILE" 2>/dev/null || echo "")
  if [[ -n "$PID" ]] && kill -0 "$PID" 2>/dev/null; then
    log "recorder already running for $STREAM (PID=$PID)"; exit 0
  else
    rm -f "$PIDFILE"
  fi
fi

# Чистим предыдущие следы (важно!)
rm -f "$STREAM_DIR"/*.ts "$STREAM_DIR"/*.m3u8 2>/dev/null || true

# Сохраняем время старта (epoch)
date +%s > "$STARTFILE"

# ВАЖНО: нулевой CPU — пишем HLS-сегменты в copy-режиме.
# Монотонная нумерация файлов, delete старых сегментов, размер плейлиста = окно записи.
nohup ffmpeg -y -hide_banner -loglevel warning -nostats \
  -i "rtmp://127.0.0.1/${APP}/${STREAM}" \
  -c copy \
  -f hls \
  -hls_time "$HLS_SEGMENT_SECONDS" \
  -hls_list_size "$LIST_SIZE" \
  -hls_flags delete_segments+split_by_time \
  -hls_segment_filename "$STREAM_DIR/${SAFE_STREAM}-%06d.ts" \
  "$STREAM_DIR/${SAFE_STREAM}.m3u8" >> "$FFLOG" 2>&1 &

echo $! > "$PIDFILE"
log "started (PID=$(cat "$PIDFILE"), list_size=${LIST_SIZE}, seg=${HLS_SEGMENT_SECONDS}s)"
exit 0
