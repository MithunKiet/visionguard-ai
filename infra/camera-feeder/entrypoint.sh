#!/bin/bash
# Feeds a looping video into MediaMTX so the demo RTSP camera stream is
# always live, without a manual `ffmpeg` command run by hand every session
# (see docs/E2E_PILOT_RUNBOOK.md). Drop a real clip at ./media/sample.mp4 —
# a factory floor / person walking clip is ideal for PPE detection testing.
# Falls back to a synthetic test pattern so the stream (and camera health
# checks) still work with zero setup.
set -u

STREAM_PATH="${CAMERA_STREAM_PATH:-factory-cam-01}"
TARGET="rtsp://mediamtx:8554/${STREAM_PATH}"
VIDEO="/media/sample.mp4"

echo "[camera-feeder] waiting for mediamtx:8554…"
until (echo > /dev/tcp/mediamtx/8554) 2>/dev/null; do
  sleep 2
done
echo "[camera-feeder] mediamtx is up."

while true; do
  if [ -f "$VIDEO" ]; then
    echo "[camera-feeder] streaming $VIDEO -> $TARGET"
    ffmpeg -re -stream_loop -1 -i "$VIDEO" -c copy -rtsp_transport tcp -f rtsp "$TARGET"
  else
    echo "[camera-feeder] no file at $VIDEO — streaming a synthetic test pattern instead."
    echo "[camera-feeder] drop a real MP4 (factory floor / people) at ./media/sample.mp4 for actual PPE detection testing."
    ffmpeg -re -stream_loop -1 -f lavfi -i "testsrc=size=1920x1080:rate=15" \
      -c:v libx264 -preset ultrafast -pix_fmt yuv420p -rtsp_transport tcp -f rtsp "$TARGET"
  fi
  echo "[camera-feeder] ffmpeg exited — restarting in 3s…"
  sleep 3
done
