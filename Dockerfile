# База с уже установленным nginx+rtmp и ffmpeg (Docker Hub)
FROM alfg/nginx-rtmp:latest

# Утилиты
RUN apk add --no-cache bash curl zip coreutils

# Каталоги приложения
WORKDIR /app
RUN mkdir -p /app/www /app/scripts /tmp/videos /var/hls /var/hls_rec /app/obs_profiles

# Конфиг nginx
COPY nginx.conf /etc/nginx/nginx.conf

# Шаблон страницы
COPY www/index.template.html /app/www/index.template.html

# Скрипты
COPY scripts/entrypoint.sh /app/entrypoint.sh
COPY scripts/start_recorder.sh /app/start_recorder.sh
COPY scripts/stop_recorder_and_finalize.sh /app/stop_recorder_and_finalize.sh
COPY scripts/make_obs_profile.sh /app/make_obs_profile.sh

# Права (без chown nginx:nginx — пользователя может не быть)
RUN chmod +x /app/*.sh

EXPOSE 80 1935
ENTRYPOINT ["/app/entrypoint.sh"]
