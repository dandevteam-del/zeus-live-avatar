#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# Zeus Live Avatar — End-to-End Pipeline Health Test
# Opulent Bots LLC — All rights reserved
#
# Validates the full pipeline by testing each service endpoint and
# running integration checks across the system.
#
# Usage:
#   chmod +x scripts/test_end_to_end.sh
#   ./scripts/test_end_to_end.sh
#   ./scripts/test_end_to_end.sh --verbose    # show full response bodies
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

VERBOSE=false
if [[ "${1:-}" == "--verbose" || "${1:-}" == "-v" ]]; then
    VERBOSE=true
fi

PASS=0
FAIL=0
SKIP=0
RESULTS=()

# Helper: run a test and record result
run_test() {
    local name="$1"
    local start_ms
    local end_ms
    local elapsed_ms

    start_ms=$(date +%s%N 2>/dev/null || python3 -c "import time; print(int(time.time()*1000))")

    if eval "$2" >/dev/null 2>&1; then
        end_ms=$(date +%s%N 2>/dev/null || python3 -c "import time; print(int(time.time()*1000))")
        # Handle nanoseconds (Linux) vs milliseconds (Python fallback)
        if (( end_ms > 1000000000000 )); then
            elapsed_ms=$(( (end_ms - start_ms) / 1000000 ))
        else
            elapsed_ms=$(( end_ms - start_ms ))
        fi
        ok "${name} (${elapsed_ms}ms)"
        RESULTS+=("PASS|${name}|${elapsed_ms}ms")
        PASS=$((PASS + 1))
    else
        end_ms=$(date +%s%N 2>/dev/null || python3 -c "import time; print(int(time.time()*1000))")
        if (( end_ms > 1000000000000 )); then
            elapsed_ms=$(( (end_ms - start_ms) / 1000000 ))
        else
            elapsed_ms=$(( end_ms - start_ms ))
        fi
        fail "${name} (${elapsed_ms}ms)"
        RESULTS+=("FAIL|${name}|${elapsed_ms}ms")
        FAIL=$((FAIL + 1))
    fi
}

skip_test() {
    local name="$1"
    local reason="$2"
    warn "${name} — SKIPPED (${reason})"
    RESULTS+=("SKIP|${name}|${reason}")
    SKIP=$((SKIP + 1))
}

header "Zeus Live Avatar — End-to-End Test Suite"
echo ""
info "Date: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo ""

# ─── 1. Service Health Checks ────────────────────────────────────────────────
header "1. Service Health Checks"

# Redis
run_test "Redis ping" \
    "docker exec zeus-redis redis-cli ping | grep -q PONG"

# STT Service
run_test "STT service /health" \
    "curl -sf http://localhost:8001/health"

# TTS Service
run_test "TTS service /health" \
    "curl -sf http://localhost:8002/health"

# Zeus Gateway
run_test "Gateway /health" \
    "curl -sf http://localhost:8000/health"

# A2F Bridge
run_test "A2F bridge /health" \
    "curl -sf http://localhost:8003/health"

# Operator Console
run_test "Operator console /health" \
    "curl -sf http://localhost:8080/health"

# ─── 2. STT Service — Audio Processing ───────────────────────────────────────
header "2. STT Service — Audio Processing"

# Generate 3 seconds of silence as raw PCM (16kHz, 16-bit, mono)
SILENCE_FILE="/tmp/zeus_test_silence.pcm"
python3 -c "
import struct, sys
# 3 seconds of silence at 16kHz, 16-bit mono
samples = 16000 * 3
with open('${SILENCE_FILE}', 'wb') as f:
    f.write(struct.pack('<' + 'h' * samples, *([0] * samples)))
" 2>/dev/null

if [[ -f "$SILENCE_FILE" ]]; then
    ok "Generated test audio (3s silence, 16kHz PCM)"

    # Test STT REST endpoint if available
    run_test "STT accepts audio upload" \
        "curl -sf -X POST http://localhost:8001/transcribe \
            -H 'Content-Type: application/octet-stream' \
            --data-binary @${SILENCE_FILE} \
            --max-time 10"

    rm -f "$SILENCE_FILE"
else
    skip_test "STT audio test" "Could not generate test audio"
fi

# ─── 3. TTS Service — Speech Synthesis ───────────────────────────────────────
header "3. TTS Service — Speech Synthesis"

# Test TTS REST endpoint
TTS_RESPONSE=$(curl -sf -X POST http://localhost:8002/synthesize \
    -H 'Content-Type: application/json' \
    -d '{"text": "Hello, this is a test of the Zeus text to speech system."}' \
    --max-time 30 \
    -o /tmp/zeus_test_tts_output.wav \
    -w "%{http_code}" 2>/dev/null || echo "000")

if [[ "$TTS_RESPONSE" == "200" ]]; then
    TTS_SIZE=$(wc -c < /tmp/zeus_test_tts_output.wav 2>/dev/null || echo "0")
    if (( TTS_SIZE > 1000 )); then
        ok "TTS synthesis returned audio (${TTS_SIZE} bytes)"
        PASS=$((PASS + 1))
        RESULTS+=("PASS|TTS synthesis|${TTS_SIZE} bytes")
    else
        fail "TTS synthesis returned too-small response (${TTS_SIZE} bytes)"
        FAIL=$((FAIL + 1))
        RESULTS+=("FAIL|TTS synthesis|${TTS_SIZE} bytes")
    fi
    rm -f /tmp/zeus_test_tts_output.wav
