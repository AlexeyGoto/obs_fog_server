#!/usr/bin/env bash
set -e

# Для корректной работы exec_* в rtmp (иначе возможны проблемы в контейнере)
ulimit -n 1024 || true

# Обновляем логин/пароль, если заданы ENV ADMIN_USER/ADMIN_PASS
if [[ -n "${ADMIN_USER}" && -n "${ADMIN_PASS}" ]]; then
  echo "[entrypoint] Applying basic auth from env ADMIN_USER/ADMIN_PASS"
  htpasswd -bc /etc/nginx/htpasswd "${ADMIN_USER}" "${ADMIN_PASS}"
else
  echo "[entrypoint] Using default basic auth (admin/admin). CHANGE IT via env!"
fi

# Проверим каталоги и права (www-data должен иметь запись)
mkdir -p /tmp/hls /var/videos
chown -R www-data:www-data /tmp/hls /var/videos

echo "[entrypoint] BOT_TOKEN: ${BOT_TOKEN:+set}, CHAT_ID: ${CHAT_ID:+set}, BASE_URL: ${BASE_URL:-<not set>}"

# Старт nginx в foreground
nginx -g 'daemon off;'
