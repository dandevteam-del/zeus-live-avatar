#!/usr/bin/env bash
# Pod startup bootstrap v2 — content-only UE project (no compile), GPU rendering via
# VirtualGL, and ALL logs mirrored into the web-served dir so they're fetchable over
# HTTPS (https://<pod>-6080.proxy.runpod.net/boot.log and /ue.log). No SSH needed.
set -x
WORK=/workspace
LOG="$WORK/boot.log"
exec > >(tee -a "$LOG") 2>&1
echo "===== ZEUS CLOUD_INIT v2 START $(date -u 2>/dev/null) ====="
echo "WHOAMI=$(whoami) UID=$(id -u) HOME=$HOME"
SUDO=""; if [ "$(id -u)" != "0" ]; then sudo -n true 2>/dev/null && SUDO="sudo -n"; fi
echo "SUDO='${SUDO:-none}'"

export DEBIAN_FRONTEND=noninteractive
$SUDO apt-get update -y 2>&1 | tail -2
# CORE desktop (proven set — must succeed so noVNC + logs come up)
$SUDO apt-get install -y --no-install-recommends \
    xvfb x11vnc novnc websockify openbox xterm git curl ca-certificates \
    libnss3 libxcomposite1 libxcursor1 libxi6 libxtst6 libxrandr2 libasound2 2>&1 | tail -3
# GPU extras (best-effort — a missing pkg must NOT abort the desktop)
$SUDO apt-get install -y --no-install-recommends virtualgl mesa-utils libvulkan1 vulkan-tools 2>&1 | tail -3 || true
# imagemagick = pod-side screenshots; xdotool/wmctrl = programmatic input into the editor
$SUDO apt-get install -y --no-install-recommends imagemagick x11-apps xdotool wmctrl 2>&1 | tail -2 || true

# ----- web-served dir we can write to (logs fetchable over HTTPS) -----
WEBDIR="$WORK/web"; mkdir -p "$WEBDIR"
cp -r /usr/share/novnc/. "$WEBDIR/" 2>/dev/null || true
touch "$WEBDIR/boot.log" "$WEBDIR/ue.log"

# ----- kit (for the ZeusAnimReceiver source we'll add later) -----
if [ -d "$WORK/kit/.git" ]; then (cd "$WORK/kit" && git pull -q); else git clone --depth 1 https://github.com/dandevteam-del/zeus-live-avatar "$WORK/kit"; fi

# ----- CONTENT-ONLY project (no Source/Modules => editor opens, nothing to compile) -----
PROJ="$WORK/ZeusAvatar"; mkdir -p "$PROJ/Content" "$PROJ/Config"
# Only generate the .uproject on FIRST boot. After that the editor may have written
# plugin-enable changes (MetaHuman etc.) into it — never clobber those on resume.
if [ ! -f "$PROJ/ZeusAvatar.uproject" ]; then
cat > "$PROJ/ZeusAvatar.uproject" <<JSON
{ "FileVersion":3, "EngineAssociation":"5.6", "Category":"",
  "Description":"Zeus Avatar (content-only; MetaHuman created in-editor)",
  "Plugins":[ {"Name":"LiveLink","Enabled":true}, {"Name":"PixelStreaming","Enabled":true},
              {"Name":"MetaHuman","Enabled":true}, {"Name":"MetaHumanCharacter","Enabled":true},
              {"Name":"MetaHumanCoreTech","Enabled":true}, {"Name":"MetaHumanLiveLink","Enabled":true},
              {"Name":"RigLogic","Enabled":true}, {"Name":"ControlRig","Enabled":true} ] }
