#!/usr/bin/env bash
# /app/stop_recorder_and_finalize.sh <KEY>
set -euo pipefail
KEY="$1"

BOT_TOKEN="${BOT_TOKEN:-}"
CHAT_ID="${CHAT_ID:-}"
SEG_TIME="${SEG_TIME:-5}"
SEG_CNT="${RECORD_SEGMENTS:-84}"

SAFE_KEY="$(printf '%s' "$KEY" | tr -cd 'A-Za-z0-9._-')"
[ -n "$SAFE_KEY" ] || SAFE_KEY="stream_unknown"

DIR="/var/hls_rec/${SAFE_KEY}"
PID="/var/run/rec-${SAFE_KEY}.pid"
START="/var/run/rec-${SAFE_KEY}.start"
LOG="$DIR/rec.log"
OUT_DIR="/tmp/videos"; mkdir -p "$OUT_DIR"

MAX_TG=$((50*1024*1024))
trim_log_if_big(){ [ -f "$LOG" ] || return 0; local sz; sz=$(stat -c%s "$LOG" 2>/dev/null||echo 0); [ "$sz" -ge $((10*1024*1024)) ] && : > "$LOG" || true; }
log(){ echo "$(date '+%F %T'): $*" >> "$LOG"; trim_log_if_big; }
safe_send_msg(){ local text="$1"; [ -n "$BOT_TOKEN" ] && [ -n "$CHAT_ID" ] && curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" --data-urlencode "chat_id=${CHAT_ID}" --data-urlencode "text=${text}" >/dev/null 2>&1 || true; }

if [ -f "$PID" ]; then
  P=$(cat "$PID" 2>/dev/null || true)
  if [ -n "${P:-}" ] && kill -0 "$P" 2>/dev/null; then
    log "stopping recorder PID $P"
    kill -INT "$P" 2>/dev/null || true
    for i in {1..10}; do kill -0 "$P" 2>/dev/null || break; sleep 1; done
    kill -0 "$P" 2>/dev/null && { log "force kill $P"; kill -9 "$P" 2>/dev/null || true; }
  fi
  rm -f "$PID"
fi

sleep 1; sync

mapfile -t CANDS < <(ls -1 "$DIR"/"${SAFE_KEY}-"*.ts 2>/dev/null | sort -V | tail -n "$SEG_CNT")
if [ "${#CANDS[@]}" -eq 0 ]; then
  log "no segments found"
  safe_send_msg "$(printf 'ПК: %s\nВремя начала: -\nВремя окончания: -\n\nЗапись не найдена.' "$KEY")"
  rm -f "$DIR"/*.ts "$DIR"/*.m3u8 2>/dev/null || true
  rmdir --ignore-fail-on-non-empty "$DIR" 2>/dev/null || true
  [ -f "$START" ] && rm -f "$START" || true
  exit 0
fi

last="${CANDS[-1]}"
if [ -n "$last" ]; then
  tries=12
  while [ $tries -gt 0 ]; do
    s1=$(stat -c%s "$last" 2>/dev/null || echo 0); sleep 0.7
    s2=$(stat -c%s "$last" 2>/dev/null || echo 0)
    [ "$s1" -eq "$s2" ] && [ "$s2" -gt 0 ] && break
    tries=$((tries-1))
  done
  log "last segment settled: $(basename "$last")"
fi

STAGE="$(mktemp -d "/tmp/stage_${SAFE_KEY}_XXXX")"
idx=0
for f in "${CANDS[@]}"; do
  if ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of csv=p=0 "$f" >/dev/null 2>&1; then
    idx=$((idx+1)); printf -v FN "%06d.ts" "$idx"
    ln "$f" "$STAGE/$FN" 2>/dev/null || cp -p "$f" "$STAGE/$FN"
  fi
done
if [ "$idx" -eq 0 ]; then
  log "all candidates audio-only"
  safe_send_msg "$(printf 'ПК: %s\nВремя начала: -\nВремя окончания: -\n\nВо входных сегментах отсутствует видеоряд.' "$KEY")"
  rm -rf "$STAGE"; rm -f "$DIR"/*.ts "$DIR"/*.m3u8 2>/dev/null || true
  rmdir --ignore-fail-on-non-empty "$DIR" 2>/dev/null || true
  [ -f "$START" ] && rm -f "$START" || true
  exit 0
fi

LIST="$STAGE/concat.txt"; : > "$LIST"
for f in $(ls -1 "$STAGE"/*.ts | sort -V); do echo "file '$f'" >> "$LIST"; done

FIRST="$(ls -1 "$STAGE"/*.ts | sort -V | head -n1)"
LASTF="$(ls -1 "$STAGE"/*.ts | sort -V | tail -n1)"
if [ -f "$START" ]; then
  S_TS=$(cat "$START" 2>/dev/null || echo '')
  [ -n "$S_TS" ] && START_FMT="$(date -d "@$S_TS" +"%d.%m.%Y %H.%M.%S")" || START_FMT="$(date -r "$FIRST" +"%d.%m.%Y %H.%M.%S")"
else
  START_FMT="$(date -r "$FIRST" +"%d.%m.%Y %H.%M.%S")"
fi
END_FMT="$(date -r "$LASTF" +"%d.%m.%Y %H.%M.%S")"

OUTF="$OUT_DIR/${SAFE_KEY}_$(date +%F_%H-%M-%S).mp4"
CAPTION=$(printf "ПК: %s\nВремя начала: %s\nВремя окончания: %s" "$KEY" "$START_FMT" "$END_FMT")

log "concat $(wc -l < "$LIST") video-segments -> $OUTF"

ffmpeg -hide_banner -loglevel error -nostats \
  -f concat -safe 0 -i "$LIST" \
  -map 0:v:0 -an -fflags +genpts \
  -c:v copy -movflags +faststart \
  "$OUTF" >> "$LOG" 2>&1 || true

if [ -f "$OUTF" ]; then
  SIZE=$(stat -c%s "$OUTF" 2>/dev/null || echo 0)
  if [ -n "$BOT_TOKEN" ] && [ -n "$CHAT_ID" ]; then
    if [ "$SIZE" -le "$MAX_TG" ]; then
      curl -s -F "chat_id=${CHAT_ID}" -F "caption=${CAPTION}" -F "video=@${OUTF}" \
           "https://api.telegram.org/bot${BOT_TOKEN}/sendVideo" >/dev/null 2>&1 || true
    else
      curl -s -F "chat_id=${CHAT_ID}" -F "caption=${CAPTION}" -F "document=@${OUTF}" \
           "https://api.telegram.org/bot${BOT_TOKEN}/sendDocument" >/dev/null 2>&1 || true
    fi
  fi
fi

rm -rf "$STAGE" 2>/dev/null || true
[ -f "$OUTF" ] && rm -f "$OUTF" || true
rm -f "$DIR"/*.ts "$DIR"/*.m3u8 2>/dev/null || true
[ -f "$START" ] && rm -f "$START" || true
rmdir --ignore-fail-on-non-empty "$DIR" 2>/dev/null || true
exit 0
