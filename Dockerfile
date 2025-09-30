FROM alfg/nginx-rtmp:latest

RUN apk add --no-cache bash curl zip coreutils wget

WORKDIR /app
RUN mkdir -p /app/www /app/scripts /tmp/videos /var/hls /var/hls_rec /app/obs_profiles /app/log

# конфиг nginx
COPY nginx.conf /etc/nginx/nginx.conf

# шаблон страницы (реальный index сгенерит entrypoint)
COPY www/index.template.html /app/www/index.template.html

# скрипты
COPY scripts/entrypoint.sh /app/entrypoint.sh
COPY scripts/start_recorder.sh /app/start_recorder.sh
COPY scripts/stop_recorder_and_finalize.sh /app/stop_recorder_and_finalize.sh
COPY scripts/make_obs_profile.sh /app/make_obs_profile.sh

RUN chmod +x /app/*.sh

EXPOSE 80 1935

# Healthcheck (даём больше стартовое окно)
HEALTHCHECK --interval=15s --timeout=4s --start-period=30s --retries=5 \
  CMD wget -q -O - http://127.0.0.1/healthz || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
