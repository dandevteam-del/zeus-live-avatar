"""
Zeus Live Avatar — STT (Speech-to-Text) Microservice

WebSocket server that accepts streaming 16kHz mono PCM audio, runs VAD
for speech boundary detection, transcribes with faster-whisper on GPU,
and returns partial/final transcripts plus barge-in events.

Coordinates with other Zeus services via Redis pub/sub event bus.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import signal
import struct
import sys
import threading
import time
import wave
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Optional

import numpy as np
import redis.asyncio as aioredis
import websockets
from faster_whisper import WhisperModel

from vad import VADProcessor

# ─── Structured JSON Logging ────────────────────────────────────────────────

class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "service": "stt-service",
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


logger = logging.getLogger("stt-service")
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JSONFormatter())
logger.addHandler(handler)
logger.setLevel(getattr(logging, os.environ.get("LOG_LEVEL", "info").upper(), logging.INFO))


# ─── Configuration ───────────────────────────────────────────────────────────

STT_HOST: str = os.environ.get("STT_HOST", "0.0.0.0")
STT_PORT: int = int(os.environ.get("STT_PORT", "8001"))
STT_MODEL_SIZE: str = os.environ.get("STT_MODEL_SIZE", "base.en")
STT_DEVICE: str = os.environ.get("STT_DEVICE", "cuda")
STT_COMPUTE_TYPE: str = os.environ.get("STT_COMPUTE_TYPE", "float16")
STT_SILENCE_DURATION_MS: int = int(os.environ.get("STT_SILENCE_DURATION_MS", "800"))
STT_VAD_THRESHOLD: float = float(os.environ.get("STT_VAD_THRESHOLD", "0.5"))

REDIS_HOST: str = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT: int = int(os.environ.get("REDIS_PORT", "6379"))
REDIS_PASSWORD: str = os.environ.get("REDIS_PASSWORD", "")

SAMPLE_RATE: int = 16000
FRAME_DURATION_MS: int = 30
FRAME_SAMPLES: int = SAMPLE_RATE * FRAME_DURATION_MS // 1000  # 480 samples
FRAME_BYTES: int = FRAME_SAMPLES * 2  # 16-bit = 2 bytes per sample

# ─── Health Check HTTP Server ────────────────────────────────────────────────

_service_healthy = False


class HealthHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler for health checks."""

    def do_GET(self) -> None:
        if self.path == "/health" and _service_healthy:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "healthy", "service": "stt"}).encode())
        else:
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "unhealthy", "service": "stt"}).encode())

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress default HTTP logging; we use our own logger
        pass


def start_health_server(port: int) -> None:
    """Run the health check HTTP server in a daemon thread."""
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="health-http")
    thread.start()
    logger.info(f"Health check server listening on port {port}")


# ─── Redis Connection with Reconnection ─────────────────────────────────────

