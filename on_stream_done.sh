#!/usr/bin/env bash
# Скрипт вызывается Nginx-RTMP при завершении публикации ($name)
set -euo pipefail

STREAM_NAME="${1:-}"
if [[ -z "$STREAM_NAME" ]]; then
  echo "[on_stream_done] No stream name provided"
  exit 0
fi

HLS_DIR="/tmp/hls/${STREAM_NAME}"
PLAYLIST="${HLS_DIR}/${STREAM_NAME}.m3u8"
OUT_DIR="/var/videos"
OUT_FILE="${OUT_DIR}/${STREAM_NAME}_latest.mp4"

# Подождём, чтобы финальный сегмент закрылся
sleep 2

if [[ ! -f "$PLAYLIST" ]]; then
  echo "[on_stream_done] Playlist not found: $PLAYLIST"
  exit 0
fi

# Прочитаем список сегментов (строки без #), добавим абсолютные пути
mapfile -t SEGMENTS < <(grep -v '^#' "$PLAYLIST" || true)

if [[ ${#SEGMENTS[@]} -eq 0 ]]; then
  echo "[on_stream_done] No segments in playlist"
  exit 0
fi

# Склеим только реально существующие файлы
CONCAT_LIST=()
for seg in "${SEGMENTS[@]}"; do
  seg_path="${HLS_DIR}/${seg}"
  if [[ -f "$seg_path" ]]; then
    CONCAT_LIST+=("$seg_path")
  fi
done

if [[ ${#CONCAT_LIST[@]} -eq 0 ]]; then
  echo "[on_stream_done] No segment files found on disk"
  exit 0
fi

# Соберём строку для concat протокола
# (экранируем спецсимволы в путях)
join_by() { local IFS="$1"; shift; echo "$*"; }
ESCAPED=()
for p in "${CONCAT_LIST[@]}"; do
  # ffmpeg concat-протокол допускает специальные символы, но безопаснее экранировать \, ' и пробел
  ESCAPED+=( "$(printf "%s" "$p" | sed "s/\\/\\\\/g; s/'/\\\\'/g")" )
done
CONCAT_STR=$(join_by '|' "${ESCAPED[@]}")

# Склеиваем БЕЗ перекодирования
mkdir -p "$OUT_DIR"
if ffmpeg -y -hide_banner -loglevel error -i "concat:${CONCAT_STR}" -c copy "$OUT_FILE"; then
  echo "[on_stream_done] Created: $OUT_FILE"
else
  echo "[on_stream_done] Direct concat failed, trying remux"
  # Редкий случай — пробуем через remux (копия дорожек в контейнер mp4 может упасть из-за таймстампов)
  ffmpeg -y -hide_banner -loglevel error -fflags +genpts -i "concat:${CONCAT_STR}" -c copy "$OUT_FILE" || {
    echo "[on_stream_done] Remux failed, trying re-encode small"
    # Последняя попытка — быстрая перекодировка в H264/AAC (на сверхнизком битрейте это мгновенно)
    ffmpeg -y -hide_banner -loglevel error -i "concat:${CONCAT_STR}" \
      -c:v libx264 -preset veryfast -crf 28 -c:a aac -b:a 96k -movflags +faststart "$OUT_FILE" || exit 0
  }
fi

# Гарантия, что файл уложится < 50 МБ (перекодируем при необходимости)
MAX=$((50 * 1024 * 1024))
SIZE=$(stat -c%s "$OUT_FILE" 2>/dev/null || echo 0)
if [[ "$SIZE" -gt "$MAX" ]]; then
  echo "[on_stream_done] File >50MB (${SIZE} bytes). Re-encoding down..."
  TMP="${OUT_FILE%.mp4}_small.mp4"
  # Примерно 350 kbps видео + 96 kbps аудио => ~ 27 MB за 5 минут
  ffmpeg -y -hide_banner -loglevel error -i "$OUT_FILE" \
    -c:v libx264 -preset veryfast -b:v 350k -bufsize 700k -maxrate 400k \
    -c:a aac -b:a 96k -movflags +faststart "$TMP" && mv -f "$TMP" "$OUT_FILE"
fi

# Отправка в Telegram как файл по ссылке (Telegram скачает с нашего HTTP /videos)
BOT_TOKEN="${BOT_TOKEN:-}"
CHAT_ID="${CHAT_ID:-}"
BASE_URL="${BASE_URL:-}"

if [[ -z "$BOT_TOKEN" || -z "$CHAT_ID" ]]; then
  echo "[on_stream_done] BOT_TOKEN or CHAT_ID not set. Skipping Telegram."
else
  # Требуется ПУБЛИЧНЫЙ base URL вашего сервиса (например, https://stream.example.com)
  if [[ -z "$BASE_URL" ]]; then
    echo "[on_stream_done] BASE_URL is not set; Telegram may not access the file."
  fi
  # Сформируем ссылку (без двойных слешей)
  BASE_TRIM="${BASE_URL%/}"
  FILE_NAME="$(basename "$OUT_FILE")"
  FILE_URL="${BASE_TRIM}/videos/${FILE_NAME}"

  API_URL="https://api.telegram.org/bot${BOT_TOKEN}/sendVideo"
  # disable_notification=true — по желанию, можно убрать
  RES=$(curl -s -X POST "$API_URL" \
        -d "chat_id=${CHAT_ID}" \
        --data-urlencode "video=${FILE_URL}" \
        -d "disable_notification=true")
  echo "[on_stream_done] Telegram response: ${RES}"
fi

# Удаляем HLS мусор конкретного стрима (держим чистоту)
rm -f "${HLS_DIR}/"*.ts "${HLS_DIR}/"*.m3u8 2>/dev/null || true
