#!/usr/bin/env bash
set -euo pipefail

log(){ echo "[boot] $*"; }

# ========= ENV c разумными дефолтами =========
: "${KEYS:=}"                         # "pc1,pc2" или "pc1 pc2"
: "${BASIC_AUTH:=false}"              # true|false
: "${BASIC_AUTH_USER:=admin}"
: "${BASIC_AUTH_PASS:=admin}"
: "${BOT_TOKEN:=}"                    # опционально
: "${CHAT_ID:=}"                      # опционально

# Профиль — только для подсказки и сообщений
: "${PROFILE_OUT_RES:=854x480}"
: "${PROFILE_FPS:=30}"
: "${PROFILE_BITRATE_KBPS:=500}"
: "${PROFILE_KEYINT_SEC:=2}"
# ============================================

log "ENV KEYS=${KEYS}"
log "ENV PROFILE: ${PROFILE_OUT_RES} @ ${PROFILE_FPS}fps, ${PROFILE_BITRATE_KBPS}kbps, keyint=${PROFILE_KEYINT_SEC}s"

# Нормализуем KEYS -> пробелы
KEYS_NORM="$(echo "$KEYS" | tr ',;' '  ' | xargs 2>/dev/null || true)"

# Basic auth (если включён)
if [[ "${BASIC_AUTH,,}" == "true" ]]; then
  log "Basic auth enabled for /"
  printf "%s:$(openssl passwd -apr1 "%s")\n" "$BASIC_AUTH_USER" "$BASIC_AUTH_PASS" > /etc/nginx/.htpasswd
else
  # Пустой файл, чтобы nginx не ругался на отсутствие
  : > /etc/nginx/.htpasswd
fi

# Генерим index.html с плитками
INDEX=/usr/share/nginx/html/index.html
mkdir -p /usr/share/nginx/html

cat > "$INDEX" <<'HTML'
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <title>PC Monitor</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:0;padding:20px;background:#0b0f14;color:#e8eef5}
    h1{font-size:20px;margin:0 0 16px;color:#c1d9ff}
    .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px}
    .tile{background:#121922;border:1px solid #1e2a38;border-radius:14px;padding:12px}
    .title{margin:8px 4px 0;font-size:14px;color:#b9c7d9}
    video{width:100%;height:auto;background:#000;border-radius:10px;outline:none}
    .muted{font-size:12px;color:#8493a8;margin:4px}
  </style>
  <script src="https://unpkg.com/hls.js@latest"></script>
</head>
<body>
  <h1>PC Monitor (HLS)</h1>
  <div class="grid" id="grid"></div>
  <script>
    // Ключи прокидываются через window.PLAYER_KEYS (см. ниже)
    (function(){
      const keys = (window.PLAYER_KEYS || []);
      const grid = document.getElementById('grid');
      keys.forEach(key => {
        const tile = document.createElement('div');
        tile.className = 'tile';
        const v = document.createElement('video');
        v.controls = true; v.autoplay = true; v.muted = true; v.playsInline = true;
        const p = document.createElement('p'); p.className = 'title'; p.textContent = key;
        const m = document.createElement('div'); m.className='muted'; m.textContent='(включен mute)';

        const src = `/hls/${key}.m3u8`;
        if (Hls.isSupported()) {
          const hls = new Hls({lowLatencyMode:false, backBufferLength:30});
          hls.loadSource(src);
          hls.attachMedia(v);
        } else {
          v.src = src; // Safari
        }
        tile.appendChild(v); tile.appendChild(p); tile.appendChild(m);
        grid.appendChild(tile);
      });
    })();
  </script>
HTML

# Вставим массив ключей в конец index.html
printf "\n<script>window.PLAYER_KEYS=%s;</script>\n" \
  "$(printf '['; i=0; for k in $KEYS_NORM; do printf '%s\"%s\"' $([[ $i -gt 0 ]] && echo , || true) "$k"; i=$((i+1)); done; printf ']')" \
  >> "$INDEX"

log "index.html generated with $(echo "$KEYS_NORM" | wc -w) player(s)"

# Подсказка в Telegram (опционально)
if [[ -n "${BOT_TOKEN}" && -n "${CHAT_ID}" && -n "${KEYS_NORM}" ]]; then
  text="OBS настройки:\nURL: rtmp://$(hostname -i)/live\n"
  for k in $KEYS_NORM; do text="${text}Key: ${k}\n"; done
  curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
       --data-urlencode "chat_id=${CHAT_ID}" \
       --data-urlencode "text=${text}" >/dev/null || true
  log "Sent OBS hints to Telegram…"
fi

# Старт nginx (фоново) и «подвешиваем» логи в STDOUT
nginx
log "nginx started"

# гарантируем наличие логов
touch /var/log/nginx/error.log /var/log/nginx/access.log /var/log/nginx/rtmp_access.log
# можно появляющиеся rec.log любого стрима тоже тащить
tail -F /var/log/nginx/error.log /var/log/nginx/access.log /var/log/nginx/rtmp_access.log /var/hls_rec/*/rec.log 2>/dev/null &
wait -n
