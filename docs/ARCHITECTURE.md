# Zeus Live Avatar -- Architecture

> Technical architecture document for the Zeus Live Avatar system.
> Opulent Bots LLC -- All rights reserved.

---

## System Diagram

```
                         +------------------+
                         |   Zoom / Teams   |
                         |   Google Meet    |
                         +--------+---------+
                                  |
                    OBS Virtual Camera + Virtual Mic
                                  |
                    +-------------+-------------+
                    |                           |
              +-----+------+             +------+-----+
              | OBS Studio |             |  System    |
              | (Video Out)|             | Audio In   |
              +-----+------+             +------+-----+
                    |                           |
              NDI / Window                 Loopback /
              Capture                      PulseAudio
                    |                           |
         +----------+----------+    +-----------+-----------+
         | Unreal Engine 5     |    |    STT Service        |
         | MetaHuman Avatar    |    |    (faster-whisper)   |
         |                     |    |    Port 8001          |
         | - LiveLink A2F      |    |                       |
         | - Emotion blending  |    | - WebSocket stream    |
         | - Idle animations   |    | - VAD detection       |
         | - Camera control    |    | - Chunked transcripts |
         +----------+----------+    +-----------+-----------+
                    ^                           |
                    |                           | Transcript
                    |                           v
         +----------+----------+    +-----------+-----------+
         | A2F Bridge          |    |    Zeus Gateway        |
         | Port 8003           |    |    Port 8000           |
         |                     |    |                        |
         | - Audio -> visemes  |    | - Orchestrator         |
         | - Blendshape stream |    | - Human timing engine  |
         | - LiveLink output   |    | - Barge-in handling    |
         +----------+----------+    | - Session management   |
                    ^               +-----------+-----------+
                    |                           |
                    |                     +-----+-----+
                    |                     |           |
                    |              +------+---+ +-----+------+
                    |              | Zeus     | | TTS Service |
                    +--------------+ Brain    | | (Coqui/    |
                    audio stream   | (MCP)    | |  Piper)    |
                                   +----------+ | Port 8002  |
                                                +------------+

                    +-------------------------------------------------+
                    |              Redis Event Bus                     |
                    |              Port 6379                           |
                    |                                                  |
                    |  Channels:                                       |
                    |    zeus:stt:transcript   zeus:tts:audio          |
                    |    zeus:a2f:blendshapes  zeus:gateway:control    |
                    |    zeus:operator:cmd     zeus:session:state      |
                    +-------------------------------------------------+

                    +-------------------------------------------------+
                    |           Operator Console                       |
                    |           Port 8080                              |
                    |                                                  |
                    |  - Live transcript view                          |
                    |  - Manual text injection                         |
                    |  - Kill switch (STOP)                            |
                    |  - Emotion / persona controls                    |
                    |  - Pipeline latency monitor                      |
                    +-------------------------------------------------+
```

---

## Data Flow

The system operates as a real-time audio/video pipeline with six discrete stages:

### Stage 1: Audio Capture

Meeting audio is captured from the system audio output (what Zeus "hears") using
either PulseAudio loopback or PipeWire routing. The raw PCM audio stream (16kHz,
16-bit, mono) is forwarded to the STT service via WebSocket.

### Stage 2: Speech-to-Text

The STT service runs `faster-whisper` with Voice Activity Detection (VAD). It:
1. Receives continuous PCM audio chunks via WebSocket
2. Runs VAD to detect speech segments
3. Accumulates audio during speech, detects end-of-utterance via silence threshold
4. Transcribes completed utterances using the Whisper model
5. Publishes interim and final transcripts to `zeus:stt:transcript` on Redis
6. Sends the final transcript to the Gateway via direct HTTP call

### Stage 3: Zeus Brain (Orchestration)

The Gateway receives the transcript and:
1. Applies human timing delay (configurable, 200-1200ms based on complexity)
2. May insert a "preface" (e.g., "Hmm, let me think about that...")
3. Sends the message to Zeus Brain (the main AI backend) via HTTP/WebSocket
4. Receives the response as a text stream (token-by-token)
5. Accumulates tokens into sentence-length chunks for TTS
6. Handles barge-in detection (if new speech arrives, cancels current response)

