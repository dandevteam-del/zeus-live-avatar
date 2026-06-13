"""
Zeus Live Avatar — TTS (Text-to-Speech) Microservice

WebSocket server that accepts text synthesis requests and streams back
PCM audio chunks with interleaved JSON metadata. Supports Coqui TTS and
Piper TTS engines, barge-in interruption via Redis, and sentence-level
progressive streaming.

Coordinates with other Zeus services via Redis pub/sub event bus.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Optional, Union

import numpy as np
import redis.asyncio as aioredis
import websockets

# ─── Structured JSON Logging ────────────────────────────────────────────────

class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "service": "tts-service",
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


logger = logging.getLogger("tts-service")
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JSONFormatter())
logger.addHandler(handler)
logger.setLevel(getattr(logging, os.environ.get("LOG_LEVEL", "info").upper(), logging.INFO))


# ─── Configuration ───────────────────────────────────────────────────────────

TTS_HOST: str = os.environ.get("TTS_HOST", "0.0.0.0")
TTS_PORT: int = int(os.environ.get("TTS_PORT", "8002"))
TTS_ENGINE: str = os.environ.get("TTS_ENGINE", "coqui")

# Coqui settings
COQUI_MODEL_NAME: str = os.environ.get("COQUI_MODEL_NAME", "tts_models/en/vctk/vits")
COQUI_SPEAKER_ID: str = os.environ.get("COQUI_SPEAKER_ID", "p225")
COQUI_USE_CUDA: bool = os.environ.get("COQUI_USE_CUDA", "true").lower() in ("true", "1", "yes")

# Piper settings
PIPER_MODEL_PATH: str = os.environ.get("PIPER_MODEL_PATH", "/models/en_US-lessac-medium.onnx")
PIPER_CONFIG_PATH: str = os.environ.get("PIPER_CONFIG_PATH", "/models/en_US-lessac-medium.onnx.json")
PIPER_SPEAKER_ID: int = int(os.environ.get("PIPER_SPEAKER_ID", "0"))

# Redis
REDIS_HOST: str = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT: int = int(os.environ.get("REDIS_PORT", "6379"))
REDIS_PASSWORD: str = os.environ.get("REDIS_PASSWORD", "")

# Audio
DEFAULT_CHUNK_SIZE: int = 4096  # samples per chunk


# ─── Health Check HTTP Server ────────────────────────────────────────────────

_service_healthy = False


class HealthHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler for health checks."""

    def do_GET(self) -> None:
        if self.path == "/health" and _service_healthy:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "healthy", "service": "tts"}).encode())
        else:
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "unhealthy", "service": "tts"}).encode())

    def log_message(self, format: str, *args: Any) -> None:
        pass


def start_health_server(port: int) -> None:
    """Run the health check HTTP server in a daemon thread."""
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="health-http")
    thread.start()
    logger.info(f"Health check server listening on port {port}")


# ─── Redis Event Bus with Reconnection ──────────────────────────────────────

