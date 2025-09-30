#!/bin/bash
# stop_recorder_and_finalize.sh (video-only assemble, no transcode by default)
APP="$1"
STREAM="$2"

set -eu

SAFE_STREAM="$(printf '%s' "$STREAM" | tr -cd 'A-Za-z0-9._-')"
[ -n "$SAFE_STREAM" ] || SAFE_STREAM="stream_unknown"

RECROOT="/var/hls_rec"
STREAM_DIR="$RECROOT/$SAFE_STREAM"
PIDFILE="/var/run/rec-${SAFE_STREAM}.pid"
STARTFILE="/var/run/rec-${SAFE_STREAM}.start"
FFLOG="$STREAM_DIR/rec.log"
OUTPUT_DIR="/tmp/videos"

# === Твои данные ===
BOT_TOKEN="8402453292:AAHklOKm-xi6HrRinDs20KLZUHL_QcBhsGs"
CHAT_ID="922064185"
# ===================

mkdir -p "$OUTPUT_DIR" "$STREAM_DIR"
touch "$FFLOG"

SEG_CNT=60                           # сколько последних сегментов склеиваем
MAX_TELEGRAM_BYTES=$((50*1024*1024)) # лимит Bot API
MAX_LOG_BYTES=$((10*1024*1024))      # 10 МБ
TRANSCODE_FALLBACK=0                 # 0 — не перекодировать; 1 — попытаться перекод (может нагружать VPS)

trim_log_if_big(){ local f="$1"; [ -f "$f" ] || return 0; local sz; sz=$(stat -c%s "$f" 2>/dev/null||echo 0); [ "$sz" -ge "$MAX_LOG_BYTES" ] && : > "$f" || true; }
log(){ echo "$(date '+%F %T'):" "$@" >> "$FFLOG"; trim_log_if_big "$FFLOG"; }

wait_file_settle(){
  local f="$1" tries=16
  while [ $tries -gt 0 ]; do
    [ -f "$f" ] || { sleep 0.5; tries=$((tries-1)); continue; }
    local s1 s2; s1=$(stat -c%s "$f" 2>/dev/null||echo 0); sleep 0.7; s2=$(stat -c%s "$f" 2>/dev/null||echo 0)
    if [ "$s1" -eq "$s2" ] && [ "$s2" -gt 0 ]; then log "settled: $(basename "$f") size=$s2"; break; fi
    tries=$((tries-1))
  done
}

safe_send_message(){
  curl -s -X POST "https://api.telegram.org/bot$BOT_TOKEN/sendMessage" \
       --data-urlencode "chat_id=$CHAT_ID" \
       --data-urlencode "text=$1" >> "$FFLOG" 2>&1 || true
  trim_log_if_big "$FFLOG"
}

has_video_stream(){ ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of csv=p=0 "$1" >/dev/null 2>&1; }

# 1) аккуратно глушим рекордер
if [ -f "$PIDFILE" ]; then
  PID=$(cat "$PIDFILE" 2>/dev/null || true)
  if [ -n "${PID:-}" ] && kill -0 "$PID" 2>/dev/null; then
    log "stopping recorder PID $PID (stream=$STREAM safe=$SAFE_STREAM)"
    kill -INT "$PID"
    for i in {1..10}; do kill -0 "$PID" 2>/dev/null || break; sleep 1; done
    kill -0 "$PID" 2>/dev/null && { log "force kill $PID"; kill -9 "$PID" || true; }
  fi
  rm -f "$PIDFILE"
fi

sleep 1; sync

