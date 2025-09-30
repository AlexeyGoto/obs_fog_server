FROM ghcr.io/alfg/nginx-rtmp:latest

# Базовый набор утилит
RUN apk add --no-cache bash curl coreutils findutils zip openssl apache2-utils ffmpeg

# Конфиг nginx и веб-корень
COPY nginx.conf /etc/nginx/nginx.conf

# Скрипты и веб
COPY boot.sh /usr/local/bin/boot.sh
COPY scripts/start_recorder.sh /usr/local/bin/start_recorder.sh
COPY scripts/stop_recorder_and_finalize.sh /usr/local/bin/stop_recorder_and_finalize.sh
RUN chmod +x /usr/local/bin/boot.sh /usr/local/bin/start_recorder.sh /usr/local/bin/stop_recorder_and_finalize.sh

# Папки под HLS
RUN mkdir -p /var/hls /var/hls_rec /tmp/videos /usr/share/nginx/html \
 && chown -R nginx:nginx /var/hls /var/hls_rec /tmp/videos /usr/share/nginx/html

ENV TZ=Europe/Moscow

EXPOSE 80 1935
CMD ["/usr/local/bin/boot.sh"]
