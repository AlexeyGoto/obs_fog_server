#!/usr/bin/env bash
set -Eeuo pipefail
trap 'echo "[boot] ERROR on line $LINENO: $BASH_COMMAND" >&2' ERR

log(){ echo "[boot] $*"; }

# ===== ENV =====
: "${KEYS:=pc1}"                     # через запятую
: "${APP_BASE_URL:=}"                # если пусто — автоопределим
: "${PROFILE_RES:=854x480}"
: "${PROFILE_FPS:=30}"
: "${PROFILE_BITRATE_KBPS:=500}"
: "${PROFILE_SEG_TIME:=5}"           # должен совпадать с REC_SEG_TIME
: "${BASIC_AUTH_USER:=}"
: "${BASIC_AUTH_PASS:=}"

log "ENV KEYS=$KEYS"
log "ENV APP_BASE_URL=${APP_BASE_URL:-<auto>}"
log "ENV PROFILE: ${PROFILE_RES} @ ${PROFILE_FPS}fps, ${PROFILE_BITRATE_KBPS}kbps, keyint=${PROFILE_SEG_TIME}s"

# ===== внешний адрес =====
BASE_HOST="$APP_BASE_URL"
if [ -z "$BASE_HOST" ]; then
  BASE_HOST="$(curl -fsS https://api.ipify.org || true)"
  [ -z "$BASE_HOST" ] && BASE_HOST="$(dig +short myip.opendns.com @resolver1.opendns.com || true)"
  [ -z "$BASE_HOST" ] && BASE_HOST="$(hostname -I 2>/dev/null | awk '{print $1}')"
fi
RTMP_URL="rtmp://${BASE_HOST}/live"
HTTP_URL="http://${BASE_HOST}"
log "Resolved BASE_HOST=$BASE_HOST"

# ===== basic auth (опционально) =====
if [ -n "$BASIC_AUTH_USER" ] && [ -n "$BASIC_AUTH_PASS" ]; then
  HASH=$(openssl passwd -apr1 "$BASIC_AUTH_PASS")
  echo "${BASIC_AUTH_USER}:${HASH}" > /etc/nginx/.htpasswd
  # включаем auth_basic (строка была 'off')
  sed -i 's/auth_basic\s\+off;/auth_basic "Restricted";/g' /etc/nginx/nginx.conf
  log "Basic auth enabled for /"
fi

# ===== index.html =====
IFS=',' read -ra KEYS_ARR <<< "$KEYS"
HTML="/usr/share/nginx/html/index.html"
{
  cat <<'HEAD'
<!doctype html><html lang="ru"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Мониторинг ПК — HLS</title>
<link href="https://vjs.zencdn.net/8.10.0/video-js.css" rel="stylesheet"/>
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
</style></head><body>
<header><strong>Мониторинг ПК</strong> · HLS / video.js · <span id="host"></span></header>
<div class="grid">
HEAD
  for key in "${KEYS_ARR[@]}"; do
    safe=$(echo "$key" | tr -cd 'A-Za-z0-9._-')
    cat <<TILE
<div class="tile">
  <div class="vwrap">
    <video id="v-${safe}" class="video-js vjs-default-skin" controls preload="auto" muted autoplay playsinline>
      <source src="/hls/${safe}.m3u8" type="application/x-mpegURL">
    </video>
  </div>
  <h3>ПК: ${safe}</h3>
  <div class="note">RTMP: ${RTMP_URL}/${safe}<br>HLS: /hls/${safe}.m3u8</div>
</div>
TILE
  done
  cat <<'FOOT'
</div>
<script src="https://vjs.zencdn.net/8.10.0/video.min.js"></script>
<script>
document.getElementById('host').textContent = location.origin;
document.querySelectorAll('video.video-js').forEach(v=>{
  const p=videojs(v,{liveui:true,inactivityTimeout:0});
  p.on('error',()=>console.warn('video.js error:',p.error()));
});
</script>
</body></html>
FOOT
} > "$HTML"
log "index.html generated with ${#KEYS_ARR[@]} player(s)"

# ===== отправка OBS-профилей (если заданы BOT_TOKEN/CHAT_ID) =====
if [ -n "${BOT_TOKEN:-}" ] && [ -n "${CHAT_ID:-}" ]; then
  log "Sending OBS profiles to Telegram…"
  for key in "${KEYS_ARR[@]}"; do
    k="$(echo "$key" | tr -cd 'A-Za-z0-9._-')"
    tmpd="$(mktemp -d)"; zipf="/tmp/OBS-Profile-${k}.zip"
    w="${PROFILE_RES%x*}"; h="${PROFILE_RES#*x}"
    cat > "${tmpd}/basic.ini" <<EOF
[General]
Name=LowVPS-RTMP-${k}
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
    echo "{\"type\":\"rtmp_custom\",\"settings\":{\"service\":\"Custom\",\"server\":\"${RTMP_URL}\",\"key\":\"${k}\",\"bwtest\":false},\"hotkeys\":{}}" > "${tmpd}/service.json"
    (cd "$tmpd" && zip -q "$zipf" basic.ini service.json)
    caption="Профиль OBS: ${k}\nСервер: ${RTMP_URL}\nКлюч: ${k}\nВидео: ${PROFILE_RES} @ ${PROFILE_FPS}fps\nБитрейт: ${PROFILE_BITRATE_KBPS} Kbps\nKeyframe: ${PROFILE_SEG_TIME}s"
    curl -s -F chat_id="$CHAT_ID" -F caption="$caption" -F "document=@${zipf}" "https://api.telegram.org/bot${BOT_TOKEN}/sendDocument" >/dev/null 2>&1 || true
    rm -rf "$tmpd" "$zipf"
  done
else
  log "BOT_TOKEN/CHAT_ID not set — skipping OBS profile send"
fi

# ===== тест/старт nginx =====
nginx -t
log "Starting nginx…"
exec nginx -g 'daemon off;'
