#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# Zeus Live Avatar — Model Fetch Script
# Opulent Bots LLC — All rights reserved
#
# Downloads model weights required by STT and TTS services.
# Models are NOT included in git (see .gitignore).
#
# Usage:
#   chmod +x scripts/fetch_models.sh
#   ./scripts/fetch_models.sh             # download all models
#   ./scripts/fetch_models.sh --stt-only  # download STT models only
#   ./scripts/fetch_models.sh --tts-only  # download TTS models only
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
MODELS_DIR="${PROJECT_ROOT}/models"

FETCH_STT=true
FETCH_TTS=true

case "${1:-all}" in
    --stt-only) FETCH_TTS=false ;;
    --tts-only) FETCH_STT=false ;;
    all|"") ;;
    *)
        echo "Usage: $0 [--stt-only|--tts-only]"
        exit 1
        ;;
esac

header "Zeus Live Avatar — Model Downloader"
echo ""
info "Project root: ${PROJECT_ROOT}"
info "Models dir:   ${MODELS_DIR}"
echo ""

# Create models directory
mkdir -p "${MODELS_DIR}"

# ─── Check Python ─────────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    fail "python3 not found. Install Python 3.10+ first."
    exit 1
fi
PYTHON_VERSION=$(python3 --version 2>&1)
ok "Python: ${PYTHON_VERSION}"

# ─── STT: faster-whisper models ───────────────────────────────────────────────
if $FETCH_STT; then
    header "STT Models (faster-whisper)"

    # Read model size from .env or default to base.en
    if [[ -f "${PROJECT_ROOT}/.env" ]]; then
        MODEL_SIZE=$(grep -E '^STT_MODEL_SIZE=' "${PROJECT_ROOT}/.env" | cut -d= -f2 || echo "base.en")
    else
        MODEL_SIZE="base.en"
    fi
    info "Target model: ${MODEL_SIZE}"

    # Check if faster-whisper is installed
    if python3 -c "import faster_whisper" &>/dev/null 2>&1; then
        ok "faster-whisper already installed"
    else
        info "Installing faster-whisper..."
        pip3 install --quiet faster-whisper
        ok "faster-whisper installed"
    fi

    # Pre-download the model (will cache in ~/.cache/huggingface/)
    info "Downloading faster-whisper model '${MODEL_SIZE}'..."
    info "This may take a few minutes on first run..."
    python3 -c "
from faster_whisper import WhisperModel
import sys
try:
    model = WhisperModel('${MODEL_SIZE}', device='cpu', compute_type='int8')
    print('  Model loaded and cached successfully.')
except Exception as e:
    print(f'  Error: {e}', file=sys.stderr)
    sys.exit(1)
"
    ok "faster-whisper model '${MODEL_SIZE}' ready"

    # Show estimated sizes
    echo ""
    info "Model size reference:"
    echo "    tiny.en   ~  75 MB  (fastest, lowest accuracy)"
    echo "    base.en   ~ 150 MB  (good balance)"
    echo "    small.en  ~ 500 MB  (better accuracy)"
    echo "    medium.en ~ 1.5 GB  (high accuracy)"
    echo "    large-v3  ~ 3.0 GB  (best accuracy, multilingual)"
fi

# ─── TTS: Coqui TTS models ───────────────────────────────────────────────────
if $FETCH_TTS; then
    header "TTS Models (Coqui TTS)"

    # Read engine from .env or default
    if [[ -f "${PROJECT_ROOT}/.env" ]]; then
        TTS_ENGINE=$(grep -E '^TTS_ENGINE=' "${PROJECT_ROOT}/.env" | cut -d= -f2 || echo "coqui")
        COQUI_MODEL=$(grep -E '^COQUI_MODEL_NAME=' "${PROJECT_ROOT}/.env" | cut -d= -f2 || echo "tts_models/en/vctk/vits")
    else
        TTS_ENGINE="coqui"
        COQUI_MODEL="tts_models/en/vctk/vits"
    fi

    if [[ "$TTS_ENGINE" == "coqui" ]] || [[ "$TTS_ENGINE" == "both" ]]; then
        info "Target Coqui model: ${COQUI_MODEL}"

        # Check if TTS is installed
        if python3 -c "from TTS.api import TTS" &>/dev/null 2>&1; then
            ok "Coqui TTS already installed"
        else
            info "Installing Coqui TTS..."
            pip3 install --quiet TTS
            ok "Coqui TTS installed"
        fi

        # Pre-download the model
        info "Downloading Coqui model '${COQUI_MODEL}'..."
        info "This may take several minutes on first run..."
        python3 -c "
from TTS.api import TTS
import sys
try:
    tts = TTS(model_name='${COQUI_MODEL}', progress_bar=True)
    print('  Model loaded and cached successfully.')
except Exception as e:
    print(f'  Error: {e}', file=sys.stderr)
    sys.exit(1)
"
        ok "Coqui model '${COQUI_MODEL}' ready"
    fi

    # ─── TTS: Piper models (optional) ────────────────────────────────────────
    if [[ "$TTS_ENGINE" == "piper" ]] || [[ "$TTS_ENGINE" == "both" ]]; then
        header "TTS Models (Piper)"

        PIPER_MODEL_URL="https://github.com/rhasspy/piper/releases/download/2023.11.14-2/voice-en_US-lessac-medium.tar.gz"
        PIPER_MODEL_FILE="${MODELS_DIR}/en_US-lessac-medium.onnx"

        if [[ -f "$PIPER_MODEL_FILE" ]]; then
            ok "Piper model already downloaded"
        else
            info "Downloading Piper voice model (en_US-lessac-medium)..."
            if command -v wget &>/dev/null; then
                wget -q --show-progress -O "${MODELS_DIR}/voice-en_US-lessac-medium.tar.gz" "$PIPER_MODEL_URL"
            elif command -v curl &>/dev/null; then
                curl -L --progress-bar -o "${MODELS_DIR}/voice-en_US-lessac-medium.tar.gz" "$PIPER_MODEL_URL"
            else
                fail "Neither wget nor curl found. Cannot download Piper model."
                exit 1
            fi

            info "Extracting..."
            tar -xzf "${MODELS_DIR}/voice-en_US-lessac-medium.tar.gz" -C "${MODELS_DIR}/"
            rm -f "${MODELS_DIR}/voice-en_US-lessac-medium.tar.gz"
            ok "Piper model extracted to ${MODELS_DIR}/"
        fi

        # Verify files exist
        if [[ -f "${PIPER_MODEL_FILE}" ]] && [[ -f "${PIPER_MODEL_FILE}.json" ]]; then
            ok "Piper model files verified"
            ONNX_SIZE=$(du -sh "${PIPER_MODEL_FILE}" | cut -f1)
            info "Model size: ${ONNX_SIZE}"
        else
            warn "Piper model files may not have extracted correctly. Check ${MODELS_DIR}/"
        fi
    fi
fi

# ─── Summary ──────────────────────────────────────────────────────────────────
header "Summary"
echo ""
echo "  Models directory: ${MODELS_DIR}"

if [[ -d "${MODELS_DIR}" ]]; then
    TOTAL_SIZE=$(du -sh "${MODELS_DIR}" 2>/dev/null | cut -f1)
    info "Total models size: ${TOTAL_SIZE}"
fi

echo ""
echo "  Cached model locations:"
echo "    faster-whisper: ~/.cache/huggingface/hub/"
echo "    Coqui TTS:     ~/.local/share/tts/"
echo "    Piper:         ${MODELS_DIR}/"
echo ""
ok "Model download complete."
echo ""
echo "  Next: ./scripts/start_all.sh"
echo ""
