#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# Zeus Live Avatar — Stop All Services
# Opulent Bots LLC — All rights reserved
#
# Gracefully stops all Zeus Live Avatar Docker services.
#
# Usage:
#   ./scripts/stop_all.sh            # stop containers (keep volumes)
#   ./scripts/stop_all.sh --clean    # stop containers + remove volumes
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
warn() { echo -e "  ${YELLOW}!${NC} $*"; }
info() { echo -e "  ${CYAN}→${NC} $*"; }
header() { echo -e "\n${BOLD}═══ $* ═══${NC}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="${PROJECT_ROOT}/infra/docker-compose.yml"

CLEAN=false
if [[ "${1:-}" == "--clean" ]]; then
    CLEAN=true
fi

header "Zeus Live Avatar — Stopping Services"
echo ""

cd "${PROJECT_ROOT}"

if $CLEAN; then
    warn "Removing containers AND volumes (Redis data, model cache)..."
    docker compose -f "${COMPOSE_FILE}" down -v --remove-orphans
    ok "All services stopped and volumes removed."
else
    info "Stopping containers (volumes preserved)..."
    docker compose -f "${COMPOSE_FILE}" down --remove-orphans
    ok "All services stopped."
fi

echo ""
info "Restart with: ./scripts/start_all.sh"
echo ""
