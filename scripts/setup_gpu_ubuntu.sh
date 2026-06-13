#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# Zeus Live Avatar — GPU Setup Script for Ubuntu 22.04 / 24.04
# Opulent Bots LLC — All rights reserved
#
# Checks and installs all GPU and container prerequisites:
#   - NVIDIA driver (535+)
#   - CUDA toolkit (12.x)
#   - Docker Engine + Docker Compose v2
#   - nvidia-container-toolkit
#   - v4l2loopback (OBS virtual camera kernel module)
#   - PulseAudio / PipeWire (virtual audio)
#
# Usage:
#   chmod +x scripts/setup_gpu_ubuntu.sh
#   ./scripts/setup_gpu_ubuntu.sh         # interactive — prompts before install
#   ./scripts/setup_gpu_ubuntu.sh -y      # auto-approve all installs
# ═══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

# ─── Color helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

ok()   { echo -e "  ${GREEN}✓${NC} $*"; }
fail() { echo -e "  ${RED}✗${NC} $*"; }
warn() { echo -e "  ${YELLOW}!${NC} $*"; }
info() { echo -e "  ${CYAN}→${NC} $*"; }
header() { echo -e "\n${BOLD}═══ $* ═══${NC}"; }

AUTO_YES=false
if [[ "${1:-}" == "-y" || "${1:-}" == "--yes" ]]; then
    AUTO_YES=true
fi

confirm() {
    if $AUTO_YES; then return 0; fi
    read -rp "  Install $1? [y/N] " answer
    [[ "$answer" =~ ^[Yy] ]]
}

MISSING=()

# ─── Pre-flight ───────────────────────────────────────────────────────────────
header "Zeus Live Avatar — GPU Environment Setup"
echo ""
echo "  OS:   $(lsb_release -ds 2>/dev/null || cat /etc/os-release | grep PRETTY_NAME | cut -d= -f2 | tr -d '\"')"
echo "  Arch: $(uname -m)"
echo "  Date: $(date -u '+%Y-%m-%d %H:%M UTC')"
echo ""

# ─── 1. NVIDIA Driver ────────────────────────────────────────────────────────
header "NVIDIA Driver"
if command -v nvidia-smi &>/dev/null; then
    DRIVER_VERSION=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader,nounits 2>/dev/null | head -1)
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
    GPU_MEM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader 2>/dev/null | head -1)
    ok "NVIDIA driver ${DRIVER_VERSION} detected"
    ok "GPU: ${GPU_NAME} (${GPU_MEM})"
    DRIVER_MAJOR=$(echo "$DRIVER_VERSION" | cut -d. -f1)
    if (( DRIVER_MAJOR < 535 )); then
        warn "Driver ${DRIVER_VERSION} is below recommended 535+. Consider upgrading."
    fi
else
    fail "NVIDIA driver not found"
    info "Required: driver 535+ for CUDA 12.x support"
    if confirm "NVIDIA driver (latest from ubuntu-drivers)"; then
        sudo apt-get update
        sudo apt-get install -y ubuntu-drivers-common
        sudo ubuntu-drivers install
        warn "NVIDIA driver installed. A REBOOT is required before continuing."
        warn "After reboot, run this script again."
        exit 0
    else
        MISSING+=("nvidia-driver")
    fi
fi

# ─── 2. CUDA Toolkit ─────────────────────────────────────────────────────────
header "CUDA Toolkit"
if command -v nvcc &>/dev/null; then
    CUDA_VERSION=$(nvcc --version | grep "release" | sed -n 's/.*release \([0-9]*\.[0-9]*\).*/\1/p')
    ok "CUDA ${CUDA_VERSION} detected"
    CUDA_MAJOR=$(echo "$CUDA_VERSION" | cut -d. -f1)
    if (( CUDA_MAJOR < 12 )); then
        warn "CUDA ${CUDA_VERSION} is below recommended 12.x"
    fi
elif nvidia-smi &>/dev/null; then
    CUDA_FROM_SMI=$(nvidia-smi | grep "CUDA Version" | sed -n 's/.*CUDA Version: \([0-9]*\.[0-9]*\).*/\1/p')
    if [[ -n "$CUDA_FROM_SMI" ]]; then
        ok "CUDA ${CUDA_FROM_SMI} available (via driver, no nvcc)"
        info "nvcc not on PATH — this is fine for Docker-based GPU workloads"
    else
        fail "CUDA not detected"
        MISSING+=("cuda-toolkit")
    fi
else
    fail "CUDA not available (no driver or nvcc)"
    if confirm "CUDA toolkit 12.x"; then
        info "Installing CUDA toolkit from NVIDIA repository..."
        wget -q https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb
        sudo dpkg -i cuda-keyring_1.1-1_all.deb
        rm -f cuda-keyring_1.1-1_all.deb
        sudo apt-get update
        sudo apt-get install -y cuda-toolkit-12-4
        ok "CUDA toolkit installed. You may need to add to PATH:"
        info "  export PATH=/usr/local/cuda/bin:\$PATH"
    else
        MISSING+=("cuda-toolkit")
    fi
fi

