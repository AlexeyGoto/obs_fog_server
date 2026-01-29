#!/bin/sh
set -e

# Ensure writable HLS directory on bind mounts (common reason for 403/404 when files exist but unreadable)
mkdir -p /data/hls/live /data/recordings /data/videos
chmod -R 777 /data/hls /data/recordings /data/videos || true

# Start nginx
exec "$@"