class RedisEventBus:
    """
    Manages Redis pub/sub connections with automatic reconnection
    and exponential backoff.
    """

    def __init__(self, host: str, port: int, password: str) -> None:
        self._host = host
        self._port = port
        self._password = password
        self._client: Optional[aioredis.Redis] = None
        self._pubsub: Optional[aioredis.client.PubSub] = None
        self._connected = False
        self._reconnect_delay = 1.0
        self._max_reconnect_delay = 30.0
        self._zeus_is_speaking = False
        self._listener_task: Optional[asyncio.Task] = None

    async def connect(self) -> None:
        """Establish Redis connection with retry logic."""
        while True:
            try:
                self._client = aioredis.Redis(
                    host=self._host,
                    port=self._port,
                    password=self._password or None,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_keepalive=True,
                    retry_on_timeout=True,
                )
                await self._client.ping()
                self._connected = True
                self._reconnect_delay = 1.0
                logger.info("Connected to Redis", extra={"host": self._host, "port": self._port})
                break
            except Exception as exc:
                logger.warning(
                    f"Redis connection failed, retrying in {self._reconnect_delay:.1f}s: {exc}"
                )
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(
                    self._reconnect_delay * 2, self._max_reconnect_delay
                )

    async def start_listening(self) -> None:
        """Subscribe to Zeus speaking channel and listen for state changes."""
        if self._client is None:
            return

        try:
            self._pubsub = self._client.pubsub()
            await self._pubsub.subscribe("zeus:speaking")
            self._listener_task = asyncio.create_task(self._listen_loop())
            logger.info("Subscribed to zeus:speaking channel")
        except Exception as exc:
            logger.error(f"Failed to subscribe to Redis channels: {exc}")

    async def _listen_loop(self) -> None:
        """Listen for Redis pub/sub messages."""
        assert self._pubsub is not None
        try:
            async for message in self._pubsub.listen():
                if message["type"] == "message":
                    channel = message["channel"]
                    data = message["data"]
                    if channel == "zeus:speaking":
                        self._zeus_is_speaking = data.lower() in ("true", "1", "yes")
                        logger.debug(f"Zeus speaking state: {self._zeus_is_speaking}")
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.error(f"Redis listener error: {exc}")
            # Trigger reconnection
            self._connected = False
            await self._reconnect()

    async def _reconnect(self) -> None:
        """Reconnect after a connection failure."""
        logger.info("Attempting Redis reconnection...")
        if self._pubsub:
            try:
                await self._pubsub.close()
            except Exception:
                pass
        await self.connect()
        await self.start_listening()

    async def publish(self, channel: str, message: str) -> None:
        """Publish a message, reconnecting if necessary."""
        for attempt in range(3):
            try:
                if self._client is None or not self._connected:
                    await self.connect()
                assert self._client is not None
                await self._client.publish(channel, message)
                return
            except Exception as exc:
                logger.warning(f"Redis publish failed (attempt {attempt + 1}): {exc}")
                self._connected = False
                await asyncio.sleep(0.5 * (attempt + 1))
        logger.error(f"Failed to publish to {channel} after 3 attempts")

    @property
    def zeus_is_speaking(self) -> bool:
        return self._zeus_is_speaking

    async def close(self) -> None:
        """Shut down Redis connections."""
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        if self._pubsub:
            try:
                await self._pubsub.close()
            except Exception:
                pass
        if self._client:
            try:
                await self._client.close()
            except Exception:
                pass


# ─── Whisper Model Manager ───────────────────────────────────────────────────

class WhisperTranscriber:
    """
    Manages the faster-whisper model and provides transcription of
    PCM audio buffers.
    """

    def __init__(self, model_size: str, device: str, compute_type: str) -> None:
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._model: Optional[WhisperModel] = None

    def load(self) -> None:
        """Load the whisper model (blocking — call before async loop starts)."""
        logger.info(
            f"Loading faster-whisper model: size={self._model_size}, "
            f"device={self._device}, compute_type={self._compute_type}"
        )
        start = time.monotonic()
        self._model = WhisperModel(
            self._model_size,
            device=self._device,
            compute_type=self._compute_type,
        )
        elapsed = time.monotonic() - start
        logger.info(f"Whisper model loaded in {elapsed:.2f}s")

    def transcribe(self, pcm_audio: np.ndarray) -> tuple[str, float]:
        """
        Transcribe a numpy PCM audio array.

        Args:
            pcm_audio: float32 numpy array of audio samples, normalized to [-1, 1].

        Returns:
            Tuple of (transcribed_text, average_confidence).
        """
        if self._model is None:
            raise RuntimeError("Whisper model not loaded — call load() first")

        if len(pcm_audio) == 0:
            return "", 0.0

        # faster-whisper expects float32 array
        segments, info = self._model.transcribe(
            pcm_audio,
            beam_size=1,
            language="en",
            vad_filter=False,  # We do our own VAD
            without_timestamps=True,
        )

        texts: list[str] = []
        confidences: list[float] = []
        for segment in segments:
            texts.append(segment.text.strip())
            confidences.append(segment.avg_logprob)

        full_text = " ".join(texts).strip()
        # Convert avg_logprob to a rough confidence score (0-1)
        avg_confidence = 0.0
        if confidences:
            avg_logprob = sum(confidences) / len(confidences)
            # logprob is negative; closer to 0 = more confident
            # Map roughly: -0.0 -> 1.0, -1.0 -> 0.37, -2.0 -> 0.14
            avg_confidence = min(1.0, max(0.0, np.exp(avg_logprob)))

        return full_text, float(avg_confidence)


# ─── Audio Buffer Utilities ──────────────────────────────────────────────────

def pcm_bytes_to_float32(pcm_bytes: bytes) -> np.ndarray:
    """Convert 16-bit signed LE PCM bytes to float32 numpy array normalized to [-1, 1]."""
    samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
    samples /= 32768.0
    return samples


# ─── WebSocket Client Handler ────────────────────────────────────────────────

