#!/usr/bin/env bash
set -euo pipefail

STREAM_NAME="${1:-}"
if [[ -z "$STREAM_NAME" ]]; then
  echo "[on_stream_done] No stream name provided"
  exit 0
fi

HLS_DIR="/tmp/hls/${STREAM_NAME}"
PLAYLIST="${HLS_DIR}/index.m3u8"
OUT_DIR="/var/videos"
OUT_FILE="${OUT_DIR}/${STREAM_NAME}_latest.mp4"

sleep 2

if [[ ! -f "$PLAYLIST" ]]; then
  echo "[on_stream_done] Playlist not found: $PLAYLIST"
  exit 0
fi

mapfile -t REL_SEGMENTS < <(grep -v '^#' "$PLAYLIST" || true)
if [[ ${#REL_SEGMENTS[@]} -eq 0 ]]; then
  echo "[on_stream_done] No segments in playlist"
  exit 0
fi

LIST_TXT="$(mktemp --suffix=.txt)"
> "$LIST_TXT"
for rel in "${REL_SEGMENTS[@]}"; do
  seg="${HLS_DIR}/${rel}"
  if [[ -f "$seg" ]]; then
    printf "file '%s'\n" "$(printf "%s" "$seg" | sed "s/'/'\\\\''/g")" >> "$LIST_TXT"
  fi
done

if [[ ! -s "$LIST_TXT" ]]; then
  echo "[on_stream_done] No segment files found on disk"
  rm -f "$LIST_TXT"
  exit 0
fi

mkdir -p "$OUT_DIR"

if ffmpeg -y -hide_banner -loglevel error -f concat -safe 0 -i "$LIST_TXT" -c copy "$OUT_FILE"; then
  echo "[on_stream_done] Created: $OUT_FILE"
else
  echo "[on_stream_done] Copy concat failed, try remux with genpts"
  if ffmpeg -y -hide_banner -loglevel error -fflags +genpts -f concat -safe 0 -i "$LIST_TXT" -c copy "$OUT_FILE"; then
    echo "[on_stream_done] Remux OK: $OUT_FILE"
  else
    echo "[on_stream_done] Re-encode as fallback"
    ffmpeg -y -hide_banner -loglevel error -f concat -safe 0 -i "$LIST_TXT" \
      -c:v libx264 -preset veryfast -crf 28 -c:a aac -b:a 96k -movflags +faststart "$OUT_FILE" || {
        rm -f "$LIST_TXT"; exit 0; }
  fi
fi

rm -f "$LIST_TXT"

MAX=$((50 * 1024 * 1024))
SIZE=$(stat -c%s "$OUT_FILE" 2>/dev/null || echo 0)
if [[ "$SIZE" -gt "$MAX" ]]; then
  echo "[on_stream_done] File >50MB (${SIZE} bytes). Re-encoding down..."
  TMP="${OUT_FILE%.mp4}_small.mp4"
  ffmpeg -y -hide_banner -loglevel error -i "$OUT_FILE" \
    -c:v libx264 -preset veryfast -b:v 350k -bufsize 700k -maxrate 400k \
    -c:a aac -b:a 96k -movflags +faststart "$TMP" && mv -f "$TMP" "$OUT_FILE"
fi

BOT_TOKEN="${BOT_TOKEN:-}"
CHAT_ID="${CHAT_ID:-}"
BASE_URL="${BASE_URL:-}"

if [[ -z "$BOT_TOKEN" || -z "$CHAT_ID" ]]; then
  echo "[on_stream_done] BOT_TOKEN or CHAT_ID not set. Skipping Telegram."
else
  if [[ -n "$BASE_URL" && "$BASE_URL" != http://* && "$BASE_URL" != https://* ]]; then
    BASE_URL="http://${BASE_URL}"
  fi
  if [[ -z "$BASE_URL" ]]; then
    echo "[on_stream_done] BASE_URL is empty; cannot form public URL."
  else
    FILE_NAME="$(basename "$OUT_FILE")"
    FILE_URL="${BASE_URL%/}/videos/${FILE_NAME}"
    API_URL="https://api.telegram.org/bot${BOT_TOKEN}/sendVideo"
    echo "[on_stream_done] Sending to Telegram: ${FILE_URL}"
    RES=$(curl -s -X POST "$API_URL" \
          -d "chat_id=${CHAT_ID}" \
          --data-urlencode "video=${FILE_URL}" \
          -d "disable_notification=true")
    echo "[on_stream_done] Telegram response: ${RES}"
  fi
fi

rm -f "${HLS_DIR}/"*.ts "${HLS_DIR}/"*.m3u8 2>/dev/null || true