class RedisEventBus:
    """
    Manages Redis pub/sub connections with automatic reconnection
    and exponential backoff. Listens for stop/barge-in signals.
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
        self._listener_task: Optional[asyncio.Task] = None

        # Callbacks for stop/barge-in events
        self._on_stop_callbacks: list[asyncio.Event] = []
        self._on_barge_in_callbacks: list[asyncio.Event] = []

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
        """Subscribe to stop and barge-in channels."""
        if self._client is None:
            return

        try:
            self._pubsub = self._client.pubsub()
            await self._pubsub.subscribe("zeus:stop_talking", "zeus:barge_in")
            self._listener_task = asyncio.create_task(self._listen_loop())
            logger.info("Subscribed to zeus:stop_talking and zeus:barge_in channels")
        except Exception as exc:
            logger.error(f"Failed to subscribe to Redis channels: {exc}")

    async def _listen_loop(self) -> None:
        """Listen for Redis pub/sub messages."""
        assert self._pubsub is not None
        try:
            async for message in self._pubsub.listen():
                if message["type"] == "message":
                    channel = message["channel"]
                    if channel == "zeus:stop_talking":
                        logger.info("Received stop_talking signal via Redis")
                        for event in self._on_stop_callbacks:
                            event.set()
                    elif channel == "zeus:barge_in":
                        logger.info("Received barge_in signal via Redis")
                        for event in self._on_barge_in_callbacks:
                            event.set()
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.error(f"Redis listener error: {exc}")
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

    def register_stop_event(self, event: asyncio.Event) -> None:
        """Register an asyncio.Event to be set when stop_talking is received."""
        self._on_stop_callbacks.append(event)

    def unregister_stop_event(self, event: asyncio.Event) -> None:
        """Remove a registered stop event."""
        try:
            self._on_stop_callbacks.remove(event)
        except ValueError:
            pass

    def register_barge_in_event(self, event: asyncio.Event) -> None:
        """Register an asyncio.Event to be set on barge_in."""
        self._on_barge_in_callbacks.append(event)

    def unregister_barge_in_event(self, event: asyncio.Event) -> None:
        """Remove a registered barge-in event."""
        try:
            self._on_barge_in_callbacks.remove(event)
        except ValueError:
            pass

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


# ─── Engine Factory ──────────────────────────────────────────────────────────

def create_engine(engine_type: str) -> Any:
    """
    Factory function to create the appropriate TTS engine based on config.

    Returns an engine instance (not yet loaded — call .load() separately).
    """
    if engine_type == "coqui":
        from engines.coqui_engine import CoquiEngine
        return CoquiEngine(
            model_name=COQUI_MODEL_NAME,
            speaker_id=COQUI_SPEAKER_ID or None,
            use_cuda=COQUI_USE_CUDA,
            chunk_size=DEFAULT_CHUNK_SIZE,
        )
    elif engine_type == "piper":
        from engines.piper_engine import PiperEngine
        return PiperEngine(
            model_path=PIPER_MODEL_PATH,
            config_path=PIPER_CONFIG_PATH,
            speaker_id=PIPER_SPEAKER_ID,
            chunk_size=DEFAULT_CHUNK_SIZE,
        )
    else:
        raise ValueError(f"Unknown TTS engine: {engine_type}. Supported: coqui, piper")


# ─── WebSocket Client Handler ────────────────────────────────────────────────

class TTSClientHandler:
    """
    Handles a single WebSocket client connection. Receives text synthesis
    requests and streams back PCM audio chunks with metadata.
    """

    def __init__(
        self,
        websocket: websockets.WebSocketServerProtocol,
        engine: Any,
        event_bus: RedisEventBus,
    ) -> None:
        self._ws = websocket
        self._engine = engine
        self._event_bus = event_bus
        self._running = True
        self._synthesis_lock = asyncio.Lock()
        self._stop_event = asyncio.Event()
        self._barge_in_event = asyncio.Event()
        self._current_stream_id: Optional[str] = None

    async def handle(self) -> None:
        """Main loop: receive synthesis requests and stream audio back."""
        client_addr = self._ws.remote_address
        logger.info(f"Client connected: {client_addr}")

        # Register for Redis stop/barge-in events
        self._event_bus.register_stop_event(self._stop_event)
        self._event_bus.register_barge_in_event(self._barge_in_event)

        try:
            async for message in self._ws:
                if not self._running:
                    break

                if isinstance(message, str):
                    await self._process_message(message)
                else:
                    await self._send_error("Expected JSON text message, got binary")
        except websockets.exceptions.ConnectionClosed as exc:
            logger.info(f"Client disconnected: {client_addr} (code={exc.code})")
        except Exception as exc:
            logger.error(f"Error handling client {client_addr}: {exc}", exc_info=True)
            await self._send_json({"type": "error", "message": str(exc)})
        finally:
            self._event_bus.unregister_stop_event(self._stop_event)
            self._event_bus.unregister_barge_in_event(self._barge_in_event)
            logger.info(f"Client handler finished: {client_addr}")

    async def _process_message(self, raw: str) -> None:
        """Parse and dispatch a JSON message from the client."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            await self._send_error("Invalid JSON")
            return

        msg_type = data.get("type")

        if msg_type == "synthesize":
            text = data.get("text", "")
            voice = data.get("voice", "default")
            stream_id = data.get("stream_id", f"stream-{int(time.time() * 1000)}")

            if not text.strip():
                await self._send_error("Empty text in synthesize request")
                return

            await self._run_synthesis(text, stream_id)

        elif msg_type == "stop":
            await self._handle_stop()

        elif msg_type == "config":
            # Config messages can adjust voice/sample_rate for the session
            # Currently informational — engine selection is at startup
            logger.info(f"Config message received: {data}")
            await self._send_json({
                "type": "meta",
                "stream_id": "config",
                "status": "acknowledged",
                "sample_rate": self._engine.sample_rate,
            })

        elif msg_type == "ping":
            await self._send_json({"type": "pong", "timestamp": int(time.time() * 1000)})

        else:
            await self._send_error(f"Unknown message type: {msg_type}")

    async def _run_synthesis(self, text: str, stream_id: str) -> None:
        """
        Run TTS synthesis with concurrent safety, stop/barge-in support.
        """
        async with self._synthesis_lock:
            self._current_stream_id = stream_id
            self._stop_event.clear()
            self._barge_in_event.clear()

            # Publish speaking state
            await self._event_bus.publish("zeus:speaking", "true")
            logger.info(f"Starting synthesis: stream_id={stream_id}, text='{text[:80]}...'")

            try:
                async for chunk in self._engine.synthesize_stream(text, stream_id):
                    if not self._running:
                        break

                    # Check for stop/barge-in between chunks
                    if self._stop_event.is_set() or self._barge_in_event.is_set():
                        reason = "barge_in" if self._barge_in_event.is_set() else "stop"
                        logger.info(
                            f"Synthesis interrupted ({reason}): stream_id={stream_id}"
                        )
                        self._engine.stop()

                        # Send flush frame (empty binary) to signal end
                        await self._send_binary(b"")
                        await self._send_json({
                            "type": "meta",
                            "stream_id": stream_id,
                            "status": "interrupted",
                            "reason": reason,
                        })
                        break

                    if isinstance(chunk, bytes):
                        await self._send_binary(chunk)
                    elif isinstance(chunk, dict):
                        await self._send_json(chunk)

            except Exception as exc:
                logger.error(f"Synthesis error: {exc}", exc_info=True)
                await self._send_json({
                    "type": "error",
                    "message": f"Synthesis failed: {exc}",
                    "stream_id": stream_id,
                })
            finally:
                # Always publish that we stopped speaking
                await self._event_bus.publish("zeus:speaking", "false")
                self._current_stream_id = None

    async def _handle_stop(self) -> None:
        """Handle a stop request from the client."""
        logger.info("Client requested stop")
        self._stop_event.set()
        self._engine.stop()

    async def _send_json(self, data: dict[str, Any]) -> None:
        """Send a JSON text message to the client."""
        try:
            await self._ws.send(json.dumps(data))
        except websockets.exceptions.ConnectionClosed:
            self._running = False
        except Exception as exc:
            logger.error(f"Failed to send JSON: {exc}")
            self._running = False

    async def _send_binary(self, data: bytes) -> None:
        """Send a binary message to the client."""
        try:
            await self._ws.send(data)
        except websockets.exceptions.ConnectionClosed:
            self._running = False
        except Exception as exc:
            logger.error(f"Failed to send binary: {exc}")
            self._running = False

    async def _send_error(self, message: str) -> None:
        """Send an error event to the client."""
        await self._send_json({"type": "error", "message": message})


