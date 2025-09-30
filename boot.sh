#!/usr/bin/env bash
set -uo pipefail

log(){ echo "[boot] $*"; }
warn(){ echo "[boot][warn] $*"; }

trap 'warn "boot step failed at line ${BASH_LINENO[0]} (exit=$?)"' ERR
# ========= Environment defaults =========
: "${KEYS:=}"                        # Comma/semicolon/space separated list of stream keys
: "${BASIC_AUTH:=false}"             # true|false
: "${BASIC_AUTH_USER:=admin}"
: "${BASIC_AUTH_PASS:=admin}"
: "${BOT_TOKEN:=}"                   # Telegram bot token
: "${CHAT_ID:=}"                     # Telegram chat id

# ========= Default transcoding profile =========
: "${PROFILE_OUT_RES:=854x480}"
: "${PROFILE_FPS:=30}"
: "${PROFILE_BITRATE_KBPS:=500}"
: "${PROFILE_KEYINT_SEC:=2}"
: "${PROFILE_X264_PRESET:=veryfast}"
: "${PROFILE_X264_TUNE:=zerolatency}"
: "${PROFILE_X264_PROFILE:=baseline}"
# ===============================================

normalize_int(){
  local value="$1" default="$2"
  if [[ "$value" =~ ^[0-9]+$ ]]; then
    printf '%s' "$value"
  else
    printf '%s' "$default"
  fi
}

log "ENV KEYS=${KEYS}"
log "ENV PROFILE: ${PROFILE_OUT_RES} @ ${PROFILE_FPS}fps, ${PROFILE_BITRATE_KBPS}kbps, keyint=${PROFILE_KEYINT_SEC}s"

# Normalize KEYS -> whitespace separated tokens
KEYS_NORM="$(echo "$KEYS" | tr ',;' '  ' | xargs 2>/dev/null || true)"
KEY_COUNT=$(echo "$KEYS_NORM" | wc -w | xargs || echo 0)

BASIC_AUTH_ENABLED="false"
if [[ "${BASIC_AUTH,,}" == "true" ]]; then
  BASIC_AUTH_ENABLED="true"
fi

# Configure basic auth (writes nginx include snippet)
AUTH_SNIPPET=/etc/nginx/conf.d/location_auth.conf
mkdir -p /etc/nginx/conf.d
HASHED_PASS=""

if [[ "$BASIC_AUTH_ENABLED" == "true" ]]; then
  log "Basic auth enabled for /"
  if ! HASHED_PASS=$(openssl passwd -apr1 "$BASIC_AUTH_PASS" 2>/dev/null); then
    warn "OpenSSL failed to hash password, trying htpasswd fallback"
    HASHED_PASS=$(htpasswd -nbBC 10 "$BASIC_AUTH_USER" "$BASIC_AUTH_PASS" 2>/dev/null | cut -d: -f2- || true)
  fi
  if [[ -z "$HASHED_PASS" ]]; then
    warn "Failed to hash password; disabling basic auth"
    BASIC_AUTH_ENABLED="false"
  else
    printf "%s:%s\n" "$BASIC_AUTH_USER" "$HASHED_PASS" > /etc/nginx/.htpasswd
    cat > "$AUTH_SNIPPET" <<'NGINX'
auth_basic "Restricted";
auth_basic_user_file /etc/nginx/.htpasswd;
NGINX
  fi
fi

if [[ "$BASIC_AUTH_ENABLED" != "true" ]]; then
  log "Basic auth disabled for /"
  : > /etc/nginx/.htpasswd
  cat > "$AUTH_SNIPPET" <<'NGINX'
allow all;
NGINX
fi