JSON
echo "wrote fresh uproject (with MetaHuman plugins pre-enabled)"
else
echo "uproject already exists — preserving editor-made plugin changes"
fi
mkdir -p "$WORK/ddc/Local"
# Override the DDC backend graph to a plain WRITABLE filesystem cache on the volume.
# The Installed engine defaults to ZenServer (not running in container) => "no
# writable nodes" crash. This points it at /workspace/ddc instead. Also silence
# the bad-driver-version warning dialog.
cat > "$PROJ/Config/DefaultEngine.ini" <<INI
[InstalledDerivedDataBackendGraph]
MinimumDaysToKeepFile=7
Root=(Type=KeyLength, Length=120, Inner=AsyncPut)
AsyncPut=(Type=AsyncPut, Inner=Hierarchy)
Hierarchy=(Type=Hierarchical, Inner=Local)
Local=(Type=FileSystem, ReadOnly=false, Clean=false, Flush=false, PurgeTransient=true, DeleteUnused=true, UnusedFileAge=34, FoldersToClean=-1, Path="/workspace/ddc/Local")

[DerivedDataBackendGraph]
MinimumDaysToKeepFile=7
Root=(Type=KeyLength, Length=120, Inner=AsyncPut)
AsyncPut=(Type=AsyncPut, Inner=Hierarchy)
Hierarchy=(Type=Hierarchical, Inner=Local)
Local=(Type=FileSystem, ReadOnly=false, Clean=false, Flush=false, PurgeTransient=true, DeleteUnused=true, UnusedFileAge=34, FoldersToClean=-1, Path="/workspace/ddc/Local")

[SystemSettings]
r.WarningOnBadDriverVersion=0
; trim heavy rendering features -> far fewer shader permutations to compile
r.Lumen.Supported=0
r.RayTracing=0
r.Nanite.ProjectEnabled=0
r.SkinCache.CompileShaders=1
; TSR (Temporal Super Resolution) generates hundreds of FTSRRejectShadingCS
; permutations that take 40-60s EACH to compile. Use TAA instead -> those never build.
r.AntiAliasingMethod=2
r.TSR.ShadingRejection=0

[DevOptions.Shaders]
; cap shader-compile workers so 64x workers don't OOM-kill the editor (rc=137)
NumUnusedShaderCompilingThreads=58
MaxShaderJobBatchSize=8
bAllowCompilingThroughWorkers=True
bAllowAsynchronousShaderCompiling=True
INI
echo "project: $PROJ (content-only, filesystem DDC at /workspace/ddc)"

UE=$(ls /home/ue4/UnrealEngine/Engine/Binaries/Linux/UnrealEditor 2>/dev/null || find / -maxdepth 6 -name UnrealEditor -type f 2>/dev/null | head -1)
echo "UE_EDITOR=$UE"

# ----- virtual desktop -----
export DISPLAY=:1
pkill -f "Xvfb :1" 2>/dev/null
Xvfb :1 -screen 0 1920x1080x24 +extension GLX +render -noreset > "$WORK/xvfb.log" 2>&1 &
sleep 3
openbox > "$WORK/openbox.log" 2>&1 &
x11vnc -display :1 -forever -shared -nopw -rfbport 5900 > "$WORK/x11vnc.log" 2>&1 &
websockify --web="$WEBDIR" 6080 localhost:5900 > "$WORK/novnc.log" 2>&1 &
sleep 2

echo "=== GPU CHECK ==="; nvidia-smi -L 2>&1 | head -2
echo "NVIDIA_DRIVER_CAPABILITIES=${NVIDIA_DRIVER_CAPABILITIES:-<unset>}"
echo "=== nvidia GLX/Vulkan libs ==="; ls -la /usr/lib/x86_64-linux-gnu/libGLX_nvidia.so* /usr/local/nvidia/lib64/libGLX_nvidia.so* 2>&1 | head
echo "=== existing vulkan ICDs ==="; ls -la /usr/share/vulkan/icd.d/ 2>&1
# Ensure the NVIDIA Vulkan ICD is registered so Vulkan can see the GPU.
NVLIB=$(ls /usr/lib/x86_64-linux-gnu/libGLX_nvidia.so.0 /usr/local/nvidia/lib64/libGLX_nvidia.so.0 2>/dev/null | head -1)
if [ -n "$NVLIB" ]; then
  $SUDO mkdir -p /usr/share/vulkan/icd.d
  echo "{\"file_format_version\":\"1.0.0\",\"ICD\":{\"library_path\":\"$NVLIB\",\"api_version\":\"1.3.277\"}}" | $SUDO tee /usr/share/vulkan/icd.d/nvidia_icd.json >/dev/null
  export VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/nvidia_icd.json
  echo "wrote nvidia ICD -> $NVLIB"
