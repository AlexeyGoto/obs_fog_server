FROM alfg/nginx-rtmp:latest

RUN apk add --no-cache \
    bash curl coreutils findutils zip openssl apache2-utils ffmpeg bind-tools tzdata

# Если хочешь оставить chown — используй блок ниже, иначе просто mkdir (вариант А):
RUN addgroup -S nginx || true \
 && adduser -S -G nginx nginx || true \
 && mkdir -p /var/hls /var/hls_rec /tmp/videos /usr/share/nginx/html \
 && chown -R nginx:nginx /var/hls /var/hls_rec /tmp/videos /usr/share/nginx/html

COPY nginx.conf /etc/nginx/nginx.conf
COPY boot.sh /usr/local/bin/boot.sh
COPY scripts/start_recorder.sh /usr/local/bin/start_recorder.sh
COPY scripts/stop_recorder_and_finalize.sh /usr/local/bin/stop_recorder_and_finalize.sh
RUN chmod +x /usr/local/bin/boot.sh /usr/local/bin/start_recorder.sh /usr/local/bin/stop_recorder_and_finalize.sh

ENV TZ=Europe/Amsterdam
EXPOSE 80 1935
CMD ["/usr/local/bin/boot.sh"]
