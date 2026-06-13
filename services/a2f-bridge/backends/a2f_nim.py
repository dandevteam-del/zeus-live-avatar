"""
NVIDIA Audio2Face NIM Backend (Optional).

Connects to the NVIDIA Audio2Face NIM container via gRPC to get
ML-based blendshape weights from audio. This produces significantly
higher quality lip sync than the open-source SDK backend.

Requirements:
    - NGC credentials (NGC_API_KEY env var)
    - NVIDIA AI Enterprise license
    - Audio2Face NIM container running (see docs/LICENSES.md)
    - grpcio and grpcio-tools packages installed

See: https://docs.nvidia.com/ace/latest/modules/a2f-docs/index.html
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray

logger = logging.getLogger("zeus.a2f_nim")

# NIM connection config
NIM_HOST: str = os.getenv("A2F_NIM_HOST", "localhost")
NIM_PORT: int = int(os.getenv("A2F_NIM_PORT", "50051"))
NIM_API_KEY: str = os.getenv("NGC_API_KEY", "")

# Audio format
SAMPLE_RATE: int = 16000
CHANNELS: int = 1


@dataclass
class NIMBlendshapeClient:
    """
    Client for NVIDIA Audio2Face NIM gRPC service.

    Sends audio chunks to the NIM container and receives ARKit-compatible
    blendshape weights in return.

    Requires NGC credentials and NVIDIA AI Enterprise license.
    See docs/LICENSES.md for licensing details.
    """

    host: str = NIM_HOST
    port: int = NIM_PORT
    api_key: str = NIM_API_KEY
    _channel: Any = None  # grpc.aio.Channel — typed as Any to avoid hard dep
    _stub: Any = None     # Generated gRPC stub
    _connected: bool = False

    async def connect(self) -> None:
        """
        Establish gRPC connection to the NIM container.

        TODO: Implement when NIM container is available.
              Requires generated proto stubs from NVIDIA ACE SDK.
        """
        if not self.api_key:
            logger.error(
                "NGC_API_KEY not set. Cannot connect to Audio2Face NIM. "
                "Set NGC_API_KEY env var or use A2F_BACKEND=sdk for the "
                "open-source backend."
            )
            return

        try:
            # TODO: Import generated gRPC stubs
            # from nvidia_ace.a2f.v1 import audio2face_pb2, audio2face_pb2_grpc
            # import grpc

            # TODO: Create authenticated gRPC channel
            # metadata = [("authorization", f"Bearer {self.api_key}")]
            # self._channel = grpc.aio.insecure_channel(f"{self.host}:{self.port}")
            # self._stub = audio2face_pb2_grpc.Audio2FaceServiceStub(self._channel)

            logger.info(
                "NIM backend stub initialized (host=%s:%d). "
                "Full implementation requires NVIDIA ACE SDK proto stubs.",
                self.host,
                self.port,
            )
            # self._connected = True

        except ImportError:
            logger.error(
                "grpcio not installed. Install with: pip install grpcio grpcio-tools"
            )
        except Exception as exc:
            logger.error("Failed to connect to NIM: %s", exc)

    async def disconnect(self) -> None:
        """Close the gRPC channel."""
        if self._channel:
            await self._channel.close()
            self._channel = None
            self._stub = None
            self._connected = False
            logger.info("NIM gRPC channel closed")

    async def process_audio_chunk(
        self,
        pcm_bytes: bytes,
        dt: float = 1.0 / 60.0,
    ) -> dict[str, Any] | None:
        """
        Send audio to NIM and receive blendshape weights.

        Args:
            pcm_bytes: Raw PCM audio (16kHz, 16-bit signed LE, mono).
            dt: Delta time (unused, for API compatibility with SDK backend).

        Returns:
            Dict with 'blendshapes' and 'head_rotation', or None if unavailable.

        TODO: Implement the actual gRPC call when NIM container is deployed.
              The expected flow is:
              1. Create AudioRequest proto with PCM data
              2. Send via stub.ProcessAudio() unary or streaming RPC
              3. Parse BlendshapeResponse proto into our dict format
              4. Map NIM's blendshape names to ARKit standard names
        """
        if not self._connected:
            logger.debug("NIM not connected, returning None")
            return None

        try:
            # TODO: Build and send gRPC request
            # request = audio2face_pb2.AudioRequest(
            #     audio_data=pcm_bytes,
            #     sample_rate=SAMPLE_RATE,
            #     num_channels=CHANNELS,
            # )
            # response = await self._stub.ProcessAudio(request)
            #
            # # Parse response into our format
            # blendshapes = {}
            # for bs in response.blendshapes:
            #     blendshapes[bs.name] = float(bs.weight)
            #
            # head_rotation = {
            #     "pitch": float(response.head_pose.pitch),
            #     "yaw": float(response.head_pose.yaw),
            #     "roll": float(response.head_pose.roll),
            # }
            #
            # return {
            #     "blendshapes": blendshapes,
            #     "head_rotation": head_rotation,
            # }

            logger.debug("NIM process_audio_chunk: stub — returning None")
            return None

        except Exception as exc:
            logger.error("NIM processing error: %s", exc)
            return None

    def reset(self) -> None:
        """Reset internal state (if any)."""
        pass
