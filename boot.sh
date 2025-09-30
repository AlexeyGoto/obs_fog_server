#!/usr/bin/env bash
set -euo pipefail

# ====== ENV с умолчаниями ======
: "${KEYS:=pc1}"                     # список ключей через запятую: pc1,pc2,pc3
: "${APP_BASE_URL:=}"                # внешний host/IP. Если пусто — автоопределение IP
: "${PROFILE_RES:=854x480}"          # профиль OBS: разрешение
: "${PROFILE_FPS:=30}"               # профиль OBS: FPS
: "${PROFILE_BITRATE_KBPS:=500}"     # профиль OBS: битрейт (CBR)
: "${PROFILE_SEG_TIME:=2}"           # интервал ключевых кадров в OBS (сек)
: "${BASIC_AUTH_USER:=}"             # для опционального basic auth
: "${BASIC_AUTH_PASS:=}"             # паролик

# ====== Определяем публичный адрес ======
BASE_HOST="$APP_BASE_URL"
if [ -z "$BASE_HOST" ]; then
  # пробуем ipify → OpenDNS → локальный IP
  BASE_HOST="$(curl -fsS https://api.ipify.org || true)"
  if [ -z "$BASE_HOST" ]; then
    BASE_HOST="$(dig +short myip.opendns.com @resolver1.opendns.com || true)"
  fi
  if [ -z "$BASE_HOST" ]; then
    BASE_HOST="$(hostname -I 2>/dev/null | awk '{print $1}')"
  fi
fi
RTMP_URL="rtmp://${BASE_HOST}/live"
HTTP_URL="http://${BASE_HOST}"

# ====== Basic auth по желанию ======
if [ -n "${BASIC_AUTH_USER}" ] && [ -n "${BASIC_AUTH_PASS}" ]; then
  HASH=$(openssl passwd -apr1 "$BASIC_AUTH_PASS")
  echo "${BASIC_AUTH_USER}:${HASH}" > /etc/nginx/.htpasswd
  sed -i 's/auth_basic\s\+off;/auth_basic "Restricted";/g' /etc/nginx/nginx.conf
fi

# ====== Рендер index.html с нужным числом плееров ======
IFS=',' read -ra KEYS_ARR <<< "$KEYS"
HTML="/usr/share/nginx/html/index.html"

cat > "$HTML" <<'HTML_HEAD'
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Мониторинг ПК — HLS</title>
  <link href="https://vjs.zencdn.net/8.10.0/video-js.css" rel="stylesheet" />
  <style>
    body{margin:0;font-family:system-ui,Segoe UI,Arial,sans-serif;background:#0b0e14;color:#e6edf3}
    header{padding:12px 16px;background:#111827;border-bottom:1px solid #1f2937}
    .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px;padding:12px}
    .tile{background:#111827;border:1px solid #1f2937;border-radius:16px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.25)}
    .tile h3{margin:8px 12px 0 12px;font-size:14px;font-weight:600;color:#9ca3af}
    .vwrap{padding:12px}
    .video-js{width:100%;height:0;padding-top:56.25%;background:#000;border-radius:12px}
    .note{padding:0 16px 12px;color:#9ca3af;font-size:12px}
    a{color:#93c5fd}
  </style>
</head>
<body>
<header>
  <strong>Мониторинг ПК</strong> · HLS / video.js
</header>
<div class="grid">
HTML_HEAD
HTML_TILE_START='    <div class="tile"><div class="vwrap">'
HTML_TILE_END='</div><div class="note"></div></div>'

for key in "${KEYS_ARR[@]}"; do
  key_trim="$(echo "$key" | tr -cd 'A-Za-z0-9._-')"
  cat >> "$HTML" <<HTML_TILE
${HTML_TILE_START}
  <video id="v-${key_trim}" class="video-js vjs-default-skin" controls preload="auto" muted autoplay playsinline>
    <source src="/hls/${key_trim}.m3u8" type="application/x-mpegURL">
  </video>
  <h3>ПК: ${key_trim}</h3>
${HTML_TILE_END}
HTML_TILE
done

cat >> "$HTML" <<'HTML_FOOT'
</div>
<script src="https://vjs.zencdn.net/8.10.0/video.min.js"></script>
<script>
  // автоинициализация всех плееров
  document.querySelectorAll('video.video-js').forEach(v => {
    const player = videojs(v, {liveui:true, inactivityTimeout:0});
    player.on('error', ()=>console.warn('video.js error:', player.error()));
  });
</script>
</body></html>
HTML_FOOT

# ====== Сборка и отправка профилей OBS для каждого ключа ======
send_obs_profile() {
  local key="$1"
  local zip="/tmp/OBS-Profile-${key}.zip"
  local tmpd; tmpd="$(mktemp -d)"
  local w="${PROFILE_RES%x*}" h="${PROFILE_RES#*x}"

  # basic.ini
  cat > "${tmpd}/basic.ini" <<EOF
[General]
Name=LowVPS-RTMP-${key}

[Output]
Mode=Advanced

[AdvOut]
Encoder=obs_x264
Bitrate=${PROFILE_BITRATE_KBPS}
KeyframeIntervalSec=${PROFILE_SEG_TIME}
Rescale=false
TrackIndex=1
ApplyServiceSettings=false

[Audio]
SampleRate=48000
ChannelSetup=Stereo

[Video]
BaseCX=${w}
BaseCY=${h}
OutputCX=${w}
OutputCY=${h}
FPSType=Simple
FPSCommon=${PROFILE_FPS}
EOF

  # service.json
  cat > "${tmpd}/service.json" <<EOF
{"type":"rtmp_custom","settings":{"service":"Custom","server":"${RTMP_URL}","key":"${key}","bwtest":false},"hotkeys":{}}
EOF

  (cd "$tmpd" && zip -q "$zip" basic.ini service.json)
  rm -rf "$tmpd"

  if [ -n "${BOT_TOKEN:-}" ] && [ -n "${CHAT_ID:-}" ]; then
    local caption="Профиль OBS для ПК: ${key}\nСервер: ${RTMP_URL}\nКлюч: ${key}\nВидео: ${PROFILE_RES} @ ${PROFILE_FPS}fps\nБитрейт: ${PROFILE_BITRATE_KBPS} Kbps\nKeyframe: ${PROFILE_SEG_TIME}s"
    curl -s -F chat_id="$CHAT_ID" -F caption="$caption" -F "document=@${zip}" "https://api.telegram.org/bot${BOT_TOKEN}/sendDocument" >/dev/null 2>&1 || true
    rm -f "$zip"
  fi
}

if [ -n "${BOT_TOKEN:-}" ] && [ -n "${CHAT_ID:-}" ]; then
  for key in "${KEYS_ARR[@]}"; do
    k="$(echo "$key" | tr -cd 'A-Za-z0-9._-')"
    [ -n "$k" ] && send_obs_profile "$k"
  done
fi

# ====== Запуск nginx в форграунде ======
exec nginx -g 'daemon off;'
