#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# [ON POD] Run the live avatar: Pixel Streaming signaling + headless UE build +
# the backend services (STT/TTS/gateway/a2f-bridge). View in a browser at
# http://<pod-ip>:<80-mapped-port>/  then capture into OBS / Zoom.
#
#   1. brings up the Dockerized services (../scripts/start_all.sh)
#   2. starts the Pixel Streaming signaling server (Epic's infra, node)
#   3. launches the packaged UE build headless (-RenderOffscreen) → signaling
#   The ZeusAnimReceiver plugin connects to ws://localhost:8003/ws_anim itself.
# ═══════════════════════════════════════════════════════════════════════════════
set -euo pipefail
WORK=/workspace
PROJ="${PROJ:-$WORK/ZeusMetaHuman}"
KIT="${KIT:-/workspace/kit}"
BIN="$PROJ/Packaged/LinuxNoEditor/ZeusMetaHuman.sh"
SIGNAL_PORT="${SIGNAL_PORT:-80}"
STREAM_PORT="${STREAM_PORT:-8888}"
[ -f "$BIN" ] || { echo "✗ packaged build missing — run 03_package_pixelstreaming.sh"; exit 1; }

# 1. backend services (Redis/STT/TTS/gateway/a2f-bridge/console)
echo "→ starting backend services…"
( cd "$KIT" && ./scripts/start_all.sh ) || echo "! services start reported issues — check 'docker compose logs'"

# 2. Pixel Streaming signaling server (clone Epic's infra once)
PSI="$WORK/PixelStreamingInfrastructure"
if [ ! -d "$PSI" ]; then
  git clone --depth=1 -b UE5.4 https://github.com/EpicGamesExt/PixelStreamingInfrastructure.git "$PSI"
fi
( cd "$PSI/SignallingWebServer/platform_scripts/bash" && ./setup.sh && \
  HTTP_PORT="$SIGNAL_PORT" STREAMER_PORT="$STREAM_PORT" ./start.sh --publicIp 0.0.0.0 ) &
SIG_PID=$!
sleep 8

# 3. headless UE build → connects to the signaling server
echo "→ launching headless MetaHuman render…"
"$BIN" \
  -RenderOffscreen -ForceRes -ResX=1920 -ResY=1080 \
  -PixelStreamingURL="ws://localhost:$STREAM_PORT" \
  -Windowed -Unattended -StdOut \
  -PixelStreamingEncoderCodec=H264 &
UE_PID=$!

echo ""
echo "✓ live. Open:  http://<pod-public-ip>:<mapped-$SIGNAL_PORT>/"
echo "  a2f-bridge ws: ws://localhost:8003/ws_anim  (plugin auto-connects)"
echo "  stop:  kill $UE_PID $SIG_PID ; (cd $KIT && ./scripts/stop_all.sh)"
echo "  ⚠ then STOP THE POD to halt billing."
wait $UE_PID