class STTClientHandler:
    """
    Handles a single WebSocket client connection. Receives streaming PCM
    audio, runs VAD, and emits transcription events.
    """

    def __init__(
        self,
        websocket: websockets.WebSocketServerProtocol,
        transcriber: WhisperTranscriber,
        event_bus: RedisEventBus,
    ) -> None:
        self._ws = websocket
        self._transcriber = transcriber
        self._event_bus = event_bus
        self._audio_buffer = bytearray()  # Accumulates PCM for current speech segment
        self._frame_buffer = bytearray()  # Accumulates incoming bytes into VAD frames
        self._vad = VADProcessor(
            sample_rate=SAMPLE_RATE,
            frame_duration_ms=FRAME_DURATION_MS,
            aggressiveness=2,
            speech_frames_threshold=5,
            silence_threshold_ms=STT_SILENCE_DURATION_MS,
        )
        self._running = True
        self._partial_text = ""
        self._transcription_lock = asyncio.Lock()
        self._loop = asyncio.get_event_loop()

    async def handle(self) -> None:
        """Main loop: receive audio frames and process through VAD + transcription."""
        client_addr = self._ws.remote_address
        logger.info(f"Client connected: {client_addr}")

        try:
            async for message in self._ws:
                if not self._running:
                    break

                if isinstance(message, bytes):
                    await self._process_audio(message)
                elif isinstance(message, str):
                    await self._process_control(message)
        except websockets.exceptions.ConnectionClosed as exc:
            logger.info(f"Client disconnected: {client_addr} (code={exc.code})")
        except Exception as exc:
            logger.error(f"Error handling client {client_addr}: {exc}", exc_info=True)
            await self._send_error(str(exc))
        finally:
            # If there's buffered audio from an in-progress speech segment, transcribe it
            if len(self._audio_buffer) > 0:
                await self._finalize_segment()
            logger.info(f"Client handler finished: {client_addr}")

    async def _process_audio(self, data: bytes) -> None:
        """Buffer incoming audio into VAD-sized frames and process each."""
        self._frame_buffer.extend(data)

        while len(self._frame_buffer) >= FRAME_BYTES:
            frame = bytes(self._frame_buffer[:FRAME_BYTES])
            del self._frame_buffer[:FRAME_BYTES]

            result = self._vad.process_frame(frame)

            # Emit VAD state changes
            if result.speech_start:
                await self._send_event({"type": "vad", "speaking": True})

                # Barge-in detection
                if self._event_bus.zeus_is_speaking:
                    timestamp_ms = int(time.time() * 1000)
                    await self._send_event({"type": "barge_in", "timestamp": timestamp_ms})
                    await self._event_bus.publish("zeus:barge_in", str(timestamp_ms))
                    logger.info("Barge-in detected — user spoke while Zeus was speaking")

            if result.speech_end:
                await self._send_event({"type": "vad", "speaking": False})

            # Accumulate audio during speech
            if result.speaking or result.speech_start:
                self._audio_buffer.extend(frame)

                # Periodically run partial transcription for long utterances
                # Every ~1.5 seconds of speech audio (50 frames * 30ms)
                if len(self._audio_buffer) >= FRAME_BYTES * 50:
                    await self._run_partial_transcription()

            # Speech ended — finalize segment
            if result.speech_end and len(self._audio_buffer) > 0:
                await self._finalize_segment()

    async def _process_control(self, message: str) -> None:
        """Handle JSON control messages from the client."""
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            await self._send_error("Invalid JSON")
            return

        msg_type = data.get("type")
        if msg_type == "reset":
            self._audio_buffer.clear()
            self._frame_buffer.clear()
            self._vad.reset()
            self._partial_text = ""
            logger.debug("Client requested reset")
        elif msg_type == "ping":
            await self._send_event({"type": "pong", "timestamp": int(time.time() * 1000)})
        else:
            await self._send_error(f"Unknown control message type: {msg_type}")

    async def _run_partial_transcription(self) -> None:
        """Run transcription on the current audio buffer for partial results."""
        async with self._transcription_lock:
            pcm_float = pcm_bytes_to_float32(bytes(self._audio_buffer))
            try:
                text, confidence = await asyncio.wait_for(
                    self._loop.run_in_executor(None, self._transcriber.transcribe, pcm_float),
                    timeout=30.0,
                )
            except asyncio.TimeoutError:
                logger.error("Partial transcription timed out after 30s")
                return
            except Exception as exc:
                logger.error(f"Partial transcription error: {exc}")
                return

            if text and text != self._partial_text:
                self._partial_text = text
                await self._send_event({
                    "type": "partial",
                    "text": text,
                    "is_final": False,
                })

    async def _finalize_segment(self) -> None:
        """Transcribe the complete speech segment and emit final result."""
        async with self._transcription_lock:
            if len(self._audio_buffer) == 0:
                return

            pcm_float = pcm_bytes_to_float32(bytes(self._audio_buffer))
            self._audio_buffer.clear()
            self._partial_text = ""

            try:
                text, confidence = await asyncio.wait_for(
                    self._loop.run_in_executor(None, self._transcriber.transcribe, pcm_float),
                    timeout=30.0,
                )
            except asyncio.TimeoutError:
                logger.error("Final transcription timed out after 30s")
                await self._send_error("Transcription timed out")
                return
            except Exception as exc:
                logger.error(f"Final transcription error: {exc}")
                await self._send_error(f"Transcription failed: {exc}")
                return

            if text:
                await self._send_event({
                    "type": "final",
                    "text": text,
                    "is_final": True,
                    "confidence": round(confidence, 4),
                })

                # Publish turn-complete to Redis for downstream services
                await self._event_bus.publish(
                    "zeus:user_turn_complete",
                    json.dumps({"text": text, "confidence": confidence, "timestamp": time.time()}),
                )
                logger.info(f"Final transcript: \"{text}\" (confidence={confidence:.3f})")

    async def _send_event(self, event: dict[str, Any]) -> None:
        """Send a JSON event to the WebSocket client."""
        try:
            await self._ws.send(json.dumps(event))
        except websockets.exceptions.ConnectionClosed:
            self._running = False
        except Exception as exc:
            logger.error(f"Failed to send event: {exc}")
            self._running = False

    async def _send_error(self, message: str) -> None:
        """Send an error event to the client."""
        await self._send_event({"type": "error", "message": message})


