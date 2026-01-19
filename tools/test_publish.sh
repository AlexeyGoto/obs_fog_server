#!/usr/bin/env bash
set -euo pipefail

if [ $# -ne 2 ]; then
  echo "Usage: $0 <server_host> <stream_key>"
  echo "Example: $0 127.0.0.1 pc-abc123"
  exit 1
fi

HOST="$1"
KEY="$2"

ffmpeg -re \
  -f lavfi -i testsrc=size=1280x720:rate=30 \
  -f lavfi -i sine=frequency=1000:sample_rate=44100 \
  -c:v libx264 -preset veryfast -tune zerolatency -g 60 -keyint_min 60 \
  -c:a aac -b:a 128k \
  -f flv "rtmp://${HOST}/live/${KEY}"
