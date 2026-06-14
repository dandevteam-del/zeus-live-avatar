#!/usr/bin/env bash
# Kick off (detached) a compile of the missing MetaHuman editor modules.
set -x
ENG=/home/ue4/UnrealEngine
WEBDIR=/workspace/web
UPROJ=/workspace/ZeusAvatar/ZeusAvatar.uproject
echo "=== is this an Installed (non-compilable) build? ==="
ls -la "$ENG/Engine/Build/InstalledBuild.txt" 2>&1 | head -1
echo "=== launch build (detached) if not already running ==="
if pgrep -f "Build.sh UnrealEditor" >/dev/null 2>&1 || pgrep -f "dotnet.*UnrealBuildTool" >/dev/null 2>&1; then
  echo "build already running"
else
  cd "$ENG"
  nohup ./Engine/Build/BatchFiles/Linux/Build.sh UnrealEditor Linux Development \
     -Project="$UPROJ" -TargetType=Editor \
     > "$WEBDIR/build.log" 2>&1 &
  echo "launched build pid $! -> /build.log"
fi
sleep 6
echo "=== build.log head ==="
head -30 "$WEBDIR/build.log" 2>/dev/null
echo "driver done"
