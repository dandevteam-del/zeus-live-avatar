#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# [ON POD] Package ZeusMetaHuman for Linux with Pixel Streaming (headless).
#
# Runs RunUAT BuildCookRun. Works in either install mode (.ue_env from step 1):
#   - container: runs RunUAT inside Epic's UE5.4 dev image with /workspace mounted
#   - source:    runs the local RunUAT directly
#
# Output: /workspace/ZeusMetaHuman/Packaged/LinuxNoEditor/  (the runnable build)
# MUST run AFTER the MetaHuman is imported + AnimBP wired (INTERACTIVE_STEPS.md).
# ═══════════════════════════════════════════════════════════════════════════════
set -euo pipefail
WORK=/workspace
PROJ="${PROJ:-$WORK/ZeusMetaHuman}"
OUT="$PROJ/Packaged"
UPROJECT="$PROJ/ZeusMetaHuman.uproject"
source "$WORK/.ue_env"
mkdir -p "$OUT"

UAT_ARGS=(BuildCookRun
  -project="$UPROJECT"
  -noP4 -platform=Linux -clientconfig=Development
  -cook -build -stage -pak -archive -archivedirectory="$OUT"
  -nocompileeditor -utf8output
  -nullrhi=false )   # need real RHI/Vulkan for MetaHuman render

if [ "${UE_MODE:-}" = "container" ]; then
  echo "→ packaging via Epic dev image $UE_IMG …"
  docker run --rm --gpus all \
    -v "$WORK":"$WORK" -w "$WORK" \
    -e HOME=/home/ue4 \
    "$UE_IMG" \
    /home/ue4/UnrealEngine/Engine/Build/BatchFiles/RunUAT.sh "${UAT_ARGS[@]}"
else
  echo "→ packaging via source build at $UE_ROOT …"
  "$UE_ROOT/Engine/Build/BatchFiles/RunUAT.sh" "${UAT_ARGS[@]}"
fi

BIN="$OUT/LinuxNoEditor/ZeusMetaHuman.sh"
[ -f "$BIN" ] && echo "✓ packaged: $BIN" || { echo "✗ no binary at $BIN — check cook log above"; exit 1; }
