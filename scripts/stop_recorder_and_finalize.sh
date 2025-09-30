#!/usr/bin/env bash
# Запускается из nginx-rtmp: exec_publish_done /usr/local/bin/stop_recorder_and_finalize.sh $app $name
set -euo pipefail

APP="$1"
STREAM="$2"

SAFE_STREAM="$(printf '%s' "$STREAM" | tr -cd 'A-Za-z0-9._-')"
[[ -n "$SAFE_STREAM" ]] || SAFE_STREAM="stream_unknown"

RECROOT="/var/hls_rec"
STREAM_DIR="$RECROOT/$SAFE_STREAM"
PIDFILE="/var/run/rec-${SAFE_STREAM}.pid"
STARTFILE="/var/run/rec-${SAFE_STREAM}.start"
FFLOG="$STREAM_DIR/rec.log"
OUTPUT_DIR="/tmp/videos"

# Telegram
: "${BOT_TOKEN:=}"
: "${CHAT_ID:=}"

mkdir -p "$OUTPUT_DIR" "$STREAM_DIR"
: > "$FFLOG" || true

MAX_LOG_BYTES=$((10*1024*1024))
trim_log(){ local f="$1"; [[ -f "$f" ]] || return 0; local s; s=$(stat -c%s "$f" 2>/dev/null || echo 0); [[ $s -ge $MAX_LOG_BYTES ]] && : > "$f" || true; }
log(){ echo "$(date '+%F %T') [stop] $*" >> "$FFLOG"; trim_log "$FFLOG"; }

# Нежно останавливаем ffmpeg
if [[ -f "$PIDFILE" ]]; then
  PID=$(cat "$PIDFILE" 2>/dev/null || echo "")
  if [[ -n "$PID" ]] && kill -0 "$PID" 2>/dev/null; then
    log "stopping recorder PID=$PID"
    kill -INT "$PID"
    for i in {1..10}; do kill -0 "$PID" 2>/dev/null || break; sleep 1; done
    kill -0 "$PID" 2>/dev/null && { log "force kill $PID"; kill -9 "$PID" || true; }
  fi
  rm -f "$PIDFILE"
fi

sleep 1; sync

