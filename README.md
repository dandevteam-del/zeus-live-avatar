# Zeus Live Avatar

> Photorealistic AI avatar for Zoom, Teams, and Meet -- powered by Zeus Brain

Zeus Live Avatar enables Zeus (Opulent Bots' AI assistant) to appear as a
photorealistic MetaHuman on any video conferencing platform. Real-time speech
recognition, AI conversation, text-to-speech, and facial animation create a
natural, human-like presence.

**Opulent Bots LLC -- All rights reserved.**

---

## Features

- **Real-time speech-to-text** -- faster-whisper on GPU with VAD and barge-in detection
- **AI conversation** -- Zeus Brain integration with human-like timing and response cadence
- **Streaming text-to-speech** -- Coqui TTS (VITS/XTTS) or Piper for natural voice output
- **Facial animation** -- Audio2Face-3D compatible lip sync and expression blending
- **MetaHuman avatar** -- Photorealistic character in Unreal Engine 5 with idle animations
- **OBS Virtual Camera** -- Direct output to Zoom, Teams, Meet, or any video platform
- **Operator console** -- Web UI for live monitoring, text injection, and kill switch
- **Barge-in handling** -- Detects when participants interrupt; Zeus stops and listens
- **Human timing engine** -- Configurable response delays that mimic natural conversation
- **Safety controls** -- Kill switch, AI disclosure badge, mandatory operator presence
- **Dockerized backend** -- All services containerized with GPU support and health checks

---

## Architecture

```
  MEETING AUDIO                           VIDEO OUTPUT
       |                                       ^
       v                                       |
  +-----------+    +-----------+     +---------+---------+
  |  System   |    |    OBS    |---->| Virtual Camera    |
  |  Audio    |    |  Studio   |     | (v4l2loopback)    |
  |  Capture  |    +-----+-----+     +-------------------+
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
+--+---+ +---+----+       +-------------------+
| Zeus | |  TTS   |       | Operator Console  |
| Brain| | Service|       |      :8080        |
| (MCP)| | :8002  |       +-------------------+
+------+ +--------+

  [============ Redis Event Bus :6379 ============]
```

---

## Quick Start

```bash
# 1. Clone and configure
git clone <repository-url> zeus-live-avatar
cd zeus-live-avatar
cp .env.example .env      # edit with your settings

# 2. Install GPU prerequisites (Ubuntu 22.04/24.04)
chmod +x scripts/*.sh
./scripts/setup_gpu_ubuntu.sh

# 3. Download ML models
./scripts/fetch_models.sh

# 4. Start all backend services
./scripts/start_all.sh

# 5. Open Unreal Engine project (see ue/ZeusMetaHuman/SETUP.md)
# 6. Start OBS Virtual Camera (see obs/SETUP.md)
# 7. In Zoom: Camera -> "OBS Virtual Camera", Mic -> "Zeus Virtual Mic"
# 8. Open operator console at http://localhost:8080
```

---

## Repository Structure

```
zeus-live-avatar/
|
|-- .env.example              # Environment configuration template
|-- .gitignore                # Git ignore rules
|-- README.md                 # This file
|
|-- infra/                    # Docker infrastructure
|   |-- docker-compose.yml           # Main compose file (6 services)
|   |-- docker-compose.override.yml.example  # Optional NVIDIA NIM A2F
|   |-- redis.conf                   # Redis configuration
|
|-- services/                 # Backend microservices
|   |-- stt-service/          # Speech-to-text (faster-whisper + VAD)
|   |   |-- Dockerfile
|   |   |-- main.py
|   |   |-- vad.py
|   |   |-- requirements.txt
|   |
|   |-- tts-service/          # Text-to-speech (Coqui / Piper)
|   |   |-- Dockerfile
|   |   |-- engines/
|   |   |-- requirements.txt
|   |
|   |-- zeus-gateway/         # Orchestrator + Brain client
|   |   |-- Dockerfile
|   |   |-- brain_client.py
|   |   |-- timing.py
|   |   |-- requirements.txt
|   |
|   |-- a2f-bridge/           # Audio-to-face animation bridge
|   |   |-- Dockerfile
|   |
|   |-- operator-console/     # Web UI for live control
|       |-- Dockerfile
|       |-- package.json
|       |-- public/
|
|-- scripts/                  # Operational scripts
|   |-- setup_gpu_ubuntu.sh   # GPU + Docker prerequisite installer
|   |-- fetch_models.sh       # ML model downloader
|   |-- start_all.sh          # Start all services
|   |-- stop_all.sh           # Stop all services
|   |-- test_end_to_end.sh    # Full pipeline health test
|
|-- docs/                     # Documentation
|   |-- RUNBOOK.md            # Complete operational guide
|   |-- ARCHITECTURE.md       # Technical architecture deep-dive
|   |-- LICENSES.md           # Component license information
|
|-- ue/                       # Unreal Engine assets
|   |-- ZeusMetaHuman/        # UE5 project with MetaHuman
|
|-- obs/                      # OBS Studio configuration
|
|-- models/                   # ML model weights (git-ignored)
```

---

## Requirements

| Component | Requirement |
|-----------|-------------|
| OS | Linux (Ubuntu 22.04 or 24.04 LTS) |
| GPU | NVIDIA RTX 3060+ (12GB VRAM minimum) |
| NVIDIA Driver | 535+ |
| Docker | 24.0+ with Docker Compose v2 |
| nvidia-container-toolkit | For GPU access in containers |
| Unreal Engine | 5.4+ (for MetaHuman rendering) |
| OBS Studio | 28+ (includes obs-websocket) |
| RAM | 32 GB recommended |
| Storage | 50 GB free (models + Docker images) |

---

## Services

| Service | Port | Purpose | GPU |
|---------|------|---------|:---:|
| Redis | 6379 | Event bus and ephemeral state | No |
| STT Service | 8001 | Speech-to-text (faster-whisper) | Yes |
| TTS Service | 8002 | Text-to-speech (Coqui / Piper) | Yes |
| Zeus Gateway | 8000 | Orchestrator, Brain client, timing | No |
| A2F Bridge | 8003 | Audio-to-face blendshapes | Optional |
| Operator Console | 8080 | Web UI for live control | No |

---

## Expected Latency

| Stage | Target |
|-------|--------|
| Audio capture | ~20ms |
| STT processing | 200-500ms |
| End-of-turn detection | 800ms |
| Human timing delay | 200-1200ms |
| Zeus Brain response | 200-500ms |
| TTS synthesis | 100-300ms |
| A2F + UE render | ~60ms |
| OBS capture + encode | ~50ms |
| **Total (simple)** | **~1.5-2.5s** |
| **Total (complex)** | **~2-4s** |

---

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/setup_gpu_ubuntu.sh` | Check/install GPU and Docker prerequisites |
| `scripts/fetch_models.sh` | Download ML model weights |
| `scripts/start_all.sh` | Build and start all Docker services |
| `scripts/stop_all.sh` | Stop all Docker services |
| `scripts/test_end_to_end.sh` | Run full pipeline health tests |

---

## Documentation

| Document | Description |
|----------|-------------|
| [Runbook](docs/RUNBOOK.md) | Full operational guide -- setup, configuration, troubleshooting |
| [Architecture](docs/ARCHITECTURE.md) | Technical deep-dive -- data flow, protocols, decisions |
| [Licenses](docs/LICENSES.md) | Component license information and compliance |

---

## Safety

Zeus is an AI assistant. The system enforces:
- AI disclosure at the start of every session
- Visible "AI" badge overlay in the video output
- Mandatory human operator presence during live sessions
- Kill switch (STOP button) always accessible
- Session recording for audit purposes
- Compliance with applicable AI disclosure laws

---

## License

Proprietary -- Opulent Bots LLC. All rights reserved.

Unauthorized copying, distribution, or modification of this software is
strictly prohibited. See [docs/LICENSES.md](docs/LICENSES.md) for
third-party component licenses.
