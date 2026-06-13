# Zeus Live Avatar -- License Information

> Component license documentation for the Zeus Live Avatar system.
> Opulent Bots LLC -- All rights reserved.

---

## Zeus Live Avatar

The Zeus Live Avatar system itself is **proprietary software** owned by
Opulent Bots LLC. It is not open-source and may not be redistributed,
modified, or used without explicit authorization.

The system integrates several open-source and commercial components, each
under their own license terms as documented below.

---

## Open-Source Components

| Component | License | Source | Usage |
|-----------|---------|--------|-------|
| faster-whisper | MIT | [github.com/SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper) | Speech-to-text engine |
| CTranslate2 | MIT | [github.com/OpenNMT/CTranslate2](https://github.com/OpenNMT/CTranslate2) | Inference backend for faster-whisper |
| Coqui TTS | MPL-2.0 | [github.com/coqui-ai/TTS](https://github.com/coqui-ai/TTS) | Text-to-speech engine |
| Piper TTS | MIT | [github.com/rhasspy/piper](https://github.com/rhasspy/piper) | Alternative TTS engine |
| OBS Studio | GPLv2 | [github.com/obsproject/obs-studio](https://github.com/obsproject/obs-studio) | Virtual camera and compositing |
| obs-websocket | GPLv2 | [github.com/obsproject/obs-websocket](https://github.com/obsproject/obs-websocket) | OBS remote control (included in OBS 28+) |
| Redis | BSD-3-Clause | [redis.io](https://redis.io) | Event bus and ephemeral state |
| FastAPI | MIT | [fastapi.tiangolo.com](https://fastapi.tiangolo.com) | HTTP/WebSocket framework for Python services |
| Uvicorn | BSD-3-Clause | [github.com/encode/uvicorn](https://github.com/encode/uvicorn) | ASGI server |
| webrtcvad | MIT | [github.com/wiseman/py-webrtcvad](https://github.com/wiseman/py-webrtcvad) | Voice activity detection |
| v4l2loopback | GPLv2 | [github.com/umlaeute/v4l2loopback](https://github.com/umlaeute/v4l2loopback) | Virtual camera kernel module |
| Docker | Apache-2.0 | [docker.com](https://docker.com) | Container runtime |
| nginx | BSD-2-Clause | [nginx.org](https://nginx.org) | Reverse proxy (if used) |

### License Compliance Notes

**MPL-2.0 (Coqui TTS):** Mozilla Public License 2.0 requires that modifications
to MPL-licensed source files be made available under MPL-2.0. Our system uses
Coqui TTS as an unmodified dependency. If you modify Coqui TTS source files,
those modifications must be released under MPL-2.0.

**GPLv2 (OBS Studio, obs-websocket, v4l2loopback):** These components run as
separate executables/kernel modules. Our system interacts with them via their
documented APIs (virtual camera device, WebSocket protocol). We do not
distribute or link against GPLv2 code.

---

## Commercial / EULA Components

| Component | License | Source | Notes |
|-----------|---------|--------|-------|
| Unreal Engine 5 | Epic Games EULA | [unrealengine.com](https://unrealengine.com) | Free for projects under $1M gross revenue |
| MetaHuman | Epic Games EULA | [metahuman.unrealengine.com](https://metahuman.unrealengine.com) | Subject to UE EULA terms |
| NVIDIA CUDA Toolkit | NVIDIA EULA | [developer.nvidia.com/cuda-toolkit](https://developer.nvidia.com/cuda-toolkit) | Free for all uses |
| NVIDIA Container Toolkit | Apache-2.0 | [github.com/NVIDIA/nvidia-container-toolkit](https://github.com/NVIDIA/nvidia-container-toolkit) | GPU Docker access |

### Unreal Engine and MetaHuman

Unreal Engine 5 is free to use under the Epic Games EULA. Key terms:
- Free for learning, development, and internal use
- 5% royalty on gross revenue above $1,000,000 per product
- MetaHuman characters are licensed for use within Unreal Engine
- You may NOT use MetaHuman assets outside of Unreal Engine
- Full terms: [unrealengine.com/eula](https://www.unrealengine.com/en-US/eula/unreal)

---

## NVIDIA Audio2Face-3D Components

The Audio2Face-3D ecosystem has three distinct tiers with different licensing:

### Tier 1: Audio2Face-3D SDK and UE Plugin

| Aspect | License |
|--------|---------|
| Source code | MIT License |
| Model weights | NVIDIA Open Model License (OML) |
| Documentation | [developer.nvidia.com/audio2face-3d](https://developer.nvidia.com/audio2face-3d) |

The **code** (SDK, Unreal Engine plugin) is MIT-licensed, permitting commercial
use, modification, and redistribution with attribution.

The **model weights** are under the NVIDIA Open Model License, which permits:
- Research and academic use
- Commercial use (subject to OML terms)
- Redistribution of outputs (the generated blendshapes)

Check the current OML terms on the NVIDIA developer hub, as license terms
may be updated.

### Tier 2: Audio2Face-3D NIM Container

| Aspect | License |
|--------|---------|
| Container image | NVIDIA AI Enterprise |
| NGC access | Requires NGC API key |
| Documentation | [docs.nvidia.com/ace](https://docs.nvidia.com/ace/) |

The NIM (NVIDIA Inference Microservice) container is a commercial product:
- Requires NGC (NVIDIA GPU Cloud) credentials
- May require an NVIDIA AI Enterprise subscription for production use
- Free evaluation tier available for development
- Container runs as a gRPC microservice on port 50051

**Our system does NOT require the NIM container.** It is an optional upgrade
for higher-quality facial animation. The default configuration uses the
MIT-licensed SDK/plugin approach.

### Tier 3: Our Open-Source Fallback

The `a2f-bridge` service includes a pure audio-analysis fallback that uses
no NVIDIA ML models:
- Analyzes audio amplitude, pitch, and formants
- Generates approximate blendshape weights for visemes
- Fully open-source, no license restrictions
- Lower quality than ML-based approaches but functional
- Enabled by default with `A2F_BACKEND=sdk` in `.env`

---

## Piper TTS

The original [rhasspy/piper](https://github.com/rhasspy/piper) repository has
been archived by its maintainer. The project may have moved to a new location --
check the archive notice on the GitHub page for the current home.

Pre-trained voice models for Piper are available under various licenses.
Each voice model has its own license terms documented in its model card.
The `en_US-lessac-medium` voice used by default is licensed for
non-commercial research. Check the specific model card for commercial
use terms.

---

## Whisper Models

The Whisper model weights (used via faster-whisper/CTranslate2 conversion)
were originally released by OpenAI under the MIT license:
- [github.com/openai/whisper](https://github.com/openai/whisper)
- MIT license permits commercial use
- CTranslate2-converted weights inherit the same MIT license

---

## Summary Matrix

| Component | Commercial Use | Modification | Redistribution | Notes |
|-----------|:-----------:|:----------:|:-------------:|-------|
| faster-whisper | Yes | Yes | Yes | MIT |
| Coqui TTS | Yes | Yes (MPL) | Yes (MPL) | MPL-2.0 for modified files |
| Piper TTS | Yes | Yes | Yes | MIT code; check voice model licenses |
| OBS Studio | Yes | Yes (GPL) | Yes (GPL) | We use as separate executable |
| Redis | Yes | Yes | Yes | BSD-3 |
| FastAPI | Yes | Yes | Yes | MIT |
| Unreal Engine | Yes* | No | No | *5% royalty over $1M |
| MetaHuman | Yes* | Limited | No | *Within UE only, subject to EULA |
| A2F SDK code | Yes | Yes | Yes | MIT |
| A2F model weights | Yes* | No | Yes* | *NVIDIA OML terms apply |
| A2F NIM container | License req. | No | No | NVIDIA AI Enterprise |
| CUDA Toolkit | Yes | No | Limited | NVIDIA EULA |

---

## Maintaining This Document

This document should be updated whenever:
- A new dependency is added to any service
- A dependency version changes that affects licensing
- NVIDIA updates the Audio2Face-3D licensing terms
- The project's revenue crosses the UE royalty threshold

Last reviewed: 2026-02-20
