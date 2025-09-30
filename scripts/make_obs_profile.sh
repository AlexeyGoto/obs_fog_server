#!/usr/bin/env bash
set -euo pipefail
KEY="${1:?stream key required}"
PHOST="${2:-localhost}"
OUTDIR="/app/obs_profiles/LowVPS-RTMP-${KEY}"
mkdir -p "$OUTDIR"
cat > "$OUTDIR/basic.ini" <<EOF
[General]
Name=LowVPS-RTMP-${KEY}

[Output]
Mode=Advanced

[AdvOut]
Encoder=obs_x264
Bitrate=500
KeyframeIntervalSec=2
Rescale=false
TrackIndex=1
ApplyServiceSettings=false

[Audio]
SampleRate=48000
ChannelSetup=Stereo

[Video]
BaseCX=854
BaseCY=480
OutputCX=854
OutputCY=480
FPSType=Simple
FPSCommon=30
EOF

cat > "$OUTDIR/service.json" <<EOF
{
  "type": "rtmp_custom",
  "settings": {
    "service": "Custom",
    "server": "rtmp://${PHOST}:1935/live",
    "key": "${KEY}",
    "bwtest": false
  },
  "hotkeys": {}
}
EOF

(cd /app/obs_profiles && zip -rq "LowVPS-RTMP-${KEY}.zip" "LowVPS-RTMP-${KEY}")
echo "/app/obs_profiles/LowVPS-RTMP-${KEY}.zip"
