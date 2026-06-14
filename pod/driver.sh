#!/usr/bin/env bash
# Force-build the missing MetaHuman editor modules by name (detached).
set -x
ENG=/home/ue4/UnrealEngine
WEBDIR=/workspace/web
UPROJ=/workspace/ZeusAvatar/ZeusAvatar.uproject
if pgrep -f "UnrealBuildTool.*Module" >/dev/null 2>&1 || pgrep -f "Build.sh UnrealEditor.*Module" >/dev/null 2>&1; then
  echo "targeted build already running"
else
  cd "$ENG"
  nohup ./Engine/Build/BatchFiles/Linux/Build.sh UnrealEditor Linux Development \
     -Project="$UPROJ" -TargetType=Editor \
     -Module=MetaHumanCharacterEditor \
     -Module=MetaHumanCharacterMigrationEditor \
     -Module=MetaHumanDefaultEditorPipeline \
     -Module=InterchangeDNA \
     > "$WEBDIR/build2.log" 2>&1 &
  echo "launched targeted build pid $! -> /build2.log"
fi
sleep 8
echo "=== build2.log head ==="
head -25 "$WEBDIR/build2.log" 2>/dev/null
echo "driver done"