# 2) берём последние SEG_CNT файлов по номеру ИЗ ПАПКИ
CANDIDATES=$(ls -1 "$STREAM_DIR"/"${SAFE_STREAM}-"*.ts 2>/dev/null | sort -V || true)
if [ -z "${CANDIDATES:-}" ]; then
  log "no segments in directory"
  safe_send_message "$(printf 'ПК: %s\nВремя начала: -\nВремя окончания: -\n\nСегменты отсутствуют.' "$STREAM")"
  rm -f "$STREAM_DIR"/*.ts 2>/dev/null || true
  rmdir --ignore-fail-on-non-empty "$STREAM_DIR" 2>/dev/null || true
  [ -f "$STARTFILE" ] && rm -f "$STARTFILE" || true
  exit 0
fi
CANDIDATES=$(echo "$CANDIDATES" | tail -n "$SEG_CNT")
LAST_SEG=$(echo "$CANDIDATES" | tail -n1)
[ -n "$LAST_SEG" ] && wait_file_settle "$LAST_SEG"

# 3) стейдж-снимок + фильтр «есть видео»
STAGE_DIR=$(mktemp -d "/tmp/stage_${SAFE_STREAM}_XXXX")
VIDEO_LIST=""
idx=0
while IFS= read -r P; do
  if has_video_stream "$P"; then
    idx=$((idx+1))
    printf -v FN "%06d.ts" "$idx"
    ln "$P" "$STAGE_DIR/$FN" 2>/dev/null || cp -p "$P" "$STAGE_DIR/$FN"
    VIDEO_LIST+="$STAGE_DIR/$FN"$'\n'
  fi
done <<< "$CANDIDATES"

if [ -z "$VIDEO_LIST" ]; then
  log "all last segments are audio-only → nothing to assemble"
  safe_send_message "$(printf 'ПК: %s\nВремя начала: -\nВремя окончания: -\n\nВо входных сегментах отсутствует видеоряд (audio-only). Запись не отправлена.' "$STREAM")"
  rm -rf "$STAGE_DIR"
  rm -f "$STREAM_DIR"/*.ts 2>/dev/null || true
  rmdir --ignore-fail-on-non-empty "$STREAM_DIR" 2>/dev/null || true
  [ -f "$STARTFILE" ] && rm -f "$STARTFILE" || true
  exit 0
fi

LISTFILE="$STAGE_DIR/concat_list.txt"; : > "$LISTFILE"
echo "$VIDEO_LIST" | sed '/^$/d' | sort -V | while read -r f; do echo "file '$f'" >> "$LISTFILE"; done

# 4) тайм-метки
FIRST_STAGED=$(echo "$VIDEO_LIST" | sed '/^$/d' | sort -V | head -n1)
LAST_STAGED=$(echo "$VIDEO_LIST"  | sed '/^$/d' | sort -V | tail -n1)

if [ -f "$STARTFILE" ]; then
  START_TS=$(cat "$STARTFILE" 2>/dev/null || echo '')
  if [ -n "${START_TS:-}" ]; then
    START_FMT=$(date -d "@$START_TS" +"%d.%m.%Y %H.%M.%S")
  else
    START_FMT=$(date -r "$FIRST_STAGED" +"%d.%m.%Y %H.%M.%S")
  fi
else
  START_FMT=$(date -r "$FIRST_STAGED" +"%d.%m.%Y %H.%М.%S")
fi
END_FMT=$(date -r "$LAST_STAGED" +"%d.%m.%Y %H.%M.%S")

OUT_FILE="$OUTPUT_DIR/${SAFE_STREAM}_$(date +%F_%H-%M-%S).mp4"
CAPTION=$(printf "ПК: %s\nВремя начала: %s\nВремя окончания: %s" "$STREAM" "$START_FMT" "$END_FMT")

log "concat $(wc -l < "$LISTFILE") video-segments → $OUT_FILE (video-only)"

# 5) сборка видео-только (копированием)
ffmpeg -hide_banner -loglevel error -nostats \
  -f concat -safe 0 -i "$LISTFILE" \
  -map 0:v:0 -an \
  -fflags +genpts \
  -c:v copy \
  -movflags +faststart \
  "$OUT_FILE" >> "$FFLOG" 2>&1 || true

probe_ok=0
if [ -f "$OUT_FILE" ] && ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,width,height -of csv=p=0 "$OUT_FILE" >/dev/null 2>&1; then
  probe_ok=1
fi

# (опционально) фолбэк-перекод если очень хочется «во что бы то ни стало»
if [ "$probe_ok" -ne 1 ] && [ "$TRANSCODE_FALLBACK" -eq 1 ]; then
  log "remux invalid → transcode (video-only)"
  TMP_OUT="${OUT_FILE%.mp4}.fixed.mp4"; rm -f "$TMP_OUT" 2>/dev/null || true
  ffmpeg -hide_banner -loglevel error -nostats \
    -f concat -safe 0 -i "$LISTFILE" \
    -map 0:v:0 -an \
    -fflags +genpts+igndts+discardcorrupt \
    -vsync 2 \
    -c:v libx264 -preset veryfast -pix_fmt yuv420p -r 30 -g 60 \
    -movflags +faststart -max_interleave_delta 0 \
    "$TMP_OUT" >> "$FFLOG" 2>&1 || true
  if ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,width,height -of csv=p=0 "$TMP_OUT" >/dev/null 2>&1; then
    mv -f "$TMP_OUT" "$OUT_FILE"; log "transcode OK (video-only)"
  else
    log "transcode failed"
  fi
fi

# 6) отправка в Telegram
if [ -f "$OUT_FILE" ]; then
  SIZE=$(stat -c%s "$OUT_FILE" 2>/dev/null || echo 0)
  if [ "$SIZE" -le "$MAX_TELEGRAM_BYTES" ]; then
    log "sendVideo ($SIZE)"
    RESP=$(curl -s -F chat_id="$CHAT_ID" -F "caption=$CAPTION" -F "video=@$OUT_FILE" \
                 "https://api.telegram.org/bot$BOT_TOKEN/sendVideo" 2>&1 || true)
    echo "$RESP" | grep -q '"ok":true' || {
      log "sendVideo failed → sendDocument"
      RESP2=$(curl -s -F chat_id="$CHAT_ID" -F "caption=$CAPTION" -F "document=@$OUT_FILE" \
                    "https://api.telegram.org/bot$BOT_TOKEN/sendDocument" 2>&1 || true)
      echo "$RESP2" | grep -q '"ok":true' || \
        safe_send_message "$(printf 'ПК: %s\nВремя начала: %s\nВремя окончания: %s\n\nФайл не отправился (размер: %s байт).' "$STREAM" "$START_FMT" "$END_FMT" "$SIZE")"
    }
  else
    log "too large ($SIZE)"
    safe_send_message "$(printf 'ПК: %s\nВремя начала: %s\nВремя окончания: %s\n\nФайл слишком большой (размер: %s байт).' "$STREAM" "$START_FMT" "$END_FMT" "$SIZE")"
  fi
else
  safe_send_message "$(printf 'ПК: %s\nВремя начала: %s\nВремя окончания: %s\n\nСборка записи завершилась ошибкой.' "$STREAM" "$START_FMT" "$END_FMT")"
fi

# 7) уборка
rm -rf "$STAGE_DIR" 2>/dev/null || true
[ -f "$STARTFILE" ] && rm -f "$STARTFILE" || true
rm -f "$STREAM_DIR"/*.ts 2>/dev/null || true
rmdir --ignore-fail-on-non-empty "$STREAM_DIR" 2>/dev/null || true
rm -f "$OUT_FILE" 2>/dev/null || true

exit 0