### Stage 4: Text-to-Speech

The TTS service receives text chunks and:
1. Synthesizes speech using Coqui VITS (fast) or XTTS (high quality) or Piper
2. Returns PCM audio via WebSocket or HTTP response
3. Publishes audio chunks to `zeus:tts:audio` on Redis
4. Audio is simultaneously sent to the A2F Bridge and the virtual mic output

### Stage 5: Facial Animation

The A2F Bridge receives PCM audio and:
1. Analyzes audio to generate ARKit-compatible blendshape weights (52 values)
2. Uses either NVIDIA Audio2Face SDK, NIM container, or open-source audio analysis
3. Streams blendshape frames at the configured FPS (30-60) via LiveLink protocol
4. Unreal Engine receives the blendshapes and applies them to the MetaHuman face

### Stage 6: Video Output

Unreal Engine renders the MetaHuman with:
1. Applied facial blendshapes from LiveLink
2. Idle animations (subtle head movement, blinking, breathing)
3. Emotion-based pose blending (from Gateway emotion tags)
4. Camera framing appropriate for video calls (head + shoulders)

The rendered frame is sent to OBS via NDI or window capture. OBS composites the
final output with any overlays (AI badge, lower third) and outputs to the
virtual camera device that Zoom/Teams/Meet sees.

---

## Component Interaction: Redis Pub/Sub Channels

All inter-service communication uses Redis pub/sub for real-time events and
Redis key-value for state. This decouples services and enables monitoring.

| Channel | Publisher | Subscriber(s) | Payload |
|---------|-----------|---------------|---------|
| `zeus:stt:transcript` | STT Service | Gateway, Operator Console | `{type, text, is_final, confidence, timestamp}` |
| `zeus:stt:vad` | STT Service | Gateway, Operator Console | `{type: "speech_start"\|"speech_end", timestamp}` |
| `zeus:gateway:response` | Gateway | TTS Service, Operator Console | `{type, text, chunk_index, is_final, emotion}` |
| `zeus:gateway:control` | Gateway | All services | `{command: "interrupt"\|"stop"\|"resume"}` |
| `zeus:tts:audio` | TTS Service | A2F Bridge, Audio Output | `{pcm_base64, sample_rate, chunk_index}` |
| `zeus:tts:status` | TTS Service | Gateway, Operator Console | `{status: "speaking"\|"idle", chunk_index}` |
| `zeus:a2f:blendshapes` | A2F Bridge | UE Plugin (via LiveLink) | `{weights: float[52], timestamp, fps}` |
| `zeus:operator:cmd` | Operator Console | Gateway | `{command, payload}` |
| `zeus:session:state` | Gateway | Operator Console | `{state, active_speaker, response_in_progress}` |

### Redis Key-Value State

| Key | Purpose | TTL |
|-----|---------|-----|
| `zeus:session:{id}` | Current session state | Session duration |
| `zeus:pipeline:latency` | Last measured pipeline latencies | 60s |
| `zeus:health:{service}` | Service heartbeat timestamp | 30s |

---

## Protocol Descriptions

### WebSocket: STT Audio Input

```
Client -> STT Service (ws://localhost:8001/ws/audio)

Binary frames: Raw PCM audio
  - 16-bit signed little-endian
  - 16000 Hz sample rate
  - Mono channel
  - Recommended chunk size: 4096 bytes (128ms at 16kHz)

JSON frames (control):
  {"type": "config", "sample_rate": 16000, "encoding": "pcm_s16le"}
  {"type": "end_of_stream"}

STT -> Client:
  {"type": "transcript", "text": "...", "is_final": false, "confidence": 0.92}
  {"type": "transcript", "text": "...", "is_final": true, "confidence": 0.97}
  {"type": "vad", "event": "speech_start", "timestamp": 1708000000.123}
  {"type": "vad", "event": "speech_end", "timestamp": 1708000002.456}
```

### WebSocket: TTS Audio Output

```
Client -> TTS Service (ws://localhost:8002/ws/synthesize)

Client sends:
  {"type": "synthesize", "text": "Hello there.", "voice_id": "p225"}
  {"type": "cancel"}

TTS -> Client:
  Binary frames: PCM audio chunks (same format as STT input)
  {"type": "synthesis_start", "text": "Hello there."}
  {"type": "synthesis_end", "duration_ms": 1234}
```

