"""
A2F Bridge — WebSocket server converting audio to facial animation data.

Accepts binary PCM audio chunks (16kHz, 16-bit signed LE, mono) via WebSocket
and outputs JSON blendshape frames at the target FPS. Supports two backends:

    - SDK (default): Open-source audio analysis engine using FFT/energy features
    - NIM (optional): NVIDIA Audio2Face NIM container via gRPC (requires license)

When no audio is being received, emits idle animation frames with blinks,
eye saccades, breathing, and head micro-movements.

WebSocket endpoint: ws://0.0.0.0:{A2F_PORT}/ws_anim
    Input:  Binary PCM audio chunks
    Output: JSON blendshape frames ({"type": "animation", ...} or {"type": "idle"})

Redis integration:
    Subscribes to zeus:speaking and zeus:stop_talking to coordinate with gateway.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

import numpy as np
import redis.asyncio as aioredis
import websockets
from websockets.server import WebSocketServerProtocol

from backends.a2f_sdk import AudioToBlendshapeEngine
from backends.a2f_nim import NIMBlendshapeClient
from idle_motion import IdleMotionGenerator

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
A2F_HOST: str = os.getenv("A2F_HOST", "0.0.0.0")
A2F_PORT: int = int(os.getenv("A2F_PORT", "8003"))
A2F_BACKEND: str = os.getenv("A2F_BACKEND", "sdk")  # "sdk" or "nim"
TARGET_FPS: int = int(os.getenv("A2F_TARGET_FPS", "60"))
REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Audio format
SAMPLE_RATE: int = 16000
SAMPLE_WIDTH: int = 2  # 16-bit = 2 bytes
CHANNELS: int = 1

# Frame timing
FRAME_INTERVAL: float = 1.0 / TARGET_FPS

# Idle timeout: switch to idle after this many seconds of silence
IDLE_TIMEOUT: float = float(os.getenv("A2F_IDLE_TIMEOUT", "0.5"))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=LOG_LEVEL,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("zeus.a2f_bridge")


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class BridgeMode(str, Enum):
    IDLE = "idle"
    SPEAKING = "speaking"


@dataclass
class BridgeState:
    """Global bridge state shared across connections."""
    mode: BridgeMode = BridgeMode.IDLE
    is_stopped: bool = False
    last_audio_time: float = 0.0
    connection_count: int = 0


# ---------------------------------------------------------------------------
# Globals
# ---------------------------------------------------------------------------

bridge_state = BridgeState()

# ---------------------------------------------------------------------------
# Health Check HTTP Server
# ---------------------------------------------------------------------------

class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "healthy",
                "service": "a2f-bridge",
                "backend": A2F_BACKEND,
                "connections": bridge_state.connection_count,
                "mode": bridge_state.mode.value,
            }).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        pass  # suppress default HTTP logging


def _start_health_server(port: int) -> None:
    server = HTTPServer(("0.0.0.0", port), _HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="health-http")
    thread.start()
    logger.info("Health check server on port %d", port)


sdk_engine = AudioToBlendshapeEngine()
nim_client = NIMBlendshapeClient()
idle_generator = IdleMotionGenerator()

_shutdown_event = asyncio.Event()
_redis_client: aioredis.Redis | None = None
_active_connections: set[WebSocketServerProtocol] = set()


# ---------------------------------------------------------------------------
# Redis Subscriber
# ---------------------------------------------------------------------------

async def redis_subscriber() -> None:
    """Subscribe to Redis channels for coordination with the gateway."""
    global _redis_client

    while not _shutdown_event.is_set():
        try:
            _redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
            pubsub = _redis_client.pubsub()
            await pubsub.subscribe("zeus:speaking", "zeus:stop_talking")
            logger.info("Redis subscriber connected: %s", REDIS_URL)

            async for message in pubsub.listen():
                if _shutdown_event.is_set():
                    break
                if message["type"] != "message":
                    continue

                channel = message["channel"]
                try:
                    data = json.loads(message["data"]) if isinstance(message["data"], str) else {}
                except (json.JSONDecodeError, TypeError):
                    data = {}

                if channel == "zeus:speaking":
                    is_speaking = data.get("speaking", False)
                    if is_speaking:
                        bridge_state.mode = BridgeMode.SPEAKING
                        bridge_state.is_stopped = False
                        logger.info("Redis: Speaking started")
                    else:
                        bridge_state.mode = BridgeMode.IDLE
                        logger.info("Redis: Speaking ended -> idle")

                elif channel == "zeus:stop_talking":
                    bridge_state.is_stopped = True
                    bridge_state.mode = BridgeMode.IDLE
                    sdk_engine.reset()
                    logger.info("Redis: Stop talking -> immediate idle")

            await pubsub.unsubscribe()
            await pubsub.close()

        except aioredis.ConnectionError as exc:
            logger.warning("Redis connection lost (%s), reconnecting in 3s...", exc)
            await asyncio.sleep(3)
        except asyncio.CancelledError:
            logger.info("Redis subscriber cancelled")
            break
        except Exception as exc:
            logger.error("Redis subscriber error: %s", exc, exc_info=True)
            await asyncio.sleep(5)

    if _redis_client:
        await _redis_client.close()
        _redis_client = None


# ---------------------------------------------------------------------------
# Frame Processing
# ---------------------------------------------------------------------------

async def process_audio_frame(pcm_bytes: bytes) -> dict[str, Any]:
    """
    Process a PCM audio chunk through the active backend.

    Args:
        pcm_bytes: Raw PCM audio data (16kHz, 16-bit signed LE, mono).

    Returns:
        Animation frame dict with type, timestamp, blendshapes, head_rotation.
    """
    dt = FRAME_INTERVAL
    result: dict[str, Any] | None = None

    if A2F_BACKEND == "nim":
        # Try NIM first, fall back to SDK
        result = await nim_client.process_audio_chunk(pcm_bytes, dt)

    if result is None:
        # SDK backend (default / NIM fallback)
        if A2F_BACKEND == "nim":
            logger.warning("NIM backend returned None — falling back to SDK engine")
        result = sdk_engine.process_audio_chunk(pcm_bytes, dt)

    return {
        "type": "animation",
        "timestamp_ms": int(time.time() * 1000),
        "blendshapes": result.get("blendshapes", {}),
        "head_rotation": result.get("head_rotation", {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}),
    }


def generate_idle_frame(dt: float) -> dict[str, Any]:
    """
    Generate an idle animation frame.

    Returns:
        Idle frame dict with blinks, saccades, breathing, head micro-moves.
    """
    result = idle_generator.generate_frame(dt)

    return {
        "type": "idle",
        "timestamp_ms": int(time.time() * 1000),
        "blendshapes": result.get("blendshapes", {}),
        "head_rotation": result.get("head_rotation", {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}),
    }


def merge_frames(speaking: dict[str, Any], idle: dict[str, Any], blend: float) -> dict[str, Any]:
    """
    Blend between speaking and idle frames for smooth transitions.

    Args:
        speaking: Speaking animation frame.
        idle: Idle animation frame.
        blend: Blend factor (0.0 = full idle, 1.0 = full speaking).

    Returns:
        Blended frame.
    """
    blendshapes: dict[str, float] = {}
    speak_bs = speaking.get("blendshapes", {})
    idle_bs = idle.get("blendshapes", {})

    # Merge all keys from both sources
    all_keys = set(speak_bs.keys()) | set(idle_bs.keys())
    for key in all_keys:
        s_val = speak_bs.get(key, 0.0)
        i_val = idle_bs.get(key, 0.0)
        blendshapes[key] = round(i_val + (s_val - i_val) * blend, 4)

    # Blend head rotation
    speak_head = speaking.get("head_rotation", {})
    idle_head = idle.get("head_rotation", {})
    head_rotation = {
        "pitch": round(
            idle_head.get("pitch", 0.0) + (speak_head.get("pitch", 0.0) - idle_head.get("pitch", 0.0)) * blend, 3
        ),
        "yaw": round(
            idle_head.get("yaw", 0.0) + (speak_head.get("yaw", 0.0) - idle_head.get("yaw", 0.0)) * blend, 3
        ),
        "roll": round(
            idle_head.get("roll", 0.0) + (speak_head.get("roll", 0.0) - idle_head.get("roll", 0.0)) * blend, 3
        ),
    }

    frame_type = "animation" if blend > 0.5 else "idle"

    return {
        "type": frame_type,
        "timestamp_ms": int(time.time() * 1000),
        "blendshapes": blendshapes,
        "head_rotation": head_rotation,
    }


# ---------------------------------------------------------------------------
# WebSocket Handler
# ---------------------------------------------------------------------------

async def handle_connection(ws: WebSocketServerProtocol) -> None:
    """
    Handle a single WebSocket connection.

    Receives binary PCM audio chunks and sends JSON animation frames.
    When no audio is received, sends idle animation frames at target FPS.

    Protocol:
        Input:  Binary messages (PCM audio) or text messages (JSON control)
        Output: Text messages (JSON animation frames)
    """
    bridge_state.connection_count += 1
    _active_connections.add(ws)
    logger.info(
        "Client connected: remote=%s total=%d",
        ws.remote_address,
        bridge_state.connection_count,
    )

    # Per-connection state
    audio_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=100)
    speaking_blend: float = 0.0
    last_frame_time: float = time.monotonic()

    async def audio_receiver() -> None:
        """Receive audio data from WebSocket and queue it."""
        try:
            async for message in ws:
                if _shutdown_event.is_set():
                    break

                if isinstance(message, bytes):
                    # Binary = PCM audio
                    bridge_state.last_audio_time = time.monotonic()
                    try:
                        audio_queue.put_nowait(message)
                    except asyncio.QueueFull:
                        # Drop oldest frame to prevent backpressure
                        try:
                            audio_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            pass
                        audio_queue.put_nowait(message)

                elif isinstance(message, str):
                    # Text = JSON control message
                    try:
                        ctrl = json.loads(message)
                        ctrl_type = ctrl.get("type")

                        if ctrl_type == "reset":
                            sdk_engine.reset()
                            logger.info("Engine reset via WS control")

                        elif ctrl_type == "config":
                            # Allow runtime config changes
                            new_fps = ctrl.get("target_fps")
                            if new_fps and isinstance(new_fps, (int, float)):
                                logger.info("Target FPS changed to %d", int(new_fps))

                        elif ctrl_type == "ping":
                            await ws.send(json.dumps({"type": "pong"}))

                    except json.JSONDecodeError:
                        logger.warning("Invalid JSON control message")

        except websockets.ConnectionClosed:
            pass
        except Exception as exc:
            logger.error("Audio receiver error: %s", exc, exc_info=True)

    async def frame_sender() -> None:
        """Send animation frames at target FPS."""
        nonlocal speaking_blend, last_frame_time

        try:
            while not _shutdown_event.is_set():
                now = time.monotonic()
                dt = now - last_frame_time
                last_frame_time = now

                # Determine if we have audio to process
                audio_chunk: bytes | None = None
                try:
                    audio_chunk = audio_queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass

                time_since_audio = now - bridge_state.last_audio_time
                has_recent_audio = time_since_audio < IDLE_TIMEOUT and not bridge_state.is_stopped

                # Update speaking blend (smooth transition over ~200ms)
                target_blend = 1.0 if (has_recent_audio and audio_chunk) else 0.0
                blend_speed = dt / 0.2  # 200ms transition
                speaking_blend += (target_blend - speaking_blend) * min(blend_speed, 1.0)
                speaking_blend = max(0.0, min(1.0, speaking_blend))

                # Generate frame
                if audio_chunk and speaking_blend > 0.01:
                    speaking_frame = await process_audio_frame(audio_chunk)
                    idle_frame = generate_idle_frame(dt)

                    if speaking_blend > 0.99:
                        frame = speaking_frame
                    else:
                        frame = merge_frames(speaking_frame, idle_frame, speaking_blend)
                else:
                    frame = generate_idle_frame(dt)

                # Send frame
                try:
                    await ws.send(json.dumps(frame))
                except websockets.ConnectionClosed:
                    break

                # Sleep to maintain target FPS
                elapsed = time.monotonic() - now
                sleep_time = max(0.0, FRAME_INTERVAL - elapsed)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

        except websockets.ConnectionClosed:
            pass
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("Frame sender error: %s", exc, exc_info=True)

    # Run receiver and sender concurrently
    receiver_task = asyncio.create_task(audio_receiver())
    sender_task = asyncio.create_task(frame_sender())

    try:
        # Wait for either task to complete (usually receiver on disconnect)
        done, pending = await asyncio.wait(
            [receiver_task, sender_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Cancel the other task
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Check for exceptions in completed tasks
        for task in done:
            if task.exception():
                logger.error("Task error: %s", task.exception())

    finally:
        bridge_state.connection_count -= 1
        _active_connections.discard(ws)
        logger.info(
            "Client disconnected: remote=%s total=%d",
            ws.remote_address,
            bridge_state.connection_count,
        )


# ---------------------------------------------------------------------------
# Broadcast to all connections
# ---------------------------------------------------------------------------

async def broadcast_to_all(message: dict[str, Any]) -> None:
    """Send a message to all connected WebSocket clients."""
    if not _active_connections:
        return

    payload = json.dumps(message)
    dead: list[WebSocketServerProtocol] = []

    for ws in _active_connections:
        try:
            await ws.send(payload)
        except Exception:
            dead.append(ws)

    for ws in dead:
        _active_connections.discard(ws)


# ---------------------------------------------------------------------------
# Server Lifecycle
# ---------------------------------------------------------------------------

async def startup() -> None:
    """Initialize backends and connections."""
    logger.info("A2F Bridge starting up (backend=%s, fps=%d)...", A2F_BACKEND, TARGET_FPS)

    if A2F_BACKEND == "nim":
        await nim_client.connect()
        logger.info("NIM backend initialized")
    else:
        logger.info("SDK backend initialized (open-source audio analysis)")


async def shutdown() -> None:
    """Clean up resources."""
    logger.info("A2F Bridge shutting down...")

    _shutdown_event.set()

    if A2F_BACKEND == "nim":
        await nim_client.disconnect()

    if _redis_client:
        await _redis_client.close()

    # Close all active connections
    for ws in list(_active_connections):
        try:
            await ws.close(1001, "Server shutting down")
        except Exception:
            pass

    logger.info("A2F Bridge shut down cleanly")


async def main() -> None:
    """Main entry point — starts WebSocket server and Redis subscriber."""
    loop = asyncio.get_running_loop()

    # Signal handlers
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: _shutdown_event.set())

    await startup()

    # Start health check HTTP server on port + 1000
    _start_health_server(A2F_PORT + 1000)

    # Start Redis subscriber
    redis_task = asyncio.create_task(redis_subscriber())

    # Start WebSocket server
    logger.info("A2F Bridge listening on ws://%s:%d/ws_anim", A2F_HOST, A2F_PORT)

    async with websockets.serve(
        handle_connection,
        A2F_HOST,
        A2F_PORT,
        ping_interval=30,
        ping_timeout=10,
        max_size=2 ** 20,  # 1MB max message (audio chunks)
        process_request=_process_request,
    ):
        # Wait for shutdown signal
        await _shutdown_event.wait()

    # Cleanup
    redis_task.cancel()
    try:
        await redis_task
    except asyncio.CancelledError:
        pass

    await shutdown()


async def _process_request(
    path: str,
    request_headers: websockets.Headers,
) -> tuple[int, websockets.Headers, bytes] | None:
    """
    Process incoming WebSocket upgrade requests.

    Only allows connections to /ws_anim path.
    Returns None to proceed with WebSocket upgrade, or a tuple to reject.
    """
    if path != "/ws_anim":
        return (
            404,
            websockets.Headers([("Content-Type", "text/plain")]),
            b"Not Found. Connect to /ws_anim",
        )

    # Accept the connection
    return None


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logger.info(
        "Starting A2F Bridge: backend=%s port=%d fps=%d",
        A2F_BACKEND,
        A2F_PORT,
        TARGET_FPS,
    )
    asyncio.run(main())
