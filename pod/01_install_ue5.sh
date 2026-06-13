#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# [ON POD] Install Unreal Engine 5.4 for the headless MetaHuman build.
#
# Default: pull Epic's official UE5.4 *dev* container image (editor + RunUAT).
# Requires you to have linked GitHub↔Epic and `docker login ghcr.io` first
# (see BUILD_ON_POD.md step 0). We run the build INSIDE that image.
#
#   --source   build UE5.4 from GitHub source instead (no ghcr login; +2-3h, +150GB)
#
# Usage (on the pod):
#   export GHCR_USER=<github-user> GHCR_PAT=<github-PAT-with-read:packages>
#   bash 01_install_ue5.sh
# ═══════════════════════════════════════════════════════════════════════════════
set -euo pipefail
WORK=/workspace
UE_TAG="${UE_TAG:-dev-slim-5.4}"          # ghcr.io/epicgames/unreal-engine:<tag>
UE_IMG="ghcr.io/epicgames/unreal-engine:${UE_TAG}"
MODE="${1:-container}"

apt-get update -y && apt-get install -y --no-install-recommends \
    git git-lfs curl ca-certificates docker.io vulkan-tools libvulkan1 xvfb >/dev/null
git lfs install || true

if [ "$MODE" = "--source" ]; then
  echo "→ building UE5.4 from source (long)…"
  cd "$WORK"
  [ -d UnrealEngine ] || git clone --depth=1 -b 5.4 https://github.com/EpicGames/UnrealEngine.git
  cd UnrealEngine
  ./Setup.sh && ./GenerateProjectFiles.sh && make
  echo "UE_ROOT=$WORK/UnrealEngine" | tee "$WORK/.ue_env"
  echo "✓ source build done"
  exit 0
fi

# ─── Container path (recommended) ───────────────────────────────────────────────
: "${GHCR_USER:?set GHCR_USER (your GitHub username)}"
: "${GHCR_PAT:?set GHCR_PAT (GitHub PAT with read:packages, Epic-linked account)}"
echo "$GHCR_PAT" | docker login ghcr.io -u "$GHCR_USER" --password-stdin
echo "→ pulling $UE_IMG (large — first pull is slow)…"
docker pull "$UE_IMG"
echo "UE_IMG=$UE_IMG"        | tee  "$WORK/.ue_env"
echo "UE_MODE=container"     | tee -a "$WORK/.ue_env"
# RunUAT/UnrealEditor live at /home/ue4/UnrealEngine inside Epic's image.
echo "UE_ROOT=/home/ue4/UnrealEngine" | tee -a "$WORK/.ue_env"
echo "✓ UE5.4 dev image ready. Project work runs inside this container with"
echo "  /workspace bind-mounted (02_bootstrap_project.sh handles it)."