### HTTP: Gateway API

```
POST /message
  Headers: Authorization: Bearer <token>
  Body: {"text": "...", "session_id": "...", "metadata": {...}}
  Response: {"response": "...", "emotion": "neutral", "latency_ms": 1234}

POST /interrupt
  Headers: Authorization: Bearer <token>
  Body: {"session_id": "..."}
  Response: {"status": "interrupted"}

GET /health
  Response: {"status": "healthy", "services": {...}, "uptime": 12345}

GET /session/:id
  Response: {"session_id": "...", "state": "...", "history": [...]}
```

---

## Technology Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| STT Engine | faster-whisper | CTranslate2 backend is 4x faster than original Whisper; supports streaming-friendly chunked processing; MIT license |
| TTS Engine | Coqui VITS (primary) | VITS model is fast enough for real-time (<300ms); good voice quality; multi-speaker support; open-source |
| TTS Fallback | Piper | Extremely fast inference via ONNX; good for low-latency scenarios; lower voice quality than Coqui |
| Facial Animation | Audio2Face-3D SDK | Industry-standard quality; runs in UE plugin; MIT licensed code; NVIDIA OML for weights |
| Render Engine | Unreal Engine 5 | MetaHuman support; LiveLink for real-time animation; highest visual fidelity available |
| Video Output | OBS Studio | Universal virtual camera support; compositing; overlays; streaming capability; GPLv2 |
| Event Bus | Redis pub/sub | Sub-millisecond latency; lightweight; well-understood; sufficient for single-machine deployment |
| Container Runtime | Docker + NVIDIA CTK | GPU passthrough to containers; reproducible builds; service isolation |
| Orchestrator | Custom (zeus-gateway) | Full control over timing, barge-in, and streaming behavior; no off-the-shelf solution fits the real-time avatar use case |
| Audio Format | PCM 16-bit 16kHz mono | Universal format for speech processing; no codec overhead; Whisper native format |
| Inter-service Protocol | WebSocket + Redis | WebSocket for streaming audio; Redis pub/sub for events; HTTP for request-response |

---

## Deployment Topology

The recommended deployment is **single-machine** to minimize network latency:

```
+─────────────────────────────────────────────────────────────────+
|  Ubuntu 22.04/24.04 Workstation                                 |
|  NVIDIA RTX 3060+ (12GB+ VRAM)                                 |
|  32GB RAM                                                        |
|                                                                  |
|  ┌──────────────────────────────────────────────────────────┐   |
|  │  Docker (GPU-enabled via nvidia-container-toolkit)        │   |
|  │                                                           │   |
|  │  redis ─── stt-service ─── zeus-gateway ─── tts-service  │   |
|  │                                      │                    │   |
|  │                                 a2f-bridge                │   |
|  │                                                           │   |
|  │  operator-console                                         │   |
|  └──────────────────────────────────────────────────────────┘   |
|                                                                  |
|  Unreal Engine 5 (native, not containerized)                    |
|  OBS Studio (native, not containerized)                         |
|  Zoom / Teams / Meet (native)                                   |
+──────────────────────────────────────────────────────────────────+
```

Unreal Engine and OBS run natively (not in Docker) because they require direct
access to the GPU display pipeline, window system, and virtual device drivers.

---

## VRAM Budget (Estimated)

| Component | VRAM Usage | Notes |
|-----------|-----------|-------|
| faster-whisper base.en | ~500 MB | Scales with model size |
| Coqui VITS | ~800 MB | ~1.5 GB for XTTS |
| Audio2Face SDK (UE plugin) | ~1 GB | Runs inside UE process |
| Unreal Engine (MetaHuman) | ~3-4 GB | At 1080p with one MetaHuman |
| OBS NVENC encoding | ~500 MB | If using hardware encoding |
| **Total** | **~6-7 GB** | Fits on RTX 3060 12GB |

For RTX 3060 (12GB), use `base.en` STT model and Coqui VITS. For RTX 4090
(24GB), you can use `large-v3` STT and XTTS for maximum quality.