# Resolve public IP (fall back to first private address)
resolve_public_ip(){
  local candidate="" url
  for url in \
    "https://api.ipify.org" \
    "https://ifconfig.me" \
    "https://ipinfo.io/ip"; do
    candidate=$(curl -fsSL --max-time 5 "$url" 2>/dev/null | tr -d '\r\n' || true)
    if [[ "$candidate" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
      printf '%s' "$candidate"
      return 0
    fi
  done
  candidate=$(ip route get 1.1.1.1 2>/dev/null | awk '/src/ {print $7; exit}')
  if [[ "$candidate" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
    printf '%s' "$candidate"
    return 0
  fi
  candidate=$(hostname -i 2>/dev/null | awk '{print $1; exit}')
  printf '%s' "${candidate:-127.0.0.1}"
}

PUBLIC_IP=$(resolve_public_ip)
STREAM_SERVER="rtmp://${PUBLIC_IP}/live"
log "Resolved public IP: ${PUBLIC_IP}"

# Prepare index.html with Video.js players
INDEX=/usr/share/nginx/html/index.html
mkdir -p /usr/share/nginx/html

cat > "$INDEX" <<'HTML'
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <title>OBS Fog Monitor</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <link href="https://unpkg.com/video.js/dist/video-js.min.css" rel="stylesheet" />
  <style>
    :root {
      color-scheme: dark;
    }
    body {
      margin: 0;
      font-family: system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;
      background: #0b0f14;
      color: #e8eef5;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }
    header {
      padding: 20px;
      background: linear-gradient(135deg,#152238,#1b283f);
      box-shadow: 0 2px 12px rgba(0,0,0,0.35);
    }
    h1 {
      margin: 0 0 6px;
      font-size: 22px;
      color: #c1d9ff;
    }
    .meta {
      font-size: 14px;
      color: #9db2d0;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit,minmax(320px,1fr));
      gap: 18px;
      padding: 24px;
      width: 100%;
      box-sizing: border-box;
      flex: 1 1 auto;
    }
    .tile {
      background: #121922;
      border: 1px solid rgba(84,123,182,0.22);
      border-radius: 14px;
      padding: 14px;
      box-shadow: 0 10px 32px rgba(7,13,25,0.35);
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .tile h2 {
      margin: 0;
      font-size: 15px;
      font-weight: 600;
      letter-spacing: 0.02em;
      color: #b9c7d9;
    }
    .video-wrap {
      position: relative;
      width: 100%;
      padding-top: 56.25%;
      border-radius: 10px;
      overflow: hidden;
      background: #000;
    }
    .video-js {
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      border-radius: 10px;
    }
    .empty-state {
      margin: auto;
      text-align: center;
      color: #6c7a8f;
      font-size: 16px;
    }
  </style>
</head>
<body>
  <header>
    <h1>OBS Fog Monitor</h1>
    <div class="meta" id="meta-info"></div>
  </header>
  <main class="grid" id="players-grid"></main>
HTML

printf '\n<script>window.STREAM_SERVER=%s;window.PLAYER_KEYS=%s;window.PROFILE_INFO=%s;</script>\n' \
  "'${STREAM_SERVER}'" \
  "$(printf '['; i=0; for k in $KEYS_NORM; do printf '%s\"%s\"' $([[ $i -gt 0 ]] && echo , || true) "$k"; i=$((i+1)); done; printf ']')" \
  "$(printf '{"resolution":"%s","fps":"%s","bitrate":"%s kbps"}' "$PROFILE_OUT_RES" "$PROFILE_FPS" "$PROFILE_BITRATE_KBPS")" \
  >> "$INDEX"

cat >> "$INDEX" <<'HTML'
  <script src="https://unpkg.com/video.js/dist/video.min.js"></script>
  <script>
    const keys = window.PLAYER_KEYS || [];
    const server = window.STREAM_SERVER || '';
    const profile = window.PROFILE_INFO || {};
    const meta = document.getElementById('meta-info');
    const grid = document.getElementById('players-grid');

    meta.textContent = keys.length
      ? `RTMP: ${server} · Потоков: ${keys.length} · Профиль: ${profile.resolution} @ ${profile.fps}fps / ${profile.bitrate}`
      : 'Ключи не заданы. Добавьте переменную окружения KEYS.';

    if (!keys.length) {
      grid.innerHTML = '<div class="empty-state">Нет активных ключей. Укажите KEYS в переменных окружения приложения.</div>';
    } else {
      keys.forEach((key, index) => {
        const tile = document.createElement('section');
        tile.className = 'tile';
        tile.innerHTML = `
          <div class="video-wrap">
            <video id="player-${index}" class="video-js vjs-default-skin" controls preload="auto" muted playsinline></video>
          </div>
          <h2>${key}</h2>
        `;
        grid.appendChild(tile);

        const player = videojs(`player-${index}`, {
          autoplay: 'muted',
          muted: true,
          controls: true,
          preload: 'auto',
          liveui: true,
        });

        const src = `/hls/${encodeURIComponent(key)}.m3u8`;
        const refresh = () => {
          player.src({ src, type: 'application/x-mpegURL' });
          player.load();
          player.play().catch(() => {});
        };

        player.on('error', () => setTimeout(refresh, 5000));
        player.on('waiting', () => setTimeout(refresh, 5000));
        player.ready(refresh);
      });
    }
  </script>
</body>
</html>
HTML

# Build OBS profile packages per key
PROFILE_BASE=/tmp/obs_profiles
rm -rf "$PROFILE_BASE"
mkdir -p "$PROFILE_BASE"

OUT_WIDTH_RAW="${PROFILE_OUT_RES%x*}"
OUT_HEIGHT_RAW="${PROFILE_OUT_RES#*x}"
OUT_WIDTH=$(normalize_int "$OUT_WIDTH_RAW" 854)
OUT_HEIGHT=$(normalize_int "$OUT_HEIGHT_RAW" 480)
FPS=$(normalize_int "$PROFILE_FPS" 30)
BITRATE=$(normalize_int "$PROFILE_BITRATE_KBPS" 500)
KEYINT=$(normalize_int "$PROFILE_KEYINT_SEC" 2)
[[ "$FPS" -gt 0 && "$KEYINT" -gt 0 ]] || { FPS=30; KEYINT=2; }
GOP=$((FPS * KEYINT))
FF_BITRATE=$((BITRATE * 5))
[[ "$FF_BITRATE" -gt 0 ]] || FF_BITRATE=$((BITRATE))
USE_AUTH=$([[ "$BASIC_AUTH_ENABLED" == "true" ]] && echo true || echo false)

PACKAGE_COUNT=0
for KEY in $KEYS_NORM; do
  SAFE_KEY="$(printf '%s' "$KEY" | tr -cd 'A-Za-z0-9._-')"
  [[ -n "$SAFE_KEY" ]] || SAFE_KEY="stream_${PACKAGE_COUNT}"
  KEY_DIR="$PROFILE_BASE/$SAFE_KEY"
  mkdir -p "$KEY_DIR"

  cat > "$KEY_DIR/basic.ini" <<EOF
[General]
Name=${SAFE_KEY}

[Output]
Mode=Advanced
FilenameFormatting=%CCYY-%MM-%DD %hh-%mm-%ss
DelayEnable=false
DelaySec=0
DelayPreserve=true
Reconnect=true
RetryDelay=2
MaxRetries=25
BindIP=default
IPFamily=IPv4+IPv6
NewSocketLoopEnable=false
LowLatencyEnable=false

[AdvOut]
Encoder=obs_x264
Bitrate=${BITRATE}
KeyframeIntervalSec=${KEYINT}
Rescale=false
TrackIndex=1
ApplyServiceSettings=false
UseRescale=false
VodTrackIndex=2
RecType=Standard
RecFilePath=C:\\Users\\obs\\Videos
RecFormat2=mkv
RecUseRescale=false
RecTracks=1
RecEncoder=none
FLVTrack=1
StreamMultiTrackAudioMixes=1
FFOutputToFile=true
FFFilePath=C:\\Users\\obs\\Videos
FFVBitrate=${FF_BITRATE}
FFVGOPSize=${GOP}
FFUseRescale=false
FFIgnoreCompat=false
FFABitrate=160
FFAudioMixes=1
Track1Bitrate=160
Track2Bitrate=160
Track3Bitrate=160
Track4Bitrate=160
Track5Bitrate=160
Track6Bitrate=160
RecSplitFileTime=15
RecSplitFileSize=2048
RecRB=false
RecRBTime=20
RecRBSize=512
AudioEncoder=ffmpeg_aac
RecAudioEncoder=ffmpeg_aac
RescaleRes=${OUT_WIDTH}x${OUT_HEIGHT}
RecRescaleRes=${OUT_WIDTH}x${OUT_HEIGHT}
RecSplitFileType=Time
FFFormat=
FFFormatMimeType=
FFRescaleRes=${OUT_WIDTH}x${OUT_HEIGHT}
FFVEncoderId=0
FFVEncoder=
FFAEncoderId=0
FFAEncoder=
RescaleFilter=3
FFExtension=mp4

[Audio]
SampleRate=48000
ChannelSetup=Stereo
MonitoringDeviceId=default
MonitoringDeviceName=Default
MeterDecayRate=23.53
PeakMeterType=0

[Video]
BaseCX=${OUT_WIDTH}
BaseCY=${OUT_HEIGHT}
OutputCX=${OUT_WIDTH}
OutputCY=${OUT_HEIGHT}
FPSType=Simple
FPSCommon=${FPS}
FPSInt=${FPS}
FPSNum=${FPS}
FPSDen=1
ScaleType=bilinear
ColorFormat=NV12
ColorSpace=709
ColorRange=Partial
SdrWhiteLevel=300
HdrNominalPeakLevel=1000
EOF

  cat > "$KEY_DIR/service.json" <<EOF
{"type":"rtmp_custom","settings":{"server":"${STREAM_SERVER}","use_auth":${USE_AUTH},"bwtest":false,"key":"${KEY}"}}
EOF

  cat > "$KEY_DIR/streamEncoder.json" <<EOF
{"bitrate":${BITRATE},"keyint_sec":${KEYINT},"preset":"${PROFILE_X264_PRESET}","profile":"${PROFILE_X264_PROFILE}","tune":"${PROFILE_X264_TUNE}","x264opts":"keyint=${GOP}:min-keyint=${GOP}:scenecut=0:rc-lookahead=0:ref=1:bframes=0:nal-hrd=cbr:aud=1"}
EOF

  {
    echo "Server: ${STREAM_SERVER}";
    echo "Stream key: ${KEY}";
    if [[ "$BASIC_AUTH_ENABLED" == "true" ]]; then
      echo "Basic-Auth: ${BASIC_AUTH_USER} / ${BASIC_AUTH_PASS}";
    fi
    echo "Profile: ${PROFILE_OUT_RES} @ ${PROFILE_FPS}fps, ${PROFILE_BITRATE_KBPS}kbps";
  } > "$KEY_DIR/README.txt"

  ZIP_PATH="$PROFILE_BASE/${SAFE_KEY}_profile.zip"
  if ! zip -j "$ZIP_PATH" "$KEY_DIR"/* >/dev/null 2>&1; then
    warn "Failed to create OBS profile package for ${KEY}"
    rm -f "$ZIP_PATH"
    continue
  fi
  PACKAGE_COUNT=$((PACKAGE_COUNT + 1))
  log "Profile package prepared for key '${KEY}' -> ${SAFE_KEY}_profile.zip"
done

# Send OBS profile packages to Telegram if configured
if [[ -n "${BOT_TOKEN}" && -n "${CHAT_ID}" && $PACKAGE_COUNT -gt 0 ]]; then
  TELEGRAM_URL="https://api.telegram.org/bot${BOT_TOKEN}/sendDocument"
  for KEY in $KEYS_NORM; do
    SAFE_KEY="$(printf '%s' "$KEY" | tr -cd 'A-Za-z0-9._-')"
    [[ -n "$SAFE_KEY" ]] || SAFE_KEY="stream"
    ZIP_PATH="$PROFILE_BASE/${SAFE_KEY}_profile.zip"
    [[ -f "$ZIP_PATH" ]] || { warn "Zip package missing for $KEY"; continue; }
    CAPTION="OBS profile: ${KEY}\nServer: ${STREAM_SERVER}"
    if [[ "$BASIC_AUTH_ENABLED" == "true" ]]; then
      CAPTION+="\nAuth: ${BASIC_AUTH_USER}/${BASIC_AUTH_PASS}"
    fi
    RESP=$(curl -s -F chat_id="${CHAT_ID}" -F caption="${CAPTION}" -F document=@"${ZIP_PATH}" "${TELEGRAM_URL}" || true)
    echo "$RESP" | grep -q '"ok":true' || warn "Telegram sendDocument failed for ${KEY}: ${RESP}"
  done
elif [[ -n "${BOT_TOKEN}" && -n "${CHAT_ID}" ]]; then
  warn "Telegram credentials provided but no keys to send profiles for"
fi

# Send OBS connection summary to Telegram (text only)
if [[ -n "${BOT_TOKEN}" && -n "${CHAT_ID}" && -n "${KEYS_NORM}" ]]; then
  text="OBS stream settings:\nURL: ${STREAM_SERVER}\n"
  for k in $KEYS_NORM; do text="${text}Key: ${k}\n"; done
  if [[ "$BASIC_AUTH_ENABLED" == "true" ]]; then
    text="${text}Auth: ${BASIC_AUTH_USER}/${BASIC_AUTH_PASS}\n"
  fi
  curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
       --data-urlencode "chat_id=${CHAT_ID}" \
       --data-urlencode "text=${text}" >/dev/null || true
  log "Sent OBS hints to Telegram"
fi

# Start nginx and stream logs to STDOUT
nginx
log "nginx started"

# Follow logs of nginx and recorder processes
touch /var/log/nginx/error.log /var/log/nginx/access.log /var/log/nginx/rtmp_access.log
shopt -s nullglob
REC_LOGS=(/var/hls_rec/*/rec.log)
shopt -u nullglob

tail -F /var/log/nginx/error.log /var/log/nginx/access.log /var/log/nginx/rtmp_access.log "${REC_LOGS[@]}" 2>/dev/null &
wait -n || true


warn(){ echo "[boot][warn] $*"; }
log(){ echo "[boot] $*"; }

trap "warn \"boot step failed at line ${BASH_LINENO[0]} (exit=$?)\"" ERR
set -uo pipefail
#!/usr/bin/env bash
# ========= Environment defaults =========
: "${KEYS:=}"                        # Comma/semicolon/space separated list of stream keys
: "${BASIC_AUTH:=false}"             # true|false
: "${BASIC_AUTH_USER:=admin}"
: "${BASIC_AUTH_PASS:=admin}"
: "${BOT_TOKEN:=}"                   # Telegram bot token
: "${CHAT_ID:=}"                     # Telegram chat id

# ========= Default transcoding profile =========
: "${PROFILE_OUT_RES:=854x480}"
: "${PROFILE_FPS:=30}"
: "${PROFILE_BITRATE_KBPS:=500}"
: "${PROFILE_KEYINT_SEC:=2}"
: "${PROFILE_X264_PRESET:=veryfast}"
: "${PROFILE_X264_TUNE:=zerolatency}"
: "${PROFILE_X264_PROFILE:=baseline}"
# ===============================================

normalize_int(){
  local value="$1" default="$2"
  if [[ "$value" =~ ^[0-9]+$ ]]; then
    printf '%s' "$value"
  else
    printf '%s' "$default"
  fi
}

log "ENV KEYS=${KEYS}"
log "ENV PROFILE: ${PROFILE_OUT_RES} @ ${PROFILE_FPS}fps, ${PROFILE_BITRATE_KBPS}kbps, keyint=${PROFILE_KEYINT_SEC}s"

# Normalize KEYS -> whitespace separated tokens
KEYS_NORM="$(echo "$KEYS" | tr ',;' '  ' | xargs 2>/dev/null || true)"
KEY_COUNT=$(echo "$KEYS_NORM" | wc -w | xargs || echo 0)

BASIC_AUTH_ENABLED="false"
if [[ "${BASIC_AUTH,,}" == "true" ]]; then
  BASIC_AUTH_ENABLED="true"
fi

# Configure basic auth (writes nginx include snippet)
AUTH_SNIPPET=/etc/nginx/conf.d/location_auth.conf
mkdir -p /etc/nginx/conf.d
HASHED_PASS=""

if [[ "$BASIC_AUTH_ENABLED" == "true" ]]; then
  log "Basic auth enabled for /"
  if ! HASHED_PASS=$(openssl passwd -apr1 "$BASIC_AUTH_PASS" 2>/dev/null); then
    warn "OpenSSL failed to hash password, trying htpasswd fallback"
    HASHED_PASS=$(htpasswd -nbBC 10 "$BASIC_AUTH_USER" "$BASIC_AUTH_PASS" 2>/dev/null | cut -d: -f2- || true)
  fi
  if [[ -z "$HASHED_PASS" ]]; then
    warn "Failed to hash password; disabling basic auth"
    BASIC_AUTH_ENABLED="false"
  else
    printf "%s:%s\n" "$BASIC_AUTH_USER" "$HASHED_PASS" > /etc/nginx/.htpasswd
    cat > "$AUTH_SNIPPET" <<'NGINX'
auth_basic "Restricted";
auth_basic_user_file /etc/nginx/.htpasswd;
NGINX
  fi
fi

if [[ "$BASIC_AUTH_ENABLED" != "true" ]]; then
  log "Basic auth disabled for /"
  : > /etc/nginx/.htpasswd
  cat > "$AUTH_SNIPPET" <<'NGINX'
allow all;
NGINX
fi

# Resolve public IP (fall back to first private address)
resolve_public_ip(){
  local candidate="" url
  for url in \
    "https://api.ipify.org" \
    "https://ifconfig.me" \
    "https://ipinfo.io/ip"; do
    candidate=$(curl -fsSL --max-time 5 "$url" 2>/dev/null | tr -d '\r\n' || true)
    if [[ "$candidate" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
      printf '%s' "$candidate"
      return 0
    fi
  done
  candidate=$(ip route get 1.1.1.1 2>/dev/null | awk '/src/ {print $7; exit}')
  if [[ "$candidate" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
    printf '%s' "$candidate"
    return 0
  fi
  candidate=$(hostname -i 2>/dev/null | awk '{print $1; exit}')
  printf '%s' "${candidate:-127.0.0.1}"
}

PUBLIC_IP=$(resolve_public_ip)
STREAM_SERVER="rtmp://${PUBLIC_IP}/live"
log "Resolved public IP: ${PUBLIC_IP}"

# Prepare index.html with Video.js players
INDEX=/usr/share/nginx/html/index.html
mkdir -p /usr/share/nginx/html

cat > "$INDEX" <<'HTML'
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <title>OBS Fog Monitor</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <link href="https://unpkg.com/video.js/dist/video-js.min.css" rel="stylesheet" />
  <style>
    :root {
      color-scheme: dark;
    }
    body {
      margin: 0;
      font-family: system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;
      background: #0b0f14;
      color: #e8eef5;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }
    header {
      padding: 20px;
      background: linear-gradient(135deg,#152238,#1b283f);
      box-shadow: 0 2px 12px rgba(0,0,0,0.35);
    }
    h1 {
      margin: 0 0 6px;
      font-size: 22px;
      color: #c1d9ff;
    }
    .meta {
      font-size: 14px;
      color: #9db2d0;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit,minmax(320px,1fr));
      gap: 18px;
      padding: 24px;
      width: 100%;
      box-sizing: border-box;
      flex: 1 1 auto;
    }
    .tile {
      background: #121922;
      border: 1px solid rgba(84,123,182,0.22);
      border-radius: 14px;
      padding: 14px;
      box-shadow: 0 10px 32px rgba(7,13,25,0.35);
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .tile h2 {
      margin: 0;
      font-size: 15px;
      font-weight: 600;
      letter-spacing: 0.02em;
      color: #b9c7d9;
    }
    .video-wrap {
      position: relative;
      width: 100%;
      padding-top: 56.25%;
      border-radius: 10px;
      overflow: hidden;
      background: #000;
    }
    .video-js {
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      border-radius: 10px;
    }
    .empty-state {
      margin: auto;
      text-align: center;
      color: #6c7a8f;
      font-size: 16px;
    }
  </style>
</head>
<body>
  <header>
    <h1>OBS Fog Monitor</h1>
    <div class="meta" id="meta-info"></div>
  </header>
  <main class="grid" id="players-grid"></main>
HTML

printf '\n<script>window.STREAM_SERVER=%s;window.PLAYER_KEYS=%s;window.PROFILE_INFO=%s;</script>\n' \
  "'${STREAM_SERVER}'" \
  "$(printf '['; i=0; for k in $KEYS_NORM; do printf '%s\"%s\"' $([[ $i -gt 0 ]] && echo , || true) "$k"; i=$((i+1)); done; printf ']')" \
  "$(printf '{"resolution":"%s","fps":"%s","bitrate":"%s kbps"}' "$PROFILE_OUT_RES" "$PROFILE_FPS" "$PROFILE_BITRATE_KBPS")" \
  >> "$INDEX"

cat >> "$INDEX" <<'HTML'
  <script src="https://unpkg.com/video.js/dist/video.min.js"></script>
  <script>
    const keys = window.PLAYER_KEYS || [];
    const server = window.STREAM_SERVER || '';
    const profile = window.PROFILE_INFO || {};
    const meta = document.getElementById('meta-info');
    const grid = document.getElementById('players-grid');

    meta.textContent = keys.length
      ? `RTMP: ${server} · Потоков: ${keys.length} · Профиль: ${profile.resolution} @ ${profile.fps}fps / ${profile.bitrate}`
      : 'Ключи не заданы. Добавьте переменную окружения KEYS.';

    if (!keys.length) {
      grid.innerHTML = '<div class="empty-state">Нет активных ключей. Укажите KEYS в переменных окружения приложения.</div>';
    } else {
      keys.forEach((key, index) => {
        const tile = document.createElement('section');
        tile.className = 'tile';
        tile.innerHTML = `
          <div class="video-wrap">
            <video id="player-${index}" class="video-js vjs-default-skin" controls preload="auto" muted playsinline></video>
          </div>
          <h2>${key}</h2>
        `;
        grid.appendChild(tile);

        const player = videojs(`player-${index}`, {
          autoplay: 'muted',
          muted: true,
          controls: true,
          preload: 'auto',
          liveui: true,
        });

        const src = `/hls/${encodeURIComponent(key)}.m3u8`;
        const refresh = () => {
          player.src({ src, type: 'application/x-mpegURL' });
          player.load();
          player.play().catch(() => {});
        };

        player.on('error', () => setTimeout(refresh, 5000));
        player.on('waiting', () => setTimeout(refresh, 5000));
        player.ready(refresh);
      });
    }
  </script>
</body>
</html>
HTML

# Build OBS profile packages per key
PROFILE_BASE=/tmp/obs_profiles
rm -rf "$PROFILE_BASE"
mkdir -p "$PROFILE_BASE"

OUT_WIDTH_RAW="${PROFILE_OUT_RES%x*}"
OUT_HEIGHT_RAW="${PROFILE_OUT_RES#*x}"
OUT_WIDTH=$(normalize_int "$OUT_WIDTH_RAW" 854)
OUT_HEIGHT=$(normalize_int "$OUT_HEIGHT_RAW" 480)
FPS=$(normalize_int "$PROFILE_FPS" 30)
BITRATE=$(normalize_int "$PROFILE_BITRATE_KBPS" 500)
KEYINT=$(normalize_int "$PROFILE_KEYINT_SEC" 2)
[[ "$FPS" -gt 0 && "$KEYINT" -gt 0 ]] || { FPS=30; KEYINT=2; }
GOP=$((FPS * KEYINT))
FF_BITRATE=$((BITRATE * 5))
[[ "$FF_BITRATE" -gt 0 ]] || FF_BITRATE=$((BITRATE))
USE_AUTH=$([[ "$BASIC_AUTH_ENABLED" == "true" ]] && echo true || echo false)

PACKAGE_COUNT=0
for KEY in $KEYS_NORM; do
  SAFE_KEY="$(printf '%s' "$KEY" | tr -cd 'A-Za-z0-9._-')"
  [[ -n "$SAFE_KEY" ]] || SAFE_KEY="stream_${PACKAGE_COUNT}"
  KEY_DIR="$PROFILE_BASE/$SAFE_KEY"
  mkdir -p "$KEY_DIR"

  cat > "$KEY_DIR/basic.ini" <<EOF
[General]
Name=${SAFE_KEY}

[Output]
Mode=Advanced
FilenameFormatting=%CCYY-%MM-%DD %hh-%mm-%ss
DelayEnable=false
DelaySec=0
DelayPreserve=true
Reconnect=true
RetryDelay=2
MaxRetries=25
BindIP=default
IPFamily=IPv4+IPv6
NewSocketLoopEnable=false
LowLatencyEnable=false

[AdvOut]
Encoder=obs_x264
Bitrate=${BITRATE}
KeyframeIntervalSec=${KEYINT}
Rescale=false
TrackIndex=1
ApplyServiceSettings=false
UseRescale=false
VodTrackIndex=2
RecType=Standard
RecFilePath=C:\\Users\\obs\\Videos
RecFormat2=mkv
RecUseRescale=false
RecTracks=1
RecEncoder=none
FLVTrack=1
StreamMultiTrackAudioMixes=1
FFOutputToFile=true
FFFilePath=C:\\Users\\obs\\Videos
FFVBitrate=${FF_BITRATE}
FFVGOPSize=${GOP}
FFUseRescale=false
FFIgnoreCompat=false
FFABitrate=160
FFAudioMixes=1
Track1Bitrate=160
Track2Bitrate=160
Track3Bitrate=160
Track4Bitrate=160
Track5Bitrate=160
Track6Bitrate=160
RecSplitFileTime=15
RecSplitFileSize=2048
RecRB=false
RecRBTime=20
RecRBSize=512
AudioEncoder=ffmpeg_aac
RecAudioEncoder=ffmpeg_aac
RescaleRes=${OUT_WIDTH}x${OUT_HEIGHT}
RecRescaleRes=${OUT_WIDTH}x${OUT_HEIGHT}
RecSplitFileType=Time
FFFormat=
FFFormatMimeType=
FFRescaleRes=${OUT_WIDTH}x${OUT_HEIGHT}
FFVEncoderId=0
FFVEncoder=
FFAEncoderId=0
FFAEncoder=
RescaleFilter=3
FFExtension=mp4

[Audio]
SampleRate=48000
ChannelSetup=Stereo
MonitoringDeviceId=default
MonitoringDeviceName=Default
MeterDecayRate=23.53
PeakMeterType=0

[Video]
BaseCX=${OUT_WIDTH}
BaseCY=${OUT_HEIGHT}
OutputCX=${OUT_WIDTH}
OutputCY=${OUT_HEIGHT}
FPSType=Simple
FPSCommon=${FPS}
FPSInt=${FPS}
FPSNum=${FPS}
FPSDen=1
ScaleType=bilinear
ColorFormat=NV12
ColorSpace=709
ColorRange=Partial
SdrWhiteLevel=300
HdrNominalPeakLevel=1000
EOF

  cat > "$KEY_DIR/service.json" <<EOF
{"type":"rtmp_custom","settings":{"server":"${STREAM_SERVER}","use_auth":${USE_AUTH},"bwtest":false,"key":"${KEY}"}}
EOF

  cat > "$KEY_DIR/streamEncoder.json" <<EOF
{"bitrate":${BITRATE},"keyint_sec":${KEYINT},"preset":"${PROFILE_X264_PRESET}","profile":"${PROFILE_X264_PROFILE}","tune":"${PROFILE_X264_TUNE}","x264opts":"keyint=${GOP}:min-keyint=${GOP}:scenecut=0:rc-lookahead=0:ref=1:bframes=0:nal-hrd=cbr:aud=1"}
EOF

  {
    echo "Server: ${STREAM_SERVER}";
    echo "Stream key: ${KEY}";
    if [[ "$BASIC_AUTH_ENABLED" == "true" ]]; then
      echo "Basic-Auth: ${BASIC_AUTH_USER} / ${BASIC_AUTH_PASS}";
    fi
    echo "Profile: ${PROFILE_OUT_RES} @ ${PROFILE_FPS}fps, ${PROFILE_BITRATE_KBPS}kbps";
  } > "$KEY_DIR/README.txt"

  ZIP_PATH="$PROFILE_BASE/${SAFE_KEY}_profile.zip"
  if ! zip -j "$ZIP_PATH" "$KEY_DIR"/* >/dev/null 2>&1; then
    warn "Failed to create OBS profile package for ${KEY}"
    rm -f "$ZIP_PATH"
    continue
  fi
  PACKAGE_COUNT=$((PACKAGE_COUNT + 1))
  log "Profile package prepared for key '${KEY}' -> ${SAFE_KEY}_profile.zip"
done

# Send OBS profile packages to Telegram if configured
if [[ -n "${BOT_TOKEN}" && -n "${CHAT_ID}" && $PACKAGE_COUNT -gt 0 ]]; then
  TELEGRAM_URL="https://api.telegram.org/bot${BOT_TOKEN}/sendDocument"
  for KEY in $KEYS_NORM; do
    SAFE_KEY="$(printf '%s' "$KEY" | tr -cd 'A-Za-z0-9._-')"
    [[ -n "$SAFE_KEY" ]] || SAFE_KEY="stream"
    ZIP_PATH="$PROFILE_BASE/${SAFE_KEY}_profile.zip"
    [[ -f "$ZIP_PATH" ]] || { warn "Zip package missing for $KEY"; continue; }
    CAPTION="OBS profile: ${KEY}\nServer: ${STREAM_SERVER}"
    if [[ "$BASIC_AUTH_ENABLED" == "true" ]]; then
      CAPTION+="\nAuth: ${BASIC_AUTH_USER}/${BASIC_AUTH_PASS}"
    fi
    RESP=$(curl -s -F chat_id="${CHAT_ID}" -F caption="${CAPTION}" -F document=@"${ZIP_PATH}" "${TELEGRAM_URL}" || true)
    echo "$RESP" | grep -q '"ok":true' || warn "Telegram sendDocument failed for ${KEY}: ${RESP}"
  done
elif [[ -n "${BOT_TOKEN}" && -n "${CHAT_ID}" ]]; then
  warn "Telegram credentials provided but no keys to send profiles for"
fi

# Send OBS connection summary to Telegram (text only)
if [[ -n "${BOT_TOKEN}" && -n "${CHAT_ID}" && -n "${KEYS_NORM}" ]]; then
  text="OBS stream settings:\nURL: ${STREAM_SERVER}\n"
  for k in $KEYS_NORM; do text="${text}Key: ${k}\n"; done
  if [[ "$BASIC_AUTH_ENABLED" == "true" ]]; then
    text="${text}Auth: ${BASIC_AUTH_USER}/${BASIC_AUTH_PASS}\n"
  fi
  curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
       --data-urlencode "chat_id=${CHAT_ID}" \
       --data-urlencode "text=${text}" >/dev/null || true
  log "Sent OBS hints to Telegram"
fi

# Start nginx and stream logs to STDOUT
nginx
log "nginx started"

# Follow logs of nginx and recorder processes
touch /var/log/nginx/error.log /var/log/nginx/access.log /var/log/nginx/rtmp_access.log
shopt -s nullglob
REC_LOGS=(/var/hls_rec/*/rec.log)
shopt -u nullglob

tail -F /var/log/nginx/error.log /var/log/nginx/access.log /var/log/nginx/rtmp_access.log "${REC_LOGS[@]}" 2>/dev/null &
wait -n || true
