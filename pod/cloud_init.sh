#!/usr/bin/env bash
# Pod startup bootstrap — runs at container start (via dockerArgs). Self-configures
# the UE MetaHuman project + a noVNC desktop so it can be driven from a browser,
# no SSH/web-terminal needed. ALL output goes to stdout → RunPod "Logs" tab.
set -x
echo "===== ZEUS CLOUD_INIT START ====="
echo "WHOAMI=$(whoami) UID=$(id -u) HOME=$HOME"
SUDO=""; if [ "$(id -u)" != "0" ]; then sudo -n true 2>/dev/null && SUDO="sudo -n"; fi
echo "SUDO_MODE='${SUDO:-none}'"

export DEBIAN_FRONTEND=noninteractive
echo "----- installing desktop + vnc packages -----"
$SUDO apt-get update -y 2>&1 | tail -3
$SUDO apt-get install -y --no-install-recommends \
    xvfb x11vnc novnc websockify openbox xterm git curl ca-certificates \
    libnss3 libxcomposite1 libxcursor1 libxi6 libxtst6 libxrandr2 libasound2 2>&1 | tail -5

WORK=/workspace
echo "----- syncing kit -----"
if [ -d "$WORK/kit/.git" ]; then (cd "$WORK/kit" && git pull -q); else git clone --depth 1 https://github.com/dandevteam-del/zeus-live-avatar "$WORK/kit"; fi
ls "$WORK/kit/pod" || { echo "KIT MISSING"; }

echo "----- locate Unreal Engine -----"
UE_EDITOR=$(ls /home/ue4/UnrealEngine/Engine/Binaries/Linux/UnrealEditor 2>/dev/null \
  || find / -maxdepth 6 -name UnrealEditor -type f 2>/dev/null | head -1)
echo "UE_EDITOR=$UE_EDITOR"

echo "----- bootstrap UE project -----"
cd "$WORK/kit/pod" && KIT="$WORK/kit" PROJ="$WORK/ZeusMetaHuman" bash 02_bootstrap_project.sh 2>&1 | tail -15

echo "----- start virtual display + noVNC -----"
export DISPLAY=:1
pkill -f "Xvfb :1" 2>/dev/null
Xvfb :1 -screen 0 1920x1080x24 +extension GLX +render -noreset > /workspace/xvfb.log 2>&1 &
sleep 3
openbox > /workspace/openbox.log 2>&1 &
x11vnc -display :1 -forever -shared -nopw -rfbport 5900 > /workspace/x11vnc.log 2>&1 &
NOVNC_DIR=$(ls -d /usr/share/novnc 2>/dev/null || echo /usr/share/novnc)
websockify --web="$NOVNC_DIR" 6080 localhost:5900 > /workspace/novnc.log 2>&1 &
sleep 3
echo "NOVNC up on :6080 (proxy: https://<pod>-6080.proxy.runpod.net/vnc.html)"

echo "----- launch UE editor in the virtual desktop -----"
if [ -n "$UE_EDITOR" ]; then
  "$UE_EDITOR" "$WORK/ZeusMetaHuman/ZeusMetaHuman.uproject" > /workspace/ue.log 2>&1 &
  echo "UE editor launching (PID $!) — first open compiles shaders, be patient"
else
  echo "!! UE editor not found — open a terminal in noVNC to investigate"
fi
echo "===== ZEUS CLOUD_INIT DONE ====="