else
  echo "!! libGLX_nvidia.so.0 NOT mounted — needs NVIDIA_DRIVER_CAPABILITIES=all at deploy"
fi
echo "=== vulkaninfo after ICD ==="; vulkaninfo --summary 2>&1 | grep -iE "deviceName|driverName|apiVersion|GPU" | head -6

# ----- launch UE editor (Vulkan on the GPU) -----
# Installed engine's DDC (shader cache) location is read-only in the container, so
# use a writable cache on the volume + memory fallback, and suppress the driver
# warning so it doesn't block startup. Relaunch loop so a crash doesn't leave a
# black desktop (and the crash reporter is killed each time).
mkdir -p "$WORK/ddc"
echo "----- launching UE editor (loop) -----"
if [ -n "$UE" ]; then
  ( while true; do
      pkill -f CrashReportClient 2>/dev/null
      env "VK_ICD_FILENAMES=${VK_ICD_FILENAMES:-}" \
          "$UE" "$PROJ/ZeusAvatar.uproject" \
          -vulkan -nosplash -stdout -NoVerifyGC -unattended -nopause \
          "-ini:Engine:[DevOptions.Shaders]:NumUnusedShaderCompilingThreads=16,[DevOptions.Shaders]:MaxShaderJobBatchSize=6" \
          -corelimit=24 \
          >> "$WORK/ue.log" 2>&1
      echo "[loop] editor exited rc=$? — relaunching in 8s" >> "$WORK/ue.log"
      sleep 8
    done ) &
  echo "launched editor loop (pid $!)"
else
  echo "!! UE editor not found"
fi

# ----- keep logs fresh in the web dir for remote viewing -----
( while true; do cp "$WORK/ue.log" "$WEBDIR/ue.log" 2>/dev/null; cp "$LOG" "$WEBDIR/boot.log" 2>/dev/null; sleep 8; done ) &
# ----- pod-side screenshot of the editor -> web dir (fetchable at /screen.png) -----
( while true; do
    DISPLAY=:1 import -window root "$WEBDIR/screen.next.png" 2>/dev/null \
      && mv "$WEBDIR/screen.next.png" "$WEBDIR/screen.png" 2>/dev/null
    sleep 4
  done ) &
echo "screenshotter -> $WEBDIR/screen.png (HTTPS: /screen.png)"

# ----- git-driven command runner: pull the kit, run pod/driver.sh when it changes -----
# Lets the operator drive the editor server-side (xdotool) by pushing driver.sh to the
# repo — no SSH, no stop/resume per iteration. Output + a fresh shot land in the web dir.
export DISPLAY=:1
( LAST=""; while true; do
    git -C "$WORK/kit" pull -q 2>/dev/null
    DRV="$WORK/kit/pod/driver.sh"
    if [ -f "$DRV" ]; then
      H=$(md5sum "$DRV" 2>/dev/null | cut -d' ' -f1)
      if [ "$H" != "$LAST" ]; then
        LAST="$H"
        echo "===== driver.sh run $(date -u 2>/dev/null) (md5 $H) =====" > "$WEBDIR/driver.out"
        DISPLAY=:1 bash "$DRV" >> "$WEBDIR/driver.out" 2>&1
        echo "----- driver.sh done rc=$? -----" >> "$WEBDIR/driver.out"
        DISPLAY=:1 import -window root "$WEBDIR/screen.png" 2>/dev/null
      fi
    fi
    sleep 12
  done ) &
echo "driver-runner watching kit/pod/driver.sh (HTTPS: /driver.out)"
echo "===== CLOUD_INIT v2 DONE — logs at /boot.log and /ue.log on :6080 ====="
sleep infinity