# ─── 3. Docker Engine ────────────────────────────────────────────────────────
header "Docker"
if command -v docker &>/dev/null; then
    DOCKER_VERSION=$(docker --version | sed -n 's/Docker version \([^,]*\).*/\1/p')
    ok "Docker ${DOCKER_VERSION} detected"
else
    fail "Docker not found"
    if confirm "Docker Engine (official repository)"; then
        info "Installing Docker from official repository..."
        sudo apt-get update
        sudo apt-get install -y ca-certificates curl gnupg
        sudo install -m 0755 -d /etc/apt/keyrings
        curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
        sudo chmod a+r /etc/apt/keyrings/docker.gpg
        echo \
            "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
            $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
            sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
        sudo apt-get update
        sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
        sudo usermod -aG docker "$USER"
        ok "Docker installed. You may need to log out and back in for group changes."
    else
        MISSING+=("docker")
    fi
fi

# ─── 4. Docker Compose v2 ────────────────────────────────────────────────────
header "Docker Compose"
if docker compose version &>/dev/null 2>&1; then
    COMPOSE_VERSION=$(docker compose version --short 2>/dev/null || docker compose version | sed -n 's/.*v\([0-9.]*\).*/\1/p')
    ok "Docker Compose ${COMPOSE_VERSION} detected"
else
    fail "Docker Compose v2 not found"
    if confirm "Docker Compose plugin"; then
        sudo apt-get update
        sudo apt-get install -y docker-compose-plugin
        ok "Docker Compose plugin installed"
    else
        MISSING+=("docker-compose")
    fi
fi

# ─── 5. nvidia-container-toolkit ─────────────────────────────────────────────
header "NVIDIA Container Toolkit"
if command -v nvidia-ctk &>/dev/null; then
    NCT_VERSION=$(nvidia-ctk --version 2>/dev/null | head -1)
    ok "nvidia-container-toolkit detected: ${NCT_VERSION}"
elif dpkg -l nvidia-container-toolkit &>/dev/null 2>&1; then
    ok "nvidia-container-toolkit installed (via dpkg)"
else
    fail "nvidia-container-toolkit not found"
    info "Required for GPU access inside Docker containers"
    if confirm "nvidia-container-toolkit"; then
        info "Installing nvidia-container-toolkit..."
        curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
        curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
            sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
            sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
        sudo apt-get update
        sudo apt-get install -y nvidia-container-toolkit
        sudo nvidia-ctk runtime configure --runtime=docker
        sudo systemctl restart docker
        ok "nvidia-container-toolkit installed and Docker runtime configured"
    else
        MISSING+=("nvidia-container-toolkit")
    fi
fi

# ─── 6. v4l2loopback (OBS Virtual Camera) ────────────────────────────────────
header "v4l2loopback (Virtual Camera)"
if lsmod 2>/dev/null | grep -q v4l2loopback; then
    ok "v4l2loopback kernel module loaded"
elif modinfo v4l2loopback &>/dev/null 2>&1; then
    ok "v4l2loopback installed (not currently loaded)"
    info "Load with: sudo modprobe v4l2loopback video_nr=10 card_label='OBS Virtual Camera'"
else
    fail "v4l2loopback not found"
    info "Required for OBS Studio virtual camera output"
    if confirm "v4l2loopback-dkms"; then
        sudo apt-get update
        sudo apt-get install -y v4l2loopback-dkms v4l2loopback-utils
        ok "v4l2loopback installed"
        info "Load with: sudo modprobe v4l2loopback video_nr=10 card_label='OBS Virtual Camera'"
    else
        MISSING+=("v4l2loopback")
    fi
fi

# ─── 7. Audio System (PulseAudio / PipeWire) ─────────────────────────────────
header "Audio System (Virtual Microphone)"
if command -v pw-cli &>/dev/null; then
    ok "PipeWire detected"
    info "Virtual mic: use pw-loopback or the PipeWire virtual device module"
elif command -v pactl &>/dev/null; then
    ok "PulseAudio detected"
    info "Virtual mic: pactl load-module module-null-sink sink_name=ZeusMic sink_properties=device.description='Zeus_Virtual_Mic'"
else
    fail "No audio system (PulseAudio/PipeWire) detected"
    if confirm "PulseAudio"; then
        sudo apt-get update
        sudo apt-get install -y pulseaudio pulseaudio-utils
        ok "PulseAudio installed"
    else
        MISSING+=("audio-system")
    fi
fi

# ─── Summary ──────────────────────────────────────────────────────────────────
header "Summary"
echo ""
if [[ ${#MISSING[@]} -eq 0 ]]; then
    echo -e "  ${GREEN}${BOLD}All prerequisites satisfied!${NC}"
    echo ""
    echo "  Next steps:"
    echo "    1. cd $(dirname "$(dirname "$(readlink -f "$0")")")"
    echo "    2. cp .env.example .env  # configure your settings"
    echo "    3. ./scripts/fetch_models.sh"
    echo "    4. ./scripts/start_all.sh"
    echo ""
else
    echo -e "  ${RED}${BOLD}Missing components:${NC}"
    for item in "${MISSING[@]}"; do
        fail "$item"
    done
    echo ""
    echo "  Re-run this script with -y to auto-install all missing components:"
    echo "    ./scripts/setup_gpu_ubuntu.sh -y"
    echo ""
    exit 1
fi
