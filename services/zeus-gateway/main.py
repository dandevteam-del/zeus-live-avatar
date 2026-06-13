"""
Zeus Gateway — FastAPI bridge between the Zeus Brain and the live avatar pipeline.

Routes user speech (from STT) through the AI brain, applies human-like timing,
and streams responses to TTS/operator console. Manages conversation state,
kill-switch, and Redis event bus integration.

Endpoints:
    GET  /health          — Health check
    WS   /ws              — Main conversation WebSocket
    POST /control/stop    — Kill switch
    POST /control/reset   — Reset conversation
    POST /control/mode    — Set conversation mode
    GET  /control/state   — Current state
    POST /message         — Inject text message via HTTP
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import redis.asyncio as aioredis
from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from brain_client import ZeusBrainClient
from timing import HumanTimingEngine

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
GATEWAY_AUTH_TOKEN: str = os.getenv("GATEWAY_AUTH_TOKEN", "zeus-dev-token")
REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
GATEWAY_PORT: int = int(os.getenv("GATEWAY_PORT", "8000"))

# Timing defaults
TIMING_SIMPLE_MIN: int = int(os.getenv("TIMING_SIMPLE_MIN", "200"))
TIMING_SIMPLE_MAX: int = int(os.getenv("TIMING_SIMPLE_MAX", "600"))
TIMING_COMPLEX_MIN: int = int(os.getenv("TIMING_COMPLEX_MIN", "700"))
TIMING_COMPLEX_MAX: int = int(os.getenv("TIMING_COMPLEX_MAX", "1200"))
TIMING_PREFACE_RATE_LIMIT: int = int(os.getenv("TIMING_PREFACE_RATE_LIMIT", "3"))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=LOG_LEVEL,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("zeus.gateway")


# ---------------------------------------------------------------------------
# Enums & Models
# ---------------------------------------------------------------------------

class Mode(str, Enum):
    MEETING = "meeting"
    WEBINAR = "webinar"
    TRAINING = "training"
    CONVERSATION = "conversation"


class Turn(str, Enum):
    USER = "user"
    ZEUS = "zeus"
    IDLE = "idle"


class Status(str, Enum):
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    PAUSED = "paused"
    STOPPED = "stopped"


class ModeRequest(BaseModel):
    mode: Mode


class MessageRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000)
    mode: Mode | None = None
    metadata: dict[str, Any] | None = None


class StateResponse(BaseModel):
    mode: str
    turn: str
    status: str
    is_stopped: bool
    history_length: int
    current_request_id: str | None


class ControlResponse(BaseModel):
    ok: bool
    message: str


# ---------------------------------------------------------------------------
# Conversation State
# ---------------------------------------------------------------------------

@dataclass
class ConversationState:
    """Tracks the full conversation state for the avatar session."""

    mode: Mode = Mode.CONVERSATION
    turn: Turn = Turn.IDLE
    status: Status = Status.LISTENING
    history: list[dict[str, Any]] = field(default_factory=list)
    current_request_id: str | None = None
    is_stopped: bool = False
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "turn": self.turn.value,
            "status": self.status.value,
            "is_stopped": self.is_stopped,
            "history_length": len(self.history),
            "current_request_id": self.current_request_id,
        }

    def add_message(self, role: str, content: str) -> None:
        self.history.append({
            "role": role,
            "content": content,
            "timestamp": time.time(),
        })
        # Keep history bounded to avoid memory leaks
        if len(self.history) > 200:
            self.history = self.history[-100:]

    def reset(self) -> None:
        self.turn = Turn.IDLE
        self.status = Status.LISTENING
        self.history.clear()
        self.current_request_id = None
        self.is_stopped = False


# ---------------------------------------------------------------------------
# WebSocket Connection Manager
# ---------------------------------------------------------------------------

class ConnectionManager:
    """Manages active WebSocket connections for broadcasting."""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.add(ws)
        logger.info("WS connected: total=%d", len(self._connections))

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(ws)
        logger.info("WS disconnected: total=%d", len(self._connections))

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Send a message to all connected WebSocket clients."""
        payload = json.dumps(message)
        async with self._lock:
            dead: list[WebSocket] = []
            for ws in self._connections:
                try:
                    await ws.send_text(payload)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self._connections.discard(ws)

    async def send_to(self, ws: WebSocket, message: dict[str, Any]) -> None:
        """Send a message to a specific WebSocket client."""
        try:
            await ws.send_text(json.dumps(message))
        except Exception:
            logger.warning("Failed to send to WS client")

    @property
    def count(self) -> int:
        return len(self._connections)