# ─── Server Setup ────────────────────────────────────────────────────────────

class TTSServer:
    """
    Main TTS server that manages the WebSocket endpoint, TTS engine,
    and Redis event bus.
    """

    def __init__(self) -> None:
        self._engine = create_engine(TTS_ENGINE)
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

        # Load TTS model (blocking)
        loop = asyncio.get_event_loop()
        logger.info(f"Initializing TTS engine: {TTS_ENGINE}")
        await loop.run_in_executor(None, self._engine.load)

        # Connect to Redis
        await self._event_bus.connect()
        await self._event_bus.start_listening()

        # Start health check HTTP server on port + 1000 (separate from WebSocket)
        health_port = TTS_PORT + 1000
        start_health_server(health_port)

        _service_healthy = True
        logger.info(
            f"TTS service ready — WebSocket on ws://{TTS_HOST}:{TTS_PORT}/ws, "
            f"health on :{health_port} (engine={TTS_ENGINE}, sample_rate={self._engine.sample_rate})"
        )

        # Start WebSocket server
        self._server = await websockets.serve(
            self._handle_connection,
            TTS_HOST,
            TTS_PORT,
            ping_interval=20,
            ping_timeout=20,
            max_size=2**20,  # 1MB max message
            max_queue=16,
        )

        # Wait for shutdown signal
        await self._shutdown_event.wait()

    async def _handle_connection(
        self,
        websocket: websockets.WebSocketServerProtocol,
        path: str,
    ) -> None:
        """Handle a new WebSocket connection."""
        if path not in ("/ws", "/"):
            await websocket.close(4004, "Not Found — connect to /ws")
            return

        handler = TTSClientHandler(
            websocket=websocket,
            engine=self._engine,
            event_bus=self._event_bus,
        )
        await handler.handle()

    async def shutdown(self) -> None:
        """Gracefully shut down the server."""
        global _service_healthy

        logger.info("Shutting down TTS service...")
        _service_healthy = False

        if self._server:
            self._server.close()
            await self._server.wait_closed()

        await self._event_bus.close()
        self._shutdown_event.set()
        logger.info("TTS service shut down complete")


# ─── Entry Point ─────────────────────────────────────────────────────────────

def main() -> None:
    """Entry point: set up signal handlers and run the server."""
    server = TTSServer()
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
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()
        logger.info("Event loop closed")


if __name__ == "__main__":
    main()