REC_M3U8="$STREAM_DIR/${SAFE_STREAM}.m3u8"
if [[ ! -f "$REC_M3U8" ]]; then
  log "playlist not found: $REC_M3U8"
  [[ -n "$BOT_TOKEN" && -n "$CHAT_ID" ]] && \
  curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
       --data-urlencode "chat_id=${CHAT_ID}" \
       --data-urlencode "text=$(printf 'ПК: %s\nВремя начала: -\nВремя окончания: -\n\nПлейлист не найден.' "$STREAM")" >/dev/null || true
  rm -f "$STREAM_DIR"/*.ts 2>/dev/null || true
  rmdir --ignore-fail-on-non-empty "$STREAM_DIR" 2>/dev/null || true
  [[ -f "$STARTFILE" ]] && rm -f "$STARTFILE" || true
  exit 0
fi

# Собираем абсолютные пути сегментов из плейлиста
MAPFILE="$(mktemp)"
awk 'BEGIN{FS="\r"} /^[^#]/ {print $1}' "$REC_M3U8" > "$MAPFILE"
sed -i -e "s#^#${STREAM_DIR}/#; s#//#/#g" "$MAPFILE"
awk 'system("[ -f \""$0"\" ]")==0{print}' "$MAPFILE" > "${MAPFILE}.ok" || true

if [[ ! -s "${MAPFILE}.ok" ]]; then
  log "no segments present per playlist"
  [[ -n "$BOT_TOKEN" && -n "$CHAT_ID" ]] && \
  curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
       --data-urlencode "chat_id=${CHAT_ID}" \
       --data-urlencode "text=$(printf 'ПК: %s\nВремя начала: -\nВремя окончания: -\n\nСегменты отсутствуют.' "$STREAM")" >/dev/null || true
  rm -f "$MAPFILE" "${MAPFILE}.ok"
  exit 0
fi

# Ждём, чтобы последний сегмент «дописался»
wait_settle(){
  local f="$1" tries=16
  while (( tries-- > 0 )); do
    [[ -f "$f" ]] || { sleep 0.5; continue; }
    local s1 s2; s1=$(stat -c%s "$f" 2>/dev/null || echo 0); sleep 0.7; s2=$(stat -c%s "$f" 2>/dev/null || echo 0)
    [[ "$s1" -eq "$s2" && "$s2" -gt 0 ]] && { log "last settled: $(basename "$f") size=$s2"; return 0; }
  done
  return 0
}

LAST_SEG="$(tail -n1 "${MAPFILE}.ok")"
[[ -n "$LAST_SEG" ]] && wait_settle "$LAST_SEG"

# Делаем стабильный снапшот (hardlink), чтобы никакая чистка не помешала
STAGE_DIR="$(mktemp -d "/tmp/stage_${SAFE_STREAM}_XXXX")"
nl -ba "${MAPFILE}.ok" | while read -r N P; do
  printf -v FN "%06d.ts" "$N"
  ln "$P" "$STAGE_DIR/$FN" 2>/dev/null || cp -p "$P" "$STAGE_DIR/$FN"
done
rm -f "$MAPFILE" "${MAPFILE}.ok"

STAGE_LIST=$(ls -1 "$STAGE_DIR"/*.ts 2>/dev/null | sort -V || true)
if [[ -z "${STAGE_LIST:-}" ]]; then
  log "stage empty"
  [[ -n "$BOT_TOKEN" && -n "$CHAT_ID" ]] && \
  curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
       --data-urlencode "chat_id=${CHAT_ID}" \
       --data-urlencode "text=$(printf 'ПК: %s\nВремя начала: -\nВремя окончания: -\n\nНе удалось подготовить сегменты.' "$STREAM")" >/dev/null || true
  rm -rf "$STAGE_DIR"; exit 0
fi

# Отбрасываем «чисто аудио» хвост (оставляем до последнего файла, где есть видео)
has_video(){ ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of csv=p=0 "$1" >/dev/null 2>&1; }
LAST_WITH_VIDEO=""
for f in $(echo "$STAGE_LIST" | tac); do
  if has_video "$f"; then LAST_WITH_VIDEO="$f"; break; fi
done
if [[ -n "$LAST_WITH_VIDEO" ]]; then
  STAGE_LIST=$(echo "$STAGE_LIST" | awk -v last="$LAST_WITH_VIDEO" '{print} $0==last {exit}')
fi

LISTFILE="$STAGE_DIR/concat_list.txt"; : > "$LISTFILE"
while IFS= read -r f; do echo "file '$f'" >> "$LISTFILE"; done <<< "$STAGE_LIST"

FIRST_STAGED=$(echo "$STAGE_LIST" | head -n1)
LAST_STAGED=$(echo "$STAGE_LIST" | tail -n1)

# Таймштампы
if [[ -f "$STARTFILE" ]]; then
  START_TS=$(cat "$STARTFILE" 2>/dev/null || echo '')
  if [[ -n "${START_TS:-}" ]]; then
    START_FMT=$(date -d "@$START_TS" +"%d.%m.%Y %H.%M.%S")
  else
    START_FMT=$(date -r "$FIRST_STAGED" +"%d.%m.%Y %H.%M.%S")
  fi
else
  START_FMT=$(date -r "$FIRST_STAGED" +"%d.%m.%Y %H.%M.%S")
fi
END_FMT=$(date -r "$LAST_STAGED" +"%d.%m.%Y %H.%M.%S")
CAPTION=$(printf "ПК: %s\nВремя начала: %s\nВремя окончания: %s" "$STREAM" "$START_FMT" "$END_FMT")

OUT_FILE="$OUTPUT_DIR/${SAFE_STREAM}_$(date +%F_%H-%M-%S).mp4"
log "concat $(wc -l < "$LISTFILE") segments → $OUT_FILE"

# 1) Remux (copy) — самый дешёвый путь
ffmpeg -hide_banner -loglevel error -nostats \
  -f concat -safe 0 -i "$LISTFILE" \
  -fflags +genpts \
  -c:v copy -c:a aac -ar 48000 -ac 2 -b:a 128k \
  -bsf:a aac_adtstoasc \
  -movflags +faststart \
  "$OUT_FILE" >> "$FFLOG" 2>&1 || true

probe_ok=0
if [[ -f "$OUT_FILE" ]] && ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,width,height -of csv=p=0 "$OUT_FILE" >/dev/null 2>&1; then
  probe_ok=1
fi

# 2) Если copy-ремультиплекс не собрал валидное видео — делаем «починку» (перекод) только по необходимости
if [[ "$probe_ok" -ne 1 ]]; then
  log "remux invalid → transcode"
  TMP_OUT="${OUT_FILE%.mp4}.fixed.mp4"; rm -f "$TMP_OUT" 2>/dev/null || true
  ffmpeg -hide_banner -loglevel error -nostats \
    -f concat -safe 0 -i "$LISTFILE" \
    -fflags +genpts+igndts+discardcorrupt \
    -vsync 2 -async 1 \
    -c:v libx264 -preset veryfast -profile:v high -level 4.1 \
    -pix_fmt yuv420p -r 30 -g 60 \
    -vf "scale=trunc(iw/2)*2:trunc(ih/2)*2" \
    -c:a aac -ar 48000 -ac 2 -b:a 160k \
    -af "aresample=async=1:first_pts=0" \
    -movflags +faststart -max_interleave_delta 0 \
    "$TMP_OUT" >> "$FFLOG" 2>&1 || true
  if ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,width,height -of csv=p=0 "$TMP_OUT" >/dev/null 2>&1; then
    mv -f "$TMP_OUT" "$OUT_FILE"; log "transcode OK"
  else
    log "transcode failed"
  fi
fi

# 3) Telegram
if [[ -f "$OUT_FILE" && -n "$BOT_TOKEN" && -n "$CHAT_ID" ]]; then
  SIZE=$(stat -c%s "$OUT_FILE" 2>/dev/null || echo 0)
  MAX_TELEGRAM_BYTES=$((50*1024*1024))
  if (( SIZE <= MAX_TELEGRAM_BYTES )); then
    log "sendVideo (${SIZE} bytes)"
    RESP=$(curl -s -F chat_id="$CHAT_ID" -F "caption=$CAPTION" -F "video=@$OUT_FILE" \
                 "https://api.telegram.org/bot${BOT_TOKEN}/sendVideo" 2>&1 || true)
    echo "$RESP" | grep -q '"ok":true' || {
      log "sendVideo failed → sendDocument"
      RESP2=$(curl -s -F chat_id="$CHAT_ID" -F "caption=$CAPTION" -F "document=@$OUT_FILE" \
                    "https://api.telegram.org/bot${BOT_TOKEN}/sendDocument" 2>&1 || true)
      echo "$RESP2" | grep -q '"ok":true' || \
        curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
             --data-urlencode "chat_id=${CHAT_ID}" \
             --data-urlencode "text=$(printf 'ПК: %s\nВремя начала: %s\nВремя окончания: %s\n\nФайл не отправился (размер: %s байт).' "$STREAM" "$START_FMT" "$END_FMT" "$SIZE")" >/dev/null || true
    }
  else
    log "too large (${SIZE})"
    curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
         --data-urlencode "chat_id=${CHAT_ID}" \
         --data-urlencode "text=$(printf 'ПК: %s\nВремя начала: %s\nВремя окончания: %s\n\nФайл слишком большой (размер: %s байт).' "$STREAM" "$START_FMT" "$END_FMT" "$SIZE")" >/dev/null || true
  fi
fi

# 4) Уборка
rm -rf "$STAGE_DIR" 2>/dev/null || true
[[ -f "$STARTFILE" ]] && rm -f "$STARTFILE" || true
rm -f "$STREAM_DIR"/*.ts 2>/dev/null || true
rmdir --ignore-fail-on-non-empty "$STREAM_DIR" 2>/dev/null || true
rm -f "$OUT_FILE" 2>/dev/null || true

log "done"
exit 0