# ---------------------------------------------------------------------------
# Globals (initialized in lifespan)
# ---------------------------------------------------------------------------

state = ConversationState()
manager = ConnectionManager()
brain = ZeusBrainClient()
timing = HumanTimingEngine(
    simple_range=(TIMING_SIMPLE_MIN, TIMING_SIMPLE_MAX),
    complex_range=(TIMING_COMPLEX_MIN, TIMING_COMPLEX_MAX),
    preface_rate_limit=TIMING_PREFACE_RATE_LIMIT,
)
redis_client: aioredis.Redis | None = None
_redis_subscriber_task: asyncio.Task | None = None
_shutdown_event = asyncio.Event()


# ---------------------------------------------------------------------------
# Redis Event Bus
# ---------------------------------------------------------------------------

async def redis_subscriber() -> None:
    """Subscribe to Redis channels and process events."""
    global redis_client

    while not _shutdown_event.is_set():
        try:
            redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
            pubsub = redis_client.pubsub()
            await pubsub.subscribe(
                "zeus:user_turn_complete",
                "zeus:barge_in",
            )
            logger.info("Redis subscriber connected: %s", REDIS_URL)

            async for message in pubsub.listen():
                if _shutdown_event.is_set():
                    break
                if message["type"] != "message":
                    continue

                channel = message["channel"]
                try:
                    data = json.loads(message["data"]) if isinstance(message["data"], str) else message["data"]
                except (json.JSONDecodeError, TypeError):
                    data = {"raw": message["data"]}

                logger.info("Redis event: channel=%s", channel)

                if channel == "zeus:user_turn_complete":
                    text = data.get("text", "")
                    if text:
                        asyncio.create_task(
                            handle_user_message(text, source="redis")
                        )

                elif channel == "zeus:barge_in":
                    await handle_barge_in()

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

    if redis_client:
        await redis_client.close()
        redis_client = None


async def redis_publish(channel: str, data: dict[str, Any]) -> None:
    """Publish a message to Redis, silently failing if unavailable."""
    if redis_client is None:
        return
    try:
        await redis_client.publish(channel, json.dumps(data))
    except Exception as exc:
        logger.warning("Redis publish failed: channel=%s err=%s", channel, exc)


# ---------------------------------------------------------------------------
# Core Message Handling
# ---------------------------------------------------------------------------