# ─── Server Setup ────────────────────────────────────────────────────────────

class STTServer:
    """
    Main STT server that manages the WebSocket endpoint, Whisper model,
    and Redis event bus.
    """

    def __init__(self) -> None:
        self._transcriber = WhisperTranscriber(
            model_size=STT_MODEL_SIZE,
            device=STT_DEVICE,
            compute_type=STT_COMPUTE_TYPE,
        )
        self._event_bus = RedisEventBus(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD,
        )
        self._shutdown_event = asyncio.Event()
        self._server: Optional[websockets.WebSocketServer] = None

    async def start(self) -> None:
        """Initialize resources and start the WebSocket server."""
        global _service_healthy

        # Load whisper model (blocking)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._transcriber.load)

        # Connect to Redis
        await self._event_bus.connect()
        await self._event_bus.start_listening()

        # Start health check HTTP server on port + 1000 (separate from WebSocket)
        health_port = STT_PORT + 1000
        start_health_server(health_port)

        _service_healthy = True
        logger.info(f"STT service ready — WebSocket on ws://{STT_HOST}:{STT_PORT}/ws, health on :{health_port}")

        # Start WebSocket server
        self._server = await websockets.serve(
            self._handle_connection,
            STT_HOST,
            STT_PORT,
            ping_interval=20,
            ping_timeout=20,
            max_size=2**20,  # 1MB max message size
            max_queue=32,
        )

        # Wait for shutdown signal
        await self._shutdown_event.wait()

    async def _handle_connection(
        self,
        websocket: websockets.WebSocketServerProtocol,
        path: str,
    ) -> None:
        """Handle a new WebSocket connection."""
        # Accept connections on /ws or / (be lenient)
        if path not in ("/ws", "/"):
            await websocket.close(4004, "Not Found — connect to /ws")
            return

        handler = STTClientHandler(
            websocket=websocket,
            transcriber=self._transcriber,
            event_bus=self._event_bus,
        )
        await handler.handle()

    async def shutdown(self) -> None:
        """Gracefully shut down the server."""
        global _service_healthy

        logger.info("Shutting down STT service...")
        _service_healthy = False

        if self._server:
            self._server.close()
            await self._server.wait_closed()

        await self._event_bus.close()
        self._shutdown_event.set()
        logger.info("STT service shut down complete")


# ─── Entry Point ─────────────────────────────────────────────────────────────

def main() -> None:
    """Entry point: set up signal handlers and run the server."""
    server = STTServer()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Signal handlers for graceful shutdown
    def handle_signal(signum: int, frame: Any) -> None:
        logger.info(f"Received signal {signum}, initiating shutdown")
        loop.call_soon_threadsafe(lambda: asyncio.ensure_future(server.shutdown()))

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    try:
        loop.run_until_complete(server.start())
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received")
        loop.run_until_complete(server.shutdown())
    finally:
        # Clean up pending tasks
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()
        logger.info("Event loop closed")


if __name__ == "__main__":
    main()
