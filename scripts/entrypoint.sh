#!/usr/bin/env bash
set -euo pipefail

LOG="/app/log/entrypoint.log"
exec > >(tee -a "$LOG") 2>&1

echo "=== [ENTRYPOINT] $(date '+%F %T') starting ==="
echo "[ENTRYPOINT] env: STREAM_KEYS='${STREAM_KEYS:-}', BOT_TOKEN set? $([ -n "${BOT_TOKEN:-}" ] && echo yes || echo no), CHAT_ID='${CHAT_ID:-}'"

STREAM_KEYS="${STREAM_KEYS:-}"
BOT_TOKEN="${BOT_TOKEN:-}"
CHAT_ID="${CHAT_ID:-}"
PUBLIC_HOST="${PUBLIC_HOST:-}"
SEG_TIME="${SEG_TIME:-5}"
RECORD_SEGMENTS="${RECORD_SEGMENTS:-84}"

# фикс для nginx-rtmp exec в Docker
ulimit -n 1024 || true

# Подготовим директории
mkdir -p /var/hls /var/hls_rec /tmp/videos /app/obs_profiles /app/www
echo "OK" > /app/www/healthz

detect_public_host() {
  if [ -n "$PUBLIC_HOST" ]; then
    echo "$PUBLIC_HOST"; return
  fi
  PH="$(curl -fsS --max-time 3 http://ifconfig.me || true)"
  if [ -n "$PH" ]; then echo "$PH"; else hostname -i | awk '{print $1}'; fi
}
PHOST="$(detect_public_host)"
echo "[ENTRYPOINT] PUBLIC HOST: $PHOST"

# Разбираем ключи (даже если пусто — сгенерим заглушку)
IFS=',' read -r -a KEYS <<< "${STREAM_KEYS}"

# Генерация index.html
echo "[ENTRYPOINT] Generating /app/www/index.html ..."
{
  cat <<'HTML_HEAD'
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <title>Streams</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <link href="https://vjs.zencdn.net/7.21.1/video-js.css" rel="stylesheet" />
  <style>
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial; margin: 16px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fill,minmax(360px,1fr)); gap: 16px; }
    .tile { border: 1px solid #ddd; border-radius: 12px; padding: 12px; box-shadow: 0 2px 10px rgba(0,0,0,.04); }
    .title { margin: 0 0 8px; font-weight: 600; font-size: 14px; color: #333; }
    .video-js { width: 100%; height: 202px; border-radius: 8px; overflow: hidden; }
    code { background: #f6f6f6; padding: 1px 6px; border-radius: 6px; }
  </style>
</head>
<body>
  <h1 style="margin-top:0">Live Streams</h1>
  <div class="grid">
HTML_HEAD

  CNT=0
  for KEY in "${KEYS[@]}"; do
    KTRIM="$(echo "$KEY" | xargs)"; [ -z "$KTRIM" ] && continue
    CNT=$((CNT+1))
    cat <<HTML_TILE
    <div class="tile">
      <div class="title">Ключ: <code>${KTRIM}</code></div>
      <video id="v_${KTRIM}" class="video-js vjs-default-skin" controls preload="auto" playsinline>
        <source src="/hls/${KTRIM}.m3u8" type="application/x-mpegURL" />
      </video>
    </div>
HTML_TILE
  done

  if [ "$CNT" -eq 0 ]; then
    cat <<HTML_EMPTY
    <div class="tile"><div class="title">Ключи не заданы</div>
      <p>В переменной окружения <code>STREAM_KEYS</code> перечисли ключи через запятую.<br>
      Пример: <code>STREAM_KEYS=12952x11,pc7</code></p>
      <p>RTMP: <code>rtmp://${PHOST}:1935/live</code></p>
    </div>
HTML_EMPTY
  fi

  cat <<'HTML_TAIL'
  </div>
  <script src="https://vjs.zencdn.net/7.21.1/video.min.js"></script>
</body>
</html>
HTML_TAIL
} > /app/www/index.html

ls -l /app/www

# OBS-профили + отправка в Telegram
make_and_send_profile() {
  local KEY="$1"
  local PROF="LowVPS-RTMP-${KEY}"
  local DIR="/app/obs_profiles/${PROF}"
  mkdir -p "$DIR"

  cat > "$DIR/basic.ini" <<EOF
[General]
Name=${PROF}

[Output]
Mode=Advanced

[AdvOut]
Encoder=obs_x264
Bitrate=500
KeyframeIntervalSec=2
Rescale=false
TrackIndex=1
ApplyServiceSettings=false

[Audio]
SampleRate=48000
ChannelSetup=Stereo

[Video]
BaseCX=854
BaseCY=480
OutputCX=854
OutputCY=480
FPSType=Simple
FPSCommon=30
EOF

  cat > "$DIR/service.json" <<EOF
{
  "type": "rtmp_custom",
  "settings": {
    "service": "Custom",
    "server": "rtmp://${PHOST}:1935/live",
    "key": "${KEY}",
    "bwtest": false
  },
  "hotkeys": {}
}
EOF

  (cd /app/obs_profiles && zip -rq "${PROF}.zip" "${PROF}")
  echo "[ENTRYPOINT] Profile zipped: /app/obs_profiles/${PROF}.zip"

  if [ -n "$BOT_TOKEN" ] && [ -n "$CHAT_ID" ]; then
    echo "[ENTRYPOINT] Sending OBS profile for '${KEY}' to Telegram..."
    curl -s -F "chat_id=${CHAT_ID}" \
         -F "document=@/app/obs_profiles/${PROF}.zip" \
         -F "caption=OBS профиль для ключа ${KEY}\nRTMP: rtmp://${PHOST}:1935/live\nKey: ${KEY}" \
         "https://api.telegram.org/bot${BOT_TOKEN}/sendDocument" >/dev/null 2>&1 || true
  else
    echo "[ENTRYPOINT] BOT_TOKEN/CHAT_ID not set; not sending profiles"
  fi
}

SENT=0
for KEY in "${KEYS[@]}"; do
  KTRIM="$(echo "$KEY" | xargs)"; [ -z "$KTRIM" ] && continue
  make_and_send_profile "$KTRIM"
  SENT=$((SENT+1))
done
echo "[ENTRYPOINT] Profiles processed: $SENT"

# sanity-чек nginx конфига
echo "[ENTRYPOINT] nginx -t"
nginx -t || { echo "[ENTRYPOINT] nginx -t failed"; cat /etc/nginx/nginx.conf; exit 1; }

echo "[ENTRYPOINT] starting nginx (foreground) ..."
exec nginx -g 'daemon off;'
