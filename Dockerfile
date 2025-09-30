# Dockerfile (исправленный)
FROM alfg/nginx-rtmp:latest

# понадобятся утилиты
RUN apk add --no-cache bash curl zip coreutils

WORKDIR /app
RUN mkdir -p /app/www /app/scripts /tmp/videos /var/hls /var/hls_rec /app/obs_profiles

COPY nginx.conf /etc/nginx/nginx.conf
COPY www/index.template.html /app/www/index.template.html

COPY scripts/entrypoint.sh /app/entrypoint.sh
COPY scripts/start_recorder.sh /app/start_recorder.sh
COPY scripts/stop_recorder_and_finalize.sh /app/stop_recorder_and_finalize.sh
COPY scripts/make_obs_profile.sh /app/make_obs_profile.sh

RUN chmod +x /app/*.sh && \
    chown -R nginx:nginx /var/hls /var/hls_rec /tmp/videos /app/obs_profiles

EXPOSE 80 1935
ENTRYPOINT ["/app/entrypoint.sh"]
