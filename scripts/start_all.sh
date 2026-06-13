#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# Zeus Live Avatar — Start All Services
# Opulent Bots LLC — All rights reserved
#
# Starts all Zeus Live Avatar Docker services and verifies health.
#
# Usage:
#   chmod +x scripts/start_all.sh
#   ./scripts/start_all.sh
#   ./scripts/start_all.sh --no-gpu    # skip GPU check (CPU-only mode)
#   ./scripts/start_all.sh --rebuild   # force rebuild all images
# ═══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

# ─── Color helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

ok()   { echo -e "  ${GREEN}✓${NC} $*"; }
fail() { echo -e "  ${RED}✗${NC} $*"; }
warn() { echo -e "  ${YELLOW}!${NC} $*"; }
info() { echo -e "  ${CYAN}→${NC} $*"; }
header() { echo -e "\n${BOLD}═══ $* ═══${NC}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="${PROJECT_ROOT}/infra/docker-compose.yml"

SKIP_GPU=false
REBUILD=false

for arg in "$@"; do
    case "$arg" in
        --no-gpu)  SKIP_GPU=true ;;
        --rebuild) REBUILD=true ;;
    esac
done

header "Zeus Live Avatar — Starting Services"
echo ""
info "Project: ${PROJECT_ROOT}"
info "Compose: ${COMPOSE_FILE}"
echo ""

# ─── 1. Check .env ───────────────────────────────────────────────────────────
header "Environment"
if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    ok ".env file found"
else
    warn ".env not found — copying from .env.example"
    if [[ -f "${PROJECT_ROOT}/.env.example" ]]; then
        cp "${PROJECT_ROOT}/.env.example" "${PROJECT_ROOT}/.env"
        ok "Copied .env.example -> .env"
        warn "Edit .env with your settings before production use!"
    else
        fail ".env.example not found. Cannot continue."
        exit 1
    fi
fi

# ─── 2. Check GPU ────────────────────────────────────────────────────────────
header "GPU Check"
if $SKIP_GPU; then
    warn "GPU check skipped (--no-gpu flag). Services requiring GPU may fail."
else
    if command -v nvidia-smi &>/dev/null; then
        GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
        GPU_MEM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader 2>/dev/null | head -1)
        GPU_UTIL=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader 2>/dev/null | head -1)
        ok "GPU: ${GPU_NAME} (${GPU_MEM}, utilization: ${GPU_UTIL})"
    else
        fail "nvidia-smi not found. GPU services will not work."
        echo ""
        info "Options:"
        info "  1. Install NVIDIA drivers: ./scripts/setup_gpu_ubuntu.sh"
        info "  2. Run in CPU-only mode:   ./scripts/start_all.sh --no-gpu"
        exit 1
    fi
fi

# ─── 3. Check Docker ─────────────────────────────────────────────────────────
header "Docker"
if ! command -v docker &>/dev/null; then
    fail "Docker not found. Run: ./scripts/setup_gpu_ubuntu.sh"
    exit 1
fi
ok "Docker: $(docker --version | sed 's/Docker version //')"

if ! docker compose version &>/dev/null 2>&1; then
    fail "Docker Compose v2 not found."
    exit 1
fi
ok "Compose: $(docker compose version --short 2>/dev/null)"

# Check Docker daemon
if ! docker info &>/dev/null 2>&1; then
    fail "Docker daemon not running. Start Docker first."
    exit 1
fi
ok "Docker daemon running"

# ─── 4. Build and Start ──────────────────────────────────────────────────────
header "Starting Containers"
echo ""

BUILD_FLAG=""
if $REBUILD; then
    BUILD_FLAG="--build --force-recreate"
    info "Forcing rebuild of all images..."
fi

info "Running: docker compose -f ${COMPOSE_FILE} up -d ${BUILD_FLAG}"
echo ""

cd "${PROJECT_ROOT}"
# shellcheck disable=SC2086
docker compose -f "${COMPOSE_FILE}" up -d ${BUILD_FLAG}

echo ""
ok "Containers started"

# ─── 5. Wait for Health ──────────────────────────────────────────────────────
header "Health Checks"
echo ""

SERVICES=(
    "redis|zeus-redis|6379|tcp"
    "stt-service|zeus-stt|8001|http"
    "tts-service|zeus-tts|8002|http"
    "zeus-gateway|zeus-gateway|8000|http"
    "a2f-bridge|zeus-a2f|8003|http"
    "operator-console|zeus-operator|8080|http"
)

MAX_WAIT=180
POLL_INTERVAL=5
ELAPSED=0

info "Waiting for services to become healthy (timeout: ${MAX_WAIT}s)..."
echo ""

all_healthy() {
    for svc_info in "${SERVICES[@]}"; do
        IFS='|' read -r name container port proto <<< "$svc_info"
        STATUS=$(docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null || echo "missing")
        if [[ "$STATUS" != "healthy" ]]; then
            return 1
        fi
    done
    return 0
}

while ! all_healthy && (( ELAPSED < MAX_WAIT )); do
    sleep "$POLL_INTERVAL"
    ELAPSED=$((ELAPSED + POLL_INTERVAL))
    printf "  Waiting... %ds / %ds\r" "$ELAPSED" "$MAX_WAIT"
done
echo ""

# ─── 6. Status Table ─────────────────────────────────────────────────────────
header "Service Status"
echo ""
printf "  ${BOLD}%-22s %-12s %-8s %s${NC}\n" "SERVICE" "STATUS" "PORT" "URL"
printf "  %-22s %-12s %-8s %s\n"             "───────────────────" "──────────" "──────" "───────────────────────────"

for svc_info in "${SERVICES[@]}"; do
    IFS='|' read -r name container port proto <<< "$svc_info"
    STATUS=$(docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null || echo "missing")

    if [[ "$STATUS" == "healthy" ]]; then
        STATUS_COLOR="${GREEN}healthy${NC}"
    elif [[ "$STATUS" == "starting" ]]; then
        STATUS_COLOR="${YELLOW}starting${NC}"
    else
        STATUS_COLOR="${RED}${STATUS}${NC}"
    fi

    if [[ "$proto" == "http" ]]; then
        URL="http://localhost:${port}"
    else
        URL="localhost:${port}"
    fi

    printf "  %-22s %-20b %-8s %s\n" "$name" "$STATUS_COLOR" "$port" "$URL"
done

echo ""

# ─── 7. Final Output ─────────────────────────────────────────────────────────
if all_healthy; then
    echo -e "  ${GREEN}${BOLD}All services healthy!${NC}"
else
    warn "Some services are still starting. Check logs:"
    info "docker compose -f ${COMPOSE_FILE} logs -f"
fi

echo ""
echo -e "  ${BOLD}Operator Console:${NC}  ${CYAN}http://localhost:8080${NC}"
echo -e "  ${BOLD}Gateway API:${NC}       ${CYAN}http://localhost:8000${NC}"
echo -e "  ${BOLD}STT Service:${NC}       ${CYAN}http://localhost:8001${NC}"
echo -e "  ${BOLD}TTS Service:${NC}       ${CYAN}http://localhost:8002${NC}"
echo -e "  ${BOLD}A2F Bridge:${NC}        ${CYAN}http://localhost:8003${NC}"
echo ""
echo "  Logs:   docker compose -f ${COMPOSE_FILE} logs -f [service]"
echo "  Stop:   ./scripts/stop_all.sh"
echo "  Test:   ./scripts/test_end_to_end.sh"
echo ""
