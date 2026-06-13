#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# [ON POD — Path A] Bring up a remote GUI so you can run the UE editor once to do
# the Epic login + Quixel Bridge MetaHuman import, then save into the project.
#
# Starts a virtual display (Xvfb) + VNC + noVNC web client, then launches the UE5.4
# editor on the bootstrapped project. Open the printed noVNC URL in your browser,
# sign into Epic + Quixel Bridge, import "ZeusAgent" into Content/MetaHumans/,
# wire the Face_AnimBP LiveLink subject "ZeusAvatar" (see INTERACTIVE_STEPS.md),
# Save All, then close. After that: 03_package_pixelstreaming.sh.
#
# Ports to expose on the pod: 6080 (noVNC web), 5900 (raw VNC).
# ═══════════════════════════════════════════════════════════════════════════════
set -uo pipefail
WORK=/workspace
PROJ="${PROJ:-$WORK/ZeusMetaHuman}"
source "$WORK/.ue_env"
export DISPLAY=:1

apt-get update -y && apt-get install -y --no-install-recommends \
    xvfb x11vnc novnc websockify openbox xterm >/dev/null 2>&1 || true

pkill -f "Xvfb :1" 2>/dev/null || true
Xvfb :1 -screen 0 1920x1080x24 +extension GLX +render -noreset >/tmp/xvfb.log 2>&1 &
sleep 2
openbox >/tmp/openbox.log 2>&1 &
x11vnc -display :1 -forever -shared -nopw -rfbport 5900 >/tmp/x11vnc.log 2>&1 &
websockify --web=/usr/share/novnc 6080 localhost:5900 >/tmp/novnc.log 2>&1 &
sleep 2

echo "→ launching UE5.4 editor on $PROJ (give it a minute)…"
if [ "${UE_MODE:-}" = "container" ]; then
  docker run -d --rm --gpus all --network host -e DISPLAY=:1 \
    -v /tmp/.X11-unix:/tmp/.X11-unix -v "$WORK":"$WORK" -e HOME=/home/ue4 \
    "$UE_IMG" \
    /home/ue4/UnrealEngine/Engine/Binaries/Linux/UnrealEditor "$PROJ/ZeusMetaHuman.uproject"
else
  "$UE_ROOT/Engine/Binaries/Linux/UnrealEditor" "$PROJ/ZeusMetaHuman.uproject" >/tmp/ue.log 2>&1 &
fi

echo ""
echo "✓ Remote desktop up. In your browser open:"
echo "    http://<pod-public-ip>:<mapped-6080>/vnc.html   (noVNC, no password)"
echo "  Then in the UE editor:"
echo "    1. Window → Quixel Bridge → sign into Epic → My MetaHumans → ZeusAgent → Add"
echo "    2. Wire Face_AnimBP LiveLink subject 'ZeusAvatar' (INTERACTIVE_STEPS.md)"
echo "    3. Drop BP_ZeusAgent into the Avatar map, Save All, close the editor."
echo "  Next:  bash 03_package_pixelstreaming.sh"
