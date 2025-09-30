FROM alfg/nginx-rtmp:latest

# Утилиты: ffmpeg (склейка/запись), zip (профили OBS), curl (TG/IP), bind-tools (dig), tzdata
RUN apk add --no-cache \
    bash curl coreutils findutils zip openssl apache2-utils ffmpeg bind-tools tzdata

# Конфиг/скрипты
COPY nginx.conf /etc/nginx/nginx.conf
COPY boot.sh /usr/local/bin/boot.sh
COPY scripts/start_recorder.sh /usr/local/bin/start_recorder.sh
COPY scripts/stop_recorder_and_finalize.sh /usr/local/bin/stop_recorder_and_finalize.sh

# Нормализуем окончания строк (на случай CRLF из Windows) и права
RUN sed -i 's/\r$//' /usr/local/bin/boot.sh /usr/local/bin/start_recorder.sh /usr/local/bin/stop_recorder_and_finalize.sh \
 && chmod +x /usr/local/bin/boot.sh /usr/local/bin/start_recorder.sh /usr/local/bin/stop_recorder_and_finalize.sh

# Директории
RUN mkdir -p /var/hls /var/hls_rec /tmp/videos /usr/share/nginx/html

ENV TZ=Europe/Amsterdam
EXPOSE 80 1935
CMD ["/usr/local/bin/boot.sh"]
