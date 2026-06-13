#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# Provision a RunPod GPU pod for the Zeus MetaHuman Unreal build.
# Creates an on-demand GPU pod (default A6000 48GB) with a large container disk +
# a persistent network volume, exposes the pixel-streaming / service ports, and
# prints the SSH + WebRTC connection details.
#
# Reads RUNPOD_API_KEY from ~/clawd/zeus/.env. Bills hourly from creation — STOP
# the pod when idle (printed at the end).
#
# Usage:
#   ./provision_pod.sh                       # A6000, new 100GB volume, US-IL-1
#   GPU="NVIDIA GeForce RTX 4090" ./provision_pod.sh
#   VOLUME_ID=xxxx ./provision_pod.sh        # reuse an existing network volume
# ═══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

ENV_FILE="${ENV_FILE:-$HOME/clawd/zeus/.env}"
API="https://api.runpod.io/graphql"
GPU="${GPU:-NVIDIA RTX A6000}"        # 48GB; or "NVIDIA GeForce RTX 4090" (24GB)
DC="${DC:-US-IL-1}"                   # must match the network volume's datacenter
VOL_GB="${VOL_GB:-100}"
CONTAINER_GB="${CONTAINER_GB:-120}"   # UE dev image + cooked build are large
NAME="${NAME:-zeus-metahuman}"
# UE5.4 official dev image (needs ghcr.io login on the pod — see 01_install_ue5.sh).
# We boot a plain CUDA box and pull UE inside it, so the pod image stays generic:
IMAGE="${IMAGE:-runpod/base:0.6.2-cuda12.4.1-ubuntu22.04}"

key() { grep -E '^RUNPOD_API_KEY=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"'"'"' '\'' ' ; }
K="$(key)"; [ -n "$K" ] || { echo "no RUNPOD_API_KEY in $ENV_FILE"; exit 1; }

gql() { curl -s -X POST "$API" -H "Authorization: Bearer $K" \
        -H "Content-Type: application/json" -d "$1"; }

# ─── 1. Network volume (reuse or create) ────────────────────────────────────────
if [ -z "${VOLUME_ID:-}" ]; then
  echo "→ creating ${VOL_GB}GB network volume in $DC ..."
  R=$(gql "{\"query\":\"mutation{createNetworkVolume(input:{name:\\\"$NAME-vol\\\",size:$VOL_GB,dataCenterId:\\\"$DC\\\"}){id name size}}\"}")
  echo "  $R"
  VOLUME_ID=$(echo "$R" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('data',{}).get('createNetworkVolume',{}).get('id',''))" 2>/dev/null || true)
  [ -n "$VOLUME_ID" ] || { echo "✗ volume create failed — create one in the console (Storage→Network Volume, $VOL_GB GB, $DC) and re-run with VOLUME_ID=…"; exit 1; }
fi
echo "✓ network volume: $VOLUME_ID"

# ─── 2. Pod (on-demand GPU) ─────────────────────────────────────────────────────
# Ports: 22/tcp ssh · 80/http signaling · 8888/tcp WebRTC · 8000/8001/8003 services
PORTS="22/tcp,80/http,8888/tcp,8000/http,8001/http,8003/http"
echo "→ deploying $GPU pod '$NAME' (disk ${CONTAINER_GB}GB, vol $VOLUME_ID @ /workspace) ..."
Q=$(cat <<JSON
{"query":"mutation{podFindAndDeployOnDemand(input:{cloudType:SECURE,gpuCount:1,gpuTypeId:\"$GPU\",name:\"$NAME\",imageName:\"$IMAGE\",containerDiskInGb:$CONTAINER_GB,volumeMountPath:\"/workspace\",networkVolumeId:\"$VOLUME_ID\",ports:\"$PORTS\",startSsh:true}){id imageName machineId desiredStatus}}"}
JSON
)
R=$(gql "$Q")
echo "  $R"
POD_ID=$(echo "$R" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('data',{}).get('podFindAndDeployOnDemand',{}).get('id',''))" 2>/dev/null || true)
[ -n "$POD_ID" ] || { echo "✗ pod deploy failed (likely no $GPU capacity in $DC — try GPU='NVIDIA GeForce RTX 4090' or another DC)."; exit 1; }

echo ""
echo "✓ POD: $POD_ID"
echo ""
echo "Next:"
echo "  • SSH:  runpodctl get pod $POD_ID   (grab the public ip:port)"
echo "  • On pod:  bash 01_install_ue5.sh   then  02_…  03_…  04_…"
echo "  • Pixel-stream viewer: http://<pod-ip>:<80-mapped-port>/"
echo ""
echo "⚠ BILLING IS RUNNING. Stop when idle:"
echo "    runpodctl stop pod $POD_ID      # or the Pods tab → Stop"
echo "    runpodctl remove pod $POD_ID    # delete entirely (volume persists)"