async def handle_user_message(
    text: str,
    source: str = "ws",
    ws: WebSocket | None = None,
) -> None:
    """
    Process a user message: update state, query brain, stream response.

    Args:
        text: The user's transcript text.
        source: Origin of the message (ws, http, redis).
        ws: Optional WebSocket to send directed responses.
    """
    async with state._lock:
        if state.is_stopped:
            logger.info("Kill switch active, ignoring message from %s", source)
            if ws:
                await manager.send_to(ws, {
                    "type": "error",
                    "message": "Kill switch is active. Send /control/reset to resume.",
                })
            return

        request_id = str(uuid.uuid4())
        state.turn = Turn.ZEUS
        state.status = Status.THINKING
        state.current_request_id = request_id
        state.add_message("user", text)

    # Broadcast state change
    await broadcast_state()

    # Get timing for human-like delay
    # We don't have the response yet, so estimate based on user text only
    estimated_delay = timing.calculate_delay("", text)

    # Broadcast thinking indicator
    await manager.broadcast({
        "type": "thinking",
        "delay_ms": estimated_delay.delay_ms,
        "request_id": request_id,
    })

    # Apply thinking delay
    await asyncio.sleep(estimated_delay.delay_ms / 1000.0)

    # Check kill switch again after delay
    if state.is_stopped or state.current_request_id != request_id:
        logger.info("Request %s superseded or stopped during thinking", request_id)
        return

    # Broadcast response start
    await manager.broadcast({
        "type": "response_start",
        "request_id": request_id,
    })

    async with state._lock:
        state.status = Status.SPEAKING

    await broadcast_state()
    await redis_publish("zeus:speaking", {"speaking": True, "request_id": request_id})

    # Stream response from brain
    full_text_parts: list[str] = []
    had_error = False

    try:
        async for chunk in brain.stream_message(
            text=text,
            mode=state.mode.value,
            request_id=request_id,
        ):
            # Abort if kill switch triggered or request superseded
            if state.is_stopped or state.current_request_id != request_id:
                logger.info("Aborting stream for request %s", request_id)
                break

            chunk_type = chunk.get("type")

            if chunk_type == "token":
                token_text = chunk.get("text", "")
                if token_text:
                    # Prepend preface to first token if applicable
                    if not full_text_parts and estimated_delay.use_preface and estimated_delay.preface_text:
                        token_text = estimated_delay.preface_text + " " + token_text

                    full_text_parts.append(token_text)

                    await manager.broadcast({
                        "type": "response_token",
                        "text": token_text,
                        "request_id": request_id,
                    })

                    await redis_publish("zeus:response_text", {
                        "text": token_text,
                        "request_id": request_id,
                        "is_final": False,
                    })

            elif chunk_type == "done":
                done_text = chunk.get("text", "")
                if done_text and not full_text_parts:
                    # Full response came at once (HTTP fallback)
                    if estimated_delay.use_preface and estimated_delay.preface_text:
                        done_text = estimated_delay.preface_text + " " + done_text
                    full_text_parts.append(done_text)

                    await manager.broadcast({
                        "type": "response_token",
                        "text": done_text,
                        "request_id": request_id,
                    })

            elif chunk_type == "error":
                had_error = True
                error_msg = chunk.get("text", "Unknown error")
                logger.error("Brain error for request %s: %s", request_id, error_msg)
                await manager.broadcast({
                    "type": "error",
                    "message": error_msg,
                    "request_id": request_id,
                })

    except Exception as exc:
        had_error = True
        logger.error("Stream processing error: %s", exc, exc_info=True)
        await manager.broadcast({
            "type": "error",
            "message": f"Gateway error: {exc}",
            "request_id": request_id,
        })

    # Finalize
    full_text = "".join(full_text_parts)

    # Calculate response latency
    response_latency_ms = int((time.time() - (state.history[-1].get("timestamp", time.time()) if state.history else time.time())) * 1000)
    await redis_publish("zeus:latency", {"ms": response_latency_ms, "request_id": request_id})

    if full_text and not had_error:
        state.add_message("assistant", full_text)

        await manager.broadcast({
            "type": "response_end",
            "request_id": request_id,
            "full_text": full_text,
        })

        await redis_publish("zeus:response_ready", {
            "text": full_text,
            "request_id": request_id,
        })

        await redis_publish("zeus:response_text", {
            "text": full_text,
            "request_id": request_id,
            "is_final": True,
        })
    elif had_error:
        await redis_publish("zeus:error", {
            "request_id": request_id,
            "message": "Response processing failed",
        })

    # Return to listening state
    async with state._lock:
        if state.current_request_id == request_id:
            state.turn = Turn.IDLE
            state.status = Status.LISTENING
            state.current_request_id = None

    await broadcast_state()
    await redis_publish("zeus:speaking", {"speaking": False, "request_id": request_id})


async def handle_barge_in() -> None:
    """Handle user barge-in: stop current response immediately."""
    logger.info("Barge-in detected, stopping current response")

    async with state._lock:
        state.status = Status.LISTENING
        state.turn = Turn.IDLE
        old_request_id = state.current_request_id
        state.current_request_id = None  # Invalidate current request

    await manager.broadcast({
        "type": "control",
        "action": "stop",
        "reason": "barge_in",
        "request_id": old_request_id,
    })

    await redis_publish("zeus:stop_talking", {"reason": "barge_in"})
    await broadcast_state()