else
    fail "TTS synthesis failed (HTTP ${TTS_RESPONSE})"
    FAIL=$((FAIL + 1))
    RESULTS+=("FAIL|TTS synthesis|HTTP ${TTS_RESPONSE}")
fi

# ─── 4. Gateway — Message Processing ─────────────────────────────────────────
header "4. Gateway — Message Processing"

# Read auth token from .env
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
AUTH_TOKEN=""
if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    AUTH_TOKEN=$(grep -E '^GATEWAY_AUTH_TOKEN=' "${PROJECT_ROOT}/.env" | cut -d= -f2 || echo "")
fi

if [[ -n "$AUTH_TOKEN" ]]; then
    run_test "Gateway /message endpoint" \
        "curl -sf -X POST http://localhost:8000/message \
            -H 'Content-Type: application/json' \
            -H 'Authorization: Bearer ${AUTH_TOKEN}' \
            -d '{\"text\": \"Hello Zeus, this is a test.\", \"session_id\": \"test-e2e\"}' \
            --max-time 15"
else
    skip_test "Gateway /message" "No GATEWAY_AUTH_TOKEN in .env"
fi

# ─── 5. A2F Bridge — Blendshape Generation ───────────────────────────────────
header "5. A2F Bridge — Facial Animation"

# Generate a short PCM audio sample (1 second, 440Hz sine wave)
SINE_FILE="/tmp/zeus_test_sine.pcm"
python3 -c "
import struct, math
sample_rate = 16000
duration = 1.0
freq = 440.0
samples = int(sample_rate * duration)
data = []
for i in range(samples):
    t = i / sample_rate
    val = int(32767 * 0.5 * math.sin(2 * math.pi * freq * t))
    data.append(val)
with open('${SINE_FILE}', 'wb') as f:
    f.write(struct.pack('<' + 'h' * len(data), *data))
" 2>/dev/null

if [[ -f "$SINE_FILE" ]]; then
    run_test "A2F accepts audio for blendshapes" \
        "curl -sf -X POST http://localhost:8003/process \
            -H 'Content-Type: application/octet-stream' \
            --data-binary @${SINE_FILE} \
            --max-time 10"
    rm -f "$SINE_FILE"
else
    skip_test "A2F blendshape test" "Could not generate test audio"
fi

# ─── 6. Redis — Pub/Sub Event Bus ────────────────────────────────────────────
header "6. Redis — Event Bus"

# Test publish/subscribe round-trip
REDIS_TEST=$(docker exec zeus-redis sh -c '
    redis-cli SET zeus:test:ping pong EX 5 &&
    redis-cli GET zeus:test:ping
' 2>/dev/null || echo "")

if echo "$REDIS_TEST" | grep -q "pong"; then
    ok "Redis SET/GET round-trip"
    PASS=$((PASS + 1))
    RESULTS+=("PASS|Redis SET/GET|OK")
else
    fail "Redis SET/GET round-trip"
    FAIL=$((FAIL + 1))
    RESULTS+=("FAIL|Redis SET/GET|no response")
fi

# Test pub/sub
PUBSUB_TEST=$(docker exec zeus-redis sh -c '
    redis-cli PUBLISH zeus:test:channel "hello" 2>/dev/null
' 2>/dev/null || echo "")

if [[ -n "$PUBSUB_TEST" ]]; then
    ok "Redis PUBLISH command accepted"
    PASS=$((PASS + 1))
    RESULTS+=("PASS|Redis PUBLISH|OK")
else
    fail "Redis PUBLISH failed"
    FAIL=$((FAIL + 1))
    RESULTS+=("FAIL|Redis PUBLISH|no response")
fi

# ─── Results Summary ─────────────────────────────────────────────────────────
header "Results Summary"
echo ""
printf "  ${BOLD}%-8s %-35s %s${NC}\n" "RESULT" "TEST" "DETAIL"
printf "  %-8s %-35s %s\n"             "──────" "───────────────────────────────────" "──────────"

for result in "${RESULTS[@]}"; do
    IFS='|' read -r status name detail <<< "$result"
    case "$status" in
        PASS) printf "  ${GREEN}%-8s${NC} %-35s %s\n" "PASS" "$name" "$detail" ;;
        FAIL) printf "  ${RED}%-8s${NC} %-35s %s\n" "FAIL" "$name" "$detail" ;;
        SKIP) printf "  ${YELLOW}%-8s${NC} %-35s %s\n" "SKIP" "$name" "$detail" ;;
    esac
done

echo ""
echo -e "  ${BOLD}Total:${NC} ${GREEN}${PASS} passed${NC}, ${RED}${FAIL} failed${NC}, ${YELLOW}${SKIP} skipped${NC}"
echo ""

if (( FAIL > 0 )); then
    fail "Some tests failed. Check service logs:"
    info "docker compose -f infra/docker-compose.yml logs -f [service]"
    exit 1
else
    ok "All tests passed!"
fi

echo ""
