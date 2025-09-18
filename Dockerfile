# RTMP + HLS + FFmpeg в одном контейнере
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    nginx libnginx-mod-rtmp ffmpeg apache2-utils curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Конфиг Nginx (HTTP + RTMP)
COPY nginx.conf /etc/nginx/nginx.conf

# Скрипты
COPY on_stream_done.sh /app/on_stream_done.sh
COPY entrypoint.sh /entrypoint.sh

# Веб-страница
COPY index.html /usr/share/nginx/html/index.html

# Папки под HLS и итоговые видео
RUN mkdir -p /tmp/hls /var/videos \
 && chown -R www-data:www-data /tmp/hls /var/videos

# Базовый htpasswd (по умолчанию admin/admin — ОБЯЗАТЕЛЬНО сменить через ENV!)
RUN htpasswd -b -c /etc/nginx/htpasswd admin admin

# Логи в stdout/stderr контейнера
RUN ln -sf /dev/stdout /var/log/nginx/access.log \
 && ln -sf /dev/stderr /var/log/nginx/error.log

# Права на скрипты
RUN chmod +x /app/on_stream_done.sh /entrypoint.sh

# Порты
EXPOSE 80 1935

# Запускаем через entrypoint (он настроит пароль, ulimit и стартует nginx)
ENTRYPOINT ["/entrypoint.sh"]