async def broadcast_state() -> None:
    """Broadcast current conversation state to all WS clients."""
    await manager.broadcast({
        "type": "state",
        **state.to_dict(),
    })


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

async def verify_auth_token(request: Request) -> None:
    """Verify Bearer token on control endpoints."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )
    token = auth_header[len("Bearer "):]
    if token != GATEWAY_AUTH_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid token",
        )


def verify_ws_token(token: str | None) -> bool:
    """Verify WebSocket auth token from query param."""
    if not token:
        return False
    return token == GATEWAY_AUTH_TOKEN


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    """Application lifespan: startup and shutdown."""
    global _redis_subscriber_task

    logger.info("Zeus Gateway starting up...")

    # Start brain client
    await brain.startup()

    # Start Redis subscriber
    _redis_subscriber_task = asyncio.create_task(redis_subscriber())

    logger.info(
        "Zeus Gateway ready: port=%d mode=%s",
        GATEWAY_PORT,
        state.mode.value,
    )

    yield

    # Shutdown
    logger.info("Zeus Gateway shutting down...")
    _shutdown_event.set()

    if _redis_subscriber_task:
        _redis_subscriber_task.cancel()
        try:
            await _redis_subscriber_task
        except asyncio.CancelledError:
            pass

    await brain.shutdown()

    if redis_client:
        await redis_client.close()

    logger.info("Zeus Gateway shut down cleanly")


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Zeus Gateway",
    description="Bridge between Zeus Brain and the live avatar pipeline",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict[str, Any]:
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "zeus-gateway",
        "version": "1.0.0",
        "connections": manager.count,
        "mode": state.mode.value,
        "is_stopped": state.is_stopped,
        "redis_connected": redis_client is not None,
    }


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(
    ws: WebSocket,
    token: str | None = Query(default=None),
) -> None:
    """
    Main conversation WebSocket.

    Input messages:
        {"type": "user_transcript", "text": "...", "is_final": true}
        {"type": "control", "action": "stop"|"reset"|"mode", "value": "..."}

    Output messages:
        {"type": "response_start", "request_id": "..."}
        {"type": "response_token", "text": "...", "request_id": "..."}
        {"type": "response_end", "request_id": "...", "full_text": "..."}
        {"type": "thinking", "delay_ms": 450}
        {"type": "state", ...}
        {"type": "error", "message": "..."}
    """
    if not verify_ws_token(token):
        await ws.close(code=4001, reason="Unauthorized")
        return

    await manager.connect(ws)

    # Send initial state
    await manager.send_to(ws, {"type": "state", **state.to_dict()})

    try:
        while True:
            raw = await ws.receive_text()

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await manager.send_to(ws, {
                    "type": "error",
                    "message": "Invalid JSON",
                })
                continue

            msg_type = msg.get("type")

            if msg_type == "user_transcript":
                text = msg.get("text", "").strip()
                is_final = msg.get("is_final", True)

                if not text:
                    continue

                if not is_final:
                    # Partial transcript — broadcast for display but don't process
                    await manager.broadcast({
                        "type": "partial_transcript",
                        "text": text,
                    })
                    continue

                # Final transcript — process through brain
                logger.info("User transcript: %s", text[:100])
                asyncio.create_task(
                    handle_user_message(text, source="ws", ws=ws)
                )

            elif msg_type == "control":
                action = msg.get("action")
                value = msg.get("value")

                if action == "stop":
                    await _do_kill_switch("ws_control")
                    await manager.send_to(ws, {
                        "type": "control",
                        "action": "stop",
                        "ok": True,
                    })

                elif action == "reset":
                    await _do_reset()
                    await manager.send_to(ws, {
                        "type": "control",
                        "action": "reset",
                        "ok": True,
                    })

                elif action == "mode":
                    if value and value in Mode.__members__.values():
                        await _do_set_mode(Mode(value))
                        await manager.send_to(ws, {
                            "type": "control",
                            "action": "mode",
                            "ok": True,
                            "mode": value,
                        })
                    else:
                        valid = [m.value for m in Mode]
                        await manager.send_to(ws, {
                            "type": "error",
                            "message": f"Invalid mode. Valid: {valid}",
                        })

                else:
                    await manager.send_to(ws, {
                        "type": "error",
                        "message": f"Unknown control action: {action}",
                    })

            elif msg_type == "ping":
                await manager.send_to(ws, {"type": "pong"})

            else:
                await manager.send_to(ws, {
                    "type": "error",
                    "message": f"Unknown message type: {msg_type}",
                })

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected normally")
    except Exception as exc:
        logger.error("WebSocket error: %s", exc, exc_info=True)
    finally:
        await manager.disconnect(ws)


# ---------------------------------------------------------------------------
# Control Endpoints
# ---------------------------------------------------------------------------

async def _do_kill_switch(source: str = "api") -> None:
    """Execute the kill switch."""
    async with state._lock:
        state.is_stopped = True
        state.status = Status.STOPPED
        state.turn = Turn.IDLE
        old_request_id = state.current_request_id
        state.current_request_id = None

    logger.warning("KILL SWITCH activated from %s", source)

    await manager.broadcast({
        "type": "control",
        "action": "stop_talking",
        "reason": "kill_switch",
        "request_id": old_request_id,
    })

    await redis_publish("zeus:stop_talking", {"reason": "kill_switch", "source": source})
    await broadcast_state()


async def _do_reset() -> None:
    """Reset conversation state."""
    async with state._lock:
        state.reset()

    logger.info("Conversation reset")
    await broadcast_state()


async def _do_set_mode(mode: Mode) -> None:
    """Set conversation mode."""
    async with state._lock:
        state.mode = mode

    logger.info("Mode changed to %s", mode.value)
    await broadcast_state()


@app.post("/control/stop", dependencies=[Depends(verify_auth_token)])
async def control_stop() -> ControlResponse:
    """Kill switch — immediately stop all output."""
    await _do_kill_switch(source="api")
    return ControlResponse(ok=True, message="Kill switch activated. All output stopped.")


@app.post("/control/reset", dependencies=[Depends(verify_auth_token)])
async def control_reset() -> ControlResponse:
    """Reset conversation state and deactivate kill switch."""
    await _do_reset()
    return ControlResponse(ok=True, message="Conversation reset.")


@app.post("/control/mode", dependencies=[Depends(verify_auth_token)])
async def control_mode(req: ModeRequest) -> ControlResponse:
    """Set conversation mode."""
    await _do_set_mode(req.mode)
    return ControlResponse(ok=True, message=f"Mode set to {req.mode.value}.")


@app.get("/control/state")
async def control_state() -> StateResponse:
    """Get current conversation state."""
    return StateResponse(**state.to_dict())


# ---------------------------------------------------------------------------
# HTTP Message Injection
# ---------------------------------------------------------------------------

@app.post("/message", dependencies=[Depends(verify_auth_token)])
async def inject_message(req: MessageRequest) -> dict[str, Any]:
    """
    Inject a text message via HTTP (alternative to WebSocket).

    The response will be broadcast to all connected WS clients.
    Returns immediately with request_id; response streams on WS.
    """
    if state.is_stopped:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Kill switch is active. POST /control/reset first.",
        )

    request_id = str(uuid.uuid4())

    # Override mode if specified
    if req.mode:
        async with state._lock:
            state.mode = req.mode

    asyncio.create_task(
        handle_user_message(req.text, source="http")
    )

    return {
        "ok": True,
        "request_id": request_id,
        "message": "Message queued for processing. Listen on WS for response.",
    }


# ---------------------------------------------------------------------------
# Graceful Shutdown
# ---------------------------------------------------------------------------

def _handle_signal(sig: signal.Signals) -> None:
    logger.info("Received signal %s, initiating shutdown...", sig.name)
    _shutdown_event.set()


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    # Register signal handlers
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda s, _: _handle_signal(s))

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=GATEWAY_PORT,
        log_level=LOG_LEVEL.lower(),
        access_log=True,
    )
