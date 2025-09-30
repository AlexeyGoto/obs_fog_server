FROM alfg/nginx-rtmp:latest

# Install essential packages for nginx-rtmp and helper scripts.
RUN apk add --no-cache \
    bash curl coreutils findutils zip openssl apache2-utils ffmpeg bind-tools tzdata

# Copy configuration and helper scripts into the image.
COPY nginx.conf /etc/nginx/nginx.conf
COPY boot.sh /usr/local/bin/boot.sh
COPY scripts/start_recorder.sh /usr/local/bin/start_recorder.sh
COPY scripts/stop_recorder_and_finalize.sh /usr/local/bin/stop_recorder_and_finalize.sh

# Normalize line endings and make the scripts executable.
RUN sed -i 's/\r$//' /usr/local/bin/boot.sh /usr/local/bin/start_recorder.sh /usr/local/bin/stop_recorder_and_finalize.sh \
 && chmod +x /usr/local/bin/boot.sh /usr/local/bin/start_recorder.sh /usr/local/bin/stop_recorder_and_finalize.sh

# Prepare directories for HLS output, recordings, and static assets.
RUN mkdir -p /var/hls /var/hls_rec /tmp/videos /usr/share/nginx/html

ENV TZ=Europe/Amsterdam
EXPOSE 80 1935
CMD ["/usr/local/bin/boot.sh"]
