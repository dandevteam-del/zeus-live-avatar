# Zeus Live Avatar -- Runbook

> Complete operational guide for the Zeus Live Avatar system.
> Opulent Bots LLC -- All rights reserved.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [GPU Prerequisites](#gpu-prerequisites)
4. [Quick Start](#quick-start)
5. [Service Details](#service-details)
6. [Connecting to Zoom / Teams / Meet](#connecting-to-zoom--teams--meet)
7. [Operator Console](#operator-console)
8. [Latency Tuning Checklist](#latency-tuning-checklist)
9. [Expected Latency Budget](#expected-latency-budget)
10. [Safety and Disclosure](#safety-and-disclosure)
11. [Barge-In and Interrupt Handling](#barge-in-and-interrupt-handling)
12. [OBS Configuration](#obs-configuration)
13. [Audio Routing](#audio-routing)
14. [Unreal Engine Setup](#unreal-engine-setup)
15. [Troubleshooting](#troubleshooting)
16. [Monitoring](#monitoring)
17. [Backup and Recovery](#backup-and-recovery)
18. [Updating Components](#updating-components)

---

## Overview

Zeus Live Avatar is a production-grade AI avatar system that enables Zeus
(the AI assistant from Opulent Bots) to appear as a photorealistic MetaHuman
on Zoom, Teams, Meet, and any video platform. The system captures audio from
the meeting, processes speech in real-time, generates responses via the Zeus
Brain, synthesizes speech, drives facial animation, and outputs video + audio
through OBS as a virtual camera and microphone.

**Key capabilities:**
- Real-time speech-to-text with sub-500ms latency
- AI-powered conversation with human-like timing
- Streaming text-to-speech with natural voice
- Photorealistic MetaHuman with lip-synced facial animation
- Operator console for live monitoring and control
- Barge-in detection and interrupt handling
- Safety kill switch for immediate shutdown

---

## Architecture

```
  MEETING AUDIO                          VIDEO OUTPUT
       |                                      ^
       v                                      |
  +-----------+    +-----------+    +---------+---------+
  |  System   |    |    OBS    |--->| Virtual Camera    |
  |  Audio    |    |  Studio   |    | (v4l2loopback)    |
  |  Capture  |    +-----+-----+    +-------------------+
  +-----+-----+          ^
        |                 | NDI / Window Capture
        v                 |
  +-----+-----+    +-----+-----+
  |    STT    |    |  Unreal   |
  |  Service  |    |  Engine 5 |
  |  :8001    |    | MetaHuman |
  +-----+-----+    +-----+-----+
        |                 ^
        | transcript      | LiveLink blendshapes
        v                 |
  +-----+-----+    +-----+-----+
  |   Zeus    |    |    A2F    |
  |  Gateway  |--->|  Bridge   |
  |  :8000    |    |  :8003    |
  +-----+-----+    +-----------+
        |
   +----+----+
   |         |
   v         v
+--+---+ +---+----+        +-------------------+
| Zeus | |  TTS   |        | Operator Console  |
| Brain| | Service|        |      :8080        |
| (MCP)| | :8002  |        +-------------------+
+------+ +--------+

  [============ Redis Event Bus :6379 ============]
```

**Data flow:**
1. Meeting audio captured from system audio loopback
2. STT service transcribes speech in real-time
3. Gateway sends transcript to Zeus Brain, applies human timing
4. TTS service synthesizes the response as speech
5. A2F Bridge generates facial blendshapes from audio
6. Unreal Engine renders the MetaHuman with animation
7. OBS captures the render and outputs via virtual camera
8. Zoom/Teams/Meet displays the avatar

---

## GPU Prerequisites

### Minimum Hardware

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| GPU | NVIDIA RTX 3060 (12GB) | NVIDIA RTX 4080 (16GB+) |
| VRAM | 12 GB | 16+ GB |
| RAM | 16 GB | 32 GB |
| CPU | 6-core (AMD/Intel) | 8+ core |
| Storage | 50 GB free | 100 GB SSD |
| OS | Ubuntu 22.04 LTS | Ubuntu 24.04 LTS |

### Software Requirements

| Software | Minimum Version | Check Command |
|----------|----------------|---------------|
| NVIDIA Driver | 535+ | `nvidia-smi` |
| CUDA | 12.0+ | `nvcc --version` or check nvidia-smi |
| Docker | 24.0+ | `docker --version` |
| Docker Compose | 2.20+ | `docker compose version` |
| nvidia-container-toolkit | 1.14+ | `nvidia-ctk --version` |
| Unreal Engine | 5.4+ | Check Epic Games Launcher |
| OBS Studio | 28+ | `obs --version` |

### Automated Setup

Run the setup script to check and install all prerequisites:

```bash
# Interactive mode (prompts before each install)
./scripts/setup_gpu_ubuntu.sh

# Auto-install everything
./scripts/setup_gpu_ubuntu.sh -y
```

---

## Quick Start

### Step 1: Clone and Configure

```bash
git clone <repository-url> zeus-live-avatar
cd zeus-live-avatar
cp .env.example .env
# Edit .env with your settings (especially auth tokens)
```

### Step 2: Install GPU Prerequisites

```bash
chmod +x scripts/*.sh
./scripts/setup_gpu_ubuntu.sh
```

### Step 3: Download Models

```bash
./scripts/fetch_models.sh
```

### Step 4: Start Backend Services

```bash
./scripts/start_all.sh
```

### Step 5: Start Unreal Engine

Open the Unreal Engine project at `ue/ZeusMetaHuman/` and follow the
instructions in `ue/ZeusMetaHuman/SETUP.md`.

### Step 6: Configure OBS

Set up OBS Studio with virtual camera output. See `obs/SETUP.md` for
detailed instructions.

### Step 7: Join a Meeting

1. Open Zoom (or Teams, or Meet)
2. Go to Settings -> Video -> Camera -> select "OBS Virtual Camera"
3. Go to Settings -> Audio -> Microphone -> select the Zeus virtual mic
4. Join or start the meeting
5. Open the Operator Console at http://localhost:8080

### Step 8: Verify

```bash
./scripts/test_end_to_end.sh
```

---

## Service Details

### Redis (Event Bus)

| Property | Value |
|----------|-------|
| Container | `zeus-redis` |
| Image | `redis:7-alpine` |
| Port | 6379 |
| Health check | `redis-cli ping` |
| Volume | `zeus-redis-data` |
| Config | `infra/redis.conf` |

**Purpose:** Inter-service event bus (pub/sub) and ephemeral state store.
No persistence is enabled -- all data is reconstructed on restart.

**Configuration (`infra/redis.conf`):**
- Memory limit: 256MB with LRU eviction
- Persistence disabled (pub/sub event bus only)
- TCP keepalive: 60s, timeout: 300s

**Troubleshooting:**
- Check connectivity: `docker exec zeus-redis redis-cli ping`
- Monitor events: `docker exec zeus-redis redis-cli MONITOR`
- Check memory: `docker exec zeus-redis redis-cli INFO memory`

---

### STT Service (Speech-to-Text)

| Property | Value |
|----------|-------|
| Container | `zeus-stt` |
| Port | 8001 |
| GPU | Required |
| Health check | `GET /health` |
| Model | Configurable via `STT_MODEL_SIZE` |

**Purpose:** Real-time speech transcription using faster-whisper with VAD.

**Endpoints:**
- `GET /health` -- Health check
- `POST /transcribe` -- Transcribe audio file (PCM)
- `WS /ws/audio` -- Streaming audio transcription

**Key environment variables:**
- `STT_MODEL_SIZE` -- Whisper model (tiny.en, base.en, small.en, medium.en, large-v3)
- `STT_DEVICE` -- cuda or cpu
- `STT_COMPUTE_TYPE` -- float16, int8, int8_float16
- `STT_VAD_THRESHOLD` -- VAD sensitivity (0.0-1.0)
- `STT_SILENCE_DURATION_MS` -- Silence before end-of-utterance (ms)

**Troubleshooting:**
- OOM errors: Use a smaller model or reduce `STT_COMPUTE_TYPE` to int8
- Poor accuracy: Switch to `small.en` or `medium.en`
- Slow response: Ensure GPU is being used (`STT_DEVICE=cuda`)
- Logs: `docker compose -f infra/docker-compose.yml logs -f stt-service`

---

### TTS Service (Text-to-Speech)

| Property | Value |
|----------|-------|
| Container | `zeus-tts` |
| Port | 8002 |
| GPU | Required |
| Health check | `GET /health` |
| Engine | Configurable via `TTS_ENGINE` |
| Model cache | `zeus-model-cache` volume |

**Purpose:** Speech synthesis from text, supporting Coqui TTS and Piper.

**Endpoints:**
- `GET /health` -- Health check
- `POST /synthesize` -- Synthesize text to audio
- `WS /ws/synthesize` -- Streaming synthesis

**Key environment variables:**
- `TTS_ENGINE` -- coqui or piper
- `COQUI_MODEL_NAME` -- Coqui model identifier
- `COQUI_SPEAKER_ID` -- Speaker voice (e.g., p225 for VCTK)
- `COQUI_USE_CUDA` -- true/false
- `PIPER_MODEL_PATH` -- Path to Piper ONNX model
- `PIPER_SPEAKER_ID` -- Piper speaker index

**Troubleshooting:**
- Slow startup: First run downloads models (~500MB-2GB). Subsequent starts use cache.
- Voice quality: Try different `COQUI_SPEAKER_ID` values or switch to XTTS
- Latency: VITS is fastest, XTTS is highest quality but slower
- Logs: `docker compose -f infra/docker-compose.yml logs -f tts-service`

---

### Zeus Gateway (Orchestrator)

| Property | Value |
|----------|-------|
| Container | `zeus-gateway` |
| Port | 8000 |
| GPU | Not required |
| Health check | `GET /health` |
| Dependencies | Redis, STT, TTS |

**Purpose:** Central orchestrator. Receives transcripts from STT, sends to
Zeus Brain, manages human timing, routes responses to TTS, handles barge-in.

**Endpoints:**
- `GET /health` -- Health check with dependency status
- `POST /message` -- Send text message to Zeus Brain
- `POST /interrupt` -- Interrupt current response
- `GET /session/:id` -- Get session state
- `WS /ws/pipeline` -- Full pipeline WebSocket (for operator console)

**Key environment variables:**
- `ZEUS_BRAIN_URL` -- Zeus Brain HTTP endpoint
- `ZEUS_BRAIN_WS_URL` -- Zeus Brain WebSocket endpoint
- `GATEWAY_AUTH_TOKEN` -- Authentication token
- `TIMING_SIMPLE_MIN_MS` / `TIMING_SIMPLE_MAX_MS` -- Response delay range (simple questions)
- `TIMING_COMPLEX_MIN_MS` / `TIMING_COMPLEX_MAX_MS` -- Response delay range (complex questions)

**Troubleshooting:**
- No responses: Check `ZEUS_BRAIN_URL` is correct and reachable
- Slow responses: Tune timing parameters lower
- Barge-in not working: Check `zeus:stt:vad` Redis channel
- Logs: `docker compose -f infra/docker-compose.yml logs -f zeus-gateway`

---

### A2F Bridge (Facial Animation)

| Property | Value |
|----------|-------|
| Container | `zeus-a2f` |
| Port | 8003 |
| GPU | Optional (for ML-based analysis) |
| Health check | `GET /health` |
| Backend | Configurable via `A2F_BACKEND` |

**Purpose:** Converts PCM audio to ARKit-compatible blendshape weights for
facial animation. Outputs via LiveLink protocol to Unreal Engine.

**Endpoints:**
- `GET /health` -- Health check
- `POST /process` -- Process audio chunk, return blendshapes
- `WS /ws/stream` -- Streaming audio-to-blendshape pipeline

**Key environment variables:**
- `A2F_BACKEND` -- sdk (open-source) or nim (NVIDIA NIM container)
- `A2F_SAMPLE_RATE` -- Input audio sample rate (default: 16000)
- `A2F_FPS` -- Output blendshape frame rate (default: 60)
- `A2F_NIM_ENDPOINT` -- NIM container address (if using nim backend)

**Troubleshooting:**
- No facial animation: Check LiveLink connection in UE (Window -> LiveLink)
- Lip sync offset: Adjust `A2F_FPS` or check audio latency
- NIM errors: Verify NGC_API_KEY and NIM container status
- Logs: `docker compose -f infra/docker-compose.yml logs -f a2f-bridge`

---

### Operator Console (Web UI)

| Property | Value |
|----------|-------|
| Container | `zeus-operator` |
| Port | 8080 |
| GPU | Not required |
| Health check | `GET /health` |
| Depends on | zeus-gateway |

**Purpose:** Web-based operator interface for live monitoring and control.

**Features:**
- Real-time transcript viewer (what Zeus hears)
- Response viewer (what Zeus says)
- Manual text injection (type a response for Zeus)
- Kill switch (STOP button) -- immediately halts all output
- Emotion/persona selector
- Pipeline latency dashboard
- Service health indicators

**Access:** Open http://localhost:8080 in a browser.

---

## Connecting to Zoom / Teams / Meet

### Prerequisites

Before joining a meeting, ensure:
- [ ] All Docker services are running and healthy (`./scripts/start_all.sh`)
- [ ] Unreal Engine is running with MetaHuman and LiveLink connected
- [ ] OBS Studio is running with Virtual Camera enabled
- [ ] Virtual audio device is configured (see Audio Routing)
- [ ] Operator Console is open at http://localhost:8080

### Zoom

1. Open Zoom and go to **Settings**
2. **Video** tab:
   - Camera: Select **"OBS Virtual Camera"**
   - Uncheck "Mirror my video" (the avatar should not be mirrored)
3. **Audio** tab:
   - Microphone: Select **"Zeus Virtual Mic"** (or your virtual audio device name)
   - Speaker: Select your normal speakers/headphones (this is what you hear)
   - Uncheck "Automatically adjust microphone volume"
4. Join or start the meeting
5. Verify avatar is visible to other participants

### Microsoft Teams

1. Open Teams and click your profile picture -> **Settings**
2. **Devices** section:
   - Camera: Select **"OBS Virtual Camera"**
   - Microphone: Select **"Zeus Virtual Mic"**
3. Join or start the meeting
4. In the meeting controls, verify camera shows the avatar

### Google Meet

1. Join a Google Meet call
2. Click the three-dot menu -> **Settings**
3. **Video** tab: Select **"OBS Virtual Camera"**
4. **Audio** tab: Microphone -> Select **"Zeus Virtual Mic"**
5. Close settings and verify avatar is visible

### Troubleshooting Video Calls

| Issue | Solution |
|-------|----------|
| Black screen in Zoom | Restart OBS Virtual Camera (Tools -> Start Virtual Camera) |
| Avatar is mirrored | Uncheck "Mirror my video" in Zoom settings |
| No audio output | Check virtual mic is selected; check TTS service is running |
| Audio echo | Mute the real microphone; use only the virtual mic |
| Low FPS | Reduce UE render resolution to 720p; use NVENC in OBS |
| Zoom uses wrong camera | Close other apps that might claim the camera |

---

## Operator Console

The operator console at http://localhost:8080 provides real-time control
during live sessions.

### Controls

| Control | Function |
|---------|----------|
| **STOP** (kill switch) | Immediately halts all audio/video output. Zeus goes silent and idle. |
| **Resume** | Resumes normal operation after STOP |
| **Inject Text** | Type a message that Zeus will speak (bypasses Brain) |
| **Set Emotion** | Change Zeus's emotional state (neutral, happy, serious, concerned) |
| **Mute Input** | Stop processing incoming audio (Zeus stops listening) |
| **Mute Output** | Stop TTS output (Zeus listens but does not speak) |

### Dashboard Panels

| Panel | Shows |
|-------|-------|
| Transcript | Live feed of what Zeus hears (STT output) |
| Response | What Zeus is saying (current response text) |
| Latency | Per-stage pipeline latency (STT, Brain, TTS, A2F) |
| Services | Health status of all backend services |
| Session | Current session ID, duration, message count |

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Escape` | Emergency STOP |
| `Space` | Toggle mute output |
| `Enter` | Focus inject text field |

---

## Latency Tuning Checklist

Use this checklist to optimize end-to-end response latency:

- [ ] **STT Model:** Use `base.en` for speed or `small.en` for balanced accuracy/speed
- [ ] **STT Silence Threshold:** Reduce `STT_SILENCE_DURATION_MS` to 600ms for faster turn detection (default 800ms)
- [ ] **STT Compute Type:** Use `float16` on capable GPUs, `int8` for lower VRAM
- [ ] **TTS Engine:** Use Coqui VITS (fastest) over XTTS (highest quality but slower)
- [ ] **TTS Model:** `tts_models/en/vctk/vits` is fastest; XTTS is 3-5x slower
- [ ] **Gateway Timing:** Reduce `TIMING_SIMPLE_MIN_MS`/`TIMING_SIMPLE_MAX_MS` for faster responses
- [ ] **A2F FPS:** Set to 30 FPS (sufficient for video calls, saves GPU)
- [ ] **UE Render Resolution:** Use 720p (1280x720) instead of 1080p
- [ ] **UE Target FPS:** Set `UE_TARGET_FPS=30` (video calls are typically 30fps)
- [ ] **OBS Encoding:** Use NVENC (hardware) with ultrafast preset, not x264
- [ ] **Network:** Run all services on the same machine (eliminates network latency)
- [ ] **Docker:** Use `--network host` if latency between containers is an issue
- [ ] **Redis:** Already configured with no persistence (minimal overhead)

---

## Expected Latency Budget

| Stage | Target | Notes |
|-------|--------|-------|
| Audio capture | ~20ms | System audio routing overhead |
| STT processing | 200-500ms | faster-whisper base.en on GPU |
| End-of-turn detection | 800ms | VAD silence threshold (configurable) |
| Human timing delay | 200-1200ms | Configurable per complexity |
| Zeus Brain response | 200-500ms | First token from LLM |
| TTS synthesis | 100-300ms | Coqui VITS on GPU |
| Audio2Face animation | ~30ms | Per-frame, fully pipelined |
| UE render | ~33ms | At 30 FPS |
| OBS capture + encode | ~50ms | NVENC hardware encoding |
| **Total (simple answer)** | **~1.5-2.5s** | **Comparable to human reaction** |
| **Total (complex answer)** | **~2-4s** | **With longer thinking time** |

These latencies assume a single RTX 3060 12GB running all services. With an
RTX 4090, expect 20-40% lower latencies for GPU-bound stages (STT, TTS).

---

## Safety and Disclosure

### Mandatory Rules

1. **Zeus is an AI assistant.** Never misrepresent Zeus as a human being.

2. **Disclosure at session start.** At the beginning of every meeting, webinar,
   or call, Zeus must introduce itself as an AI. Example: "Hello, I'm Zeus,
   an AI assistant from Opulent Bots. I'll be joining this meeting to help
   with [topic]."

3. **Visible AI badge.** The OBS overlay must include a visible "AI" or
   "AI Avatar" badge at all times. This is configured in the OBS scene.

4. **Operator presence.** A human operator must be present and monitoring the
   Operator Console during all live sessions. The operator has the ability
   and responsibility to intervene at any time.

5. **Kill switch.** The STOP button in the Operator Console (or the `Escape`
   key shortcut) must always be accessible. It immediately halts all audio
   and video output.

6. **Session recording.** All live sessions should be recorded for audit
   purposes. OBS can record the session output simultaneously.

7. **Legal compliance.** Comply with all applicable laws regarding:
   - AI disclosure in video calls
   - Recording consent (varies by jurisdiction)
   - Synthetic media regulations
   - Data privacy (GDPR, CCPA, etc.)

### Content Guardrails

The Zeus Brain (backend AI) enforces its own content guardrails. Additionally:
- The Gateway filters responses for inappropriate content
- The Operator can inject corrections or stop responses mid-sentence
- All responses are logged for review

---

## Barge-In and Interrupt Handling

"Barge-in" occurs when a meeting participant starts speaking while Zeus is
still responding. The system handles this gracefully:

### How It Works

1. **VAD Detection:** The STT service continuously monitors for voice activity
   even while Zeus is speaking.

2. **Interrupt Signal:** When speech is detected during a Zeus response, the
   STT service publishes a `speech_start` event on `zeus:stt:vad`.

3. **Gateway Response:** The Gateway receives the interrupt signal and:
   - Immediately stops sending text to TTS
   - Sends a `cancel` command to TTS (stops audio output)
   - Publishes an `interrupt` command on `zeus:gateway:control`
   - Waits for the new utterance to complete

4. **Graceful Transition:** Zeus stops speaking mid-sentence and listens to
   the new input. The response is abandoned (not resumed later).

5. **New Response:** After the participant finishes speaking, the normal
   pipeline resumes with the new transcript.

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `STT_VAD_THRESHOLD` | 0.5 | Sensitivity for barge-in detection (lower = more sensitive) |
| `STT_SILENCE_DURATION_MS` | 800 | How long to wait after speech ends before finalizing |

---

## OBS Configuration

### Basic Setup

1. Install OBS Studio 28+ (includes obs-websocket by default)
2. Create a new Scene called "ZeusAvatar"
3. Add sources:
   - **Window Capture** or **NDI Source**: Capture the UE5 render window
   - **Image**: AI badge overlay (positioned in a corner)
   - **Text (GDI+)**: Optional lower-third text
4. Configure output:
   - Settings -> Video -> Base Resolution: 1920x1080
   - Settings -> Video -> Output Resolution: 1280x720 (for performance)
   - Settings -> Video -> FPS: 30
5. Start Virtual Camera: Tools -> Start Virtual Camera

### OBS WebSocket (Remote Control)

OBS 28+ includes obs-websocket by default. Configure in:
- Tools -> obs-websocket Settings
- Enable WebSocket server
- Set port (default 4455)
- Set password (set in `.env` as `OBS_WS_PASSWORD`)

The Gateway can control OBS remotely via WebSocket to:
- Switch scenes
- Show/hide sources (e.g., toggle AI badge)
- Start/stop virtual camera
- Start/stop recording

### Recommended OBS Settings for Video Calls

| Setting | Value | Location |
|---------|-------|----------|
| Encoder | NVENC H.264 | Settings -> Output -> Streaming |
| Rate Control | CBR | Settings -> Output -> Streaming |
| Bitrate | 2500 Kbps | Settings -> Output -> Streaming |
| Preset | Low Latency Quality | Settings -> Output -> Streaming |
| Base Resolution | 1920x1080 | Settings -> Video |
| Output Resolution | 1280x720 | Settings -> Video |
| FPS | 30 | Settings -> Video |

---

## Audio Routing

### PulseAudio (Ubuntu 22.04)

Create a virtual microphone (null sink) that receives TTS audio:

```bash
# Create virtual mic
pactl load-module module-null-sink sink_name=ZeusMic \
    sink_properties=device.description='Zeus_Virtual_Mic'

# Create a monitor source from the sink
# (This appears as a microphone in Zoom)
pactl load-module module-remap-source \
    master=ZeusMic.monitor \
    source_name=ZeusMicSource \
    source_properties=device.description='Zeus_Virtual_Mic_Source'

# Verify
pactl list short sources | grep Zeus
```

In Zoom/Teams/Meet, select "Zeus_Virtual_Mic_Source" (or "Monitor of
Zeus_Virtual_Mic") as the microphone.

### PipeWire (Ubuntu 24.04)

PipeWire is the default audio system on Ubuntu 24.04:

```bash
# Create a virtual sink + source pair
pw-cli create-node adapter \
    '{ factory.name=support.null-audio-sink \
       node.name=ZeusMic \
       media.class=Audio/Sink \
       audio.position=[FL FR] \
       monitor.channel-volumes=true }'

# The monitor source automatically appears as "ZeusMic Monitor"
```

### Capturing Meeting Audio

To capture what other participants are saying (so Zeus can hear them):

```bash
# PulseAudio: Create a loopback from speakers to STT input
pactl load-module module-loopback \
    source=@DEFAULT_MONITOR@ \
    sink=ZeusInput \
    latency_msec=20

# PipeWire: Use pw-loopback
pw-loopback --capture-props='node.target=default_output' \
    --playback-props='node.target=ZeusInput'
```

---

## Unreal Engine Setup

See `ue/ZeusMetaHuman/SETUP.md` for the complete UE setup guide.

### Quick Reference

1. Open the project in UE 5.4+
2. Enable the LiveLink plugin (Edit -> Plugins -> LiveLink)
3. Add a LiveLink source: Window -> LiveLink -> Add Source -> Message Bus
4. The A2F Bridge publishes blendshapes via LiveLink protocol
5. Apply the LiveLink animation blueprint to the MetaHuman
6. Set render resolution via `UE_RENDER_WIDTH` and `UE_RENDER_HEIGHT` in .env
7. Target FPS via `UE_TARGET_FPS` (30 recommended for video calls)

---

## Troubleshooting

### Service Won't Start

| Symptom | Cause | Solution |
|---------|-------|----------|
| GPU service fails with "no NVIDIA GPU" | nvidia-container-toolkit not configured | Run `./scripts/setup_gpu_ubuntu.sh` |
| Port already in use | Another service on same port | Change port in `.env` or stop conflicting service |
| Build fails | Missing base image | `docker pull nvidia/cuda:12.4.0-runtime-ubuntu22.04` |
| OOM killed | Insufficient VRAM/RAM | Use smaller STT model; reduce services |

### Audio Issues

| Symptom | Cause | Solution |
|---------|-------|----------|
| No transcription | Audio not reaching STT | Check audio routing (see Audio Routing section) |
| Wrong language | Using multilingual model | Use `.en` model variant |
| Too many false triggers | VAD too sensitive | Increase `STT_VAD_THRESHOLD` |
| Missed speech | VAD not sensitive enough | Decrease `STT_VAD_THRESHOLD` |
| Robotic voice | Using low-quality TTS | Switch to Coqui VITS or XTTS |
| No TTS output | TTS container unhealthy | Check logs: `docker logs zeus-tts` |
| Audio crackling | Buffer underrun | Increase audio buffer size |

### Video Issues

| Symptom | Cause | Solution |
|---------|-------|----------|
| Black screen in Zoom | OBS Virtual Camera not started | Tools -> Start Virtual Camera in OBS |
| Low FPS avatar | UE render too heavy | Reduce resolution, lower quality settings |
| No facial animation | LiveLink not connected | Check Window -> LiveLink in UE |
| Lip sync delay | Audio pipeline latency | Reduce A2F FPS; check timing |
| Avatar frozen | UE crashed or LiveLink disconnected | Restart UE and reconnect LiveLink |

### Network/Connectivity

| Symptom | Cause | Solution |
|---------|-------|----------|
| Gateway timeout | Zeus Brain unreachable | Check `ZEUS_BRAIN_URL` in `.env` |
| Redis connection refused | Redis not running | `docker logs zeus-redis` |
| Services can't find each other | Docker network issue | `docker network inspect zeus-avatar-net` |

### Common Docker Commands

```bash
# View logs for all services
docker compose -f infra/docker-compose.yml logs -f

# View logs for specific service
docker compose -f infra/docker-compose.yml logs -f stt-service

# Restart a specific service
docker compose -f infra/docker-compose.yml restart stt-service

# Rebuild a specific service
docker compose -f infra/docker-compose.yml build stt-service
docker compose -f infra/docker-compose.yml up -d stt-service

# Check resource usage
docker stats

# Shell into a container
docker exec -it zeus-stt bash

# Check GPU from within container
docker exec zeus-stt nvidia-smi
```

---

## Monitoring

### Health Endpoints

All services expose a `/health` endpoint:

```bash
# Quick health check
curl -s http://localhost:8000/health | jq .  # Gateway
curl -s http://localhost:8001/health | jq .  # STT
curl -s http://localhost:8002/health | jq .  # TTS
curl -s http://localhost:8003/health | jq .  # A2F
curl -s http://localhost:8080/health | jq .  # Operator Console
docker exec zeus-redis redis-cli ping        # Redis
```

### Logging

All services log to stdout. View via Docker:

```bash
# All services
docker compose -f infra/docker-compose.yml logs -f

# Specific service with timestamps
docker compose -f infra/docker-compose.yml logs -f -t zeus-gateway

# Last 100 lines
docker compose -f infra/docker-compose.yml logs --tail=100 stt-service
```

Log level is configurable via `LOG_LEVEL` in `.env`:
- `debug` -- Verbose, includes audio chunk processing, Redis messages
- `info` -- Normal operation (recommended)
- `warning` -- Only warnings and errors
- `error` -- Only errors

### Redis Event Tracing

Monitor all Redis pub/sub events in real-time:

```bash
# Subscribe to all Zeus channels
docker exec zeus-redis redis-cli PSUBSCRIBE 'zeus:*'

# Subscribe to specific channel
docker exec zeus-redis redis-cli SUBSCRIBE zeus:stt:transcript
```

### Operator Console

The Operator Console at http://localhost:8080 provides a real-time dashboard
with service health, pipeline latency, and event history.

---

## Backup and Recovery

### What to Back Up

| Item | Location | Frequency |
|------|----------|-----------|
| Environment config | `.env` | After every change |
| OBS scene collection | `obs/` | After setup |
| UE project settings | `ue/ZeusMetaHuman/Config/` | After changes |
| Session recordings | OBS recording directory | Per session |
| Custom voice models | `models/` | After training |

### Recovery Procedure

If the system crashes or needs to be rebuilt:

1. Ensure `.env` is intact (restore from backup if needed)
2. `./scripts/start_all.sh --rebuild` to rebuild all containers
3. Start Unreal Engine and verify LiveLink
4. Start OBS and verify Virtual Camera
5. Run `./scripts/test_end_to_end.sh` to verify
6. Join a test meeting to confirm full pipeline

---

## Updating Components

### Updating Docker Services

```bash
# Pull latest code changes
git pull

# Rebuild and restart
./scripts/stop_all.sh
./scripts/start_all.sh --rebuild
```

### Updating Models

```bash
# Re-download models (will fetch latest versions)
./scripts/fetch_models.sh

# Restart services to pick up new models
./scripts/stop_all.sh
./scripts/start_all.sh
```

### Updating NVIDIA Drivers

```bash
# Check current version
nvidia-smi

# Update via ubuntu-drivers
sudo ubuntu-drivers install

# REBOOT REQUIRED after driver update
sudo reboot

# After reboot, restart services
./scripts/start_all.sh
```

### Updating Docker Images

```bash
# Update base images
docker pull redis:7-alpine
docker pull nvidia/cuda:12.4.0-runtime-ubuntu22.04
docker pull python:3.11-slim
docker pull node:20-slim

# Rebuild with fresh base
./scripts/start_all.sh --rebuild
```

---

## Appendix: Environment Variable Reference

See `.env.example` for the complete list of configurable environment variables
with descriptions and default values.

## Appendix: Redis Channel Reference

See `docs/ARCHITECTURE.md` for the complete Redis pub/sub channel documentation.

## Appendix: API Reference

See `docs/ARCHITECTURE.md` for HTTP and WebSocket endpoint documentation.
