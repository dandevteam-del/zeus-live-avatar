"""
Zeus Brain Client — Connects the gateway to the Zeus AI brain.

Supports both HTTP POST (simple request-response) and WebSocket (streaming)
communication modes. Falls back gracefully from WS to HTTP if streaming
is unavailable.

Sends messages in CanonicalMessage format so the brain can route through
the standard triage pipeline.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

import httpx
import websockets
from websockets.exceptions import (
    ConnectionClosed,
    InvalidURI,
    WebSocketException,
)

logger = logging.getLogger("zeus.brain_client")

ZEUS_BRAIN_URL: str = os.getenv("ZEUS_BRAIN_URL", "http://localhost:3000")
ZEUS_BRAIN_WS_URL: str = os.getenv(
    "ZEUS_BRAIN_WS_URL",
    ZEUS_BRAIN_URL.replace("http://", "ws://").replace("https://", "wss://") + "/ws",
)
BRAIN_TIMEOUT: float = float(os.getenv("BRAIN_TIMEOUT", "30"))
BRAIN_MAX_RETRIES: int = int(os.getenv("BRAIN_MAX_RETRIES", "3"))
BRAIN_RETRY_BASE_DELAY: float = float(os.getenv("BRAIN_RETRY_BASE_DELAY", "1.0"))


@dataclass
class BrainResponse:
    """Encapsulates a response from the Zeus brain."""
    request_id: str
    text: str
    is_streaming: bool = False
    error: str | None = None
    latency_ms: float = 0.0


def build_canonical_message(
    text: str,
    mode: str = "conversation",
    user_id: str = "avatar-session",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a CanonicalMessage payload for the Zeus brain."""
    msg: dict[str, Any] = {
        "channel": "avatar",
        "user_id": user_id,
        "text": text,
        "metadata": {
            "mode": mode,
            "source": "zeus-gateway",
            "timestamp": time.time(),
            **(metadata or {}),
        },
    }
    return msg


class ZeusBrainClient:
    """
    Client for communicating with the Zeus AI brain.

    Supports HTTP POST for simple request/response and WebSocket for
    streaming token-by-token responses.
    """

    def __init__(self) -> None:
        self._http_client: httpx.AsyncClient | None = None
        self._ws_available: bool = True  # Assume WS until proven otherwise

    async def startup(self) -> None:
        """Initialize the HTTP client."""
        self._http_client = httpx.AsyncClient(
            base_url=ZEUS_BRAIN_URL,
            timeout=httpx.Timeout(BRAIN_TIMEOUT, connect=10.0),
        )
        logger.info("Brain client initialized: url=%s", ZEUS_BRAIN_URL)

    async def shutdown(self) -> None:
        """Close the HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        logger.info("Brain client shut down")

    async def send_message(
        self,
        text: str,
        mode: str = "conversation",
        request_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> BrainResponse:
        """
        Send a message to the Zeus brain via HTTP POST with retry logic.

        Args:
            text: The user's message text.
            mode: Conversation mode (meeting, webinar, training, conversation).
            request_id: Optional request ID for tracking.
            metadata: Additional metadata to include.

        Returns:
            BrainResponse with the AI's reply.
        """
        request_id = request_id or str(uuid.uuid4())
        payload = build_canonical_message(text, mode=mode, metadata=metadata)

        last_error: Exception | None = None
        start_time = time.monotonic()

        for attempt in range(1, BRAIN_MAX_RETRIES + 1):
            try:
                if not self._http_client:
                    await self.startup()

                assert self._http_client is not None
                response = await self._http_client.post("/message", json=payload)
                response.raise_for_status()

                data = response.json()
                elapsed_ms = (time.monotonic() - start_time) * 1000

                response_text = data.get("text") or data.get("response") or data.get("content", "")
                if not response_text:
                    logger.warning("Brain returned empty response: %s", data)
                    response_text = ""

                logger.info(
                    "Brain response: request_id=%s latency=%.0fms length=%d",
                    request_id,
                    elapsed_ms,
                    len(response_text),
                )

                return BrainResponse(
                    request_id=request_id,
                    text=response_text,
                    is_streaming=False,
                    latency_ms=elapsed_ms,
                )

            except httpx.HTTPStatusError as exc:
                last_error = exc
                logger.warning(
                    "Brain HTTP error (attempt %d/%d): status=%d",
                    attempt,
                    BRAIN_MAX_RETRIES,
                    exc.response.status_code,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                last_error = exc
                logger.warning(
                    "Brain request error (attempt %d/%d): %s",
                    attempt,
                    BRAIN_MAX_RETRIES,
                    exc,
                )
            except Exception as exc:
                last_error = exc
                logger.error(
                    "Brain unexpected error (attempt %d/%d): %s",
                    attempt,
                    BRAIN_MAX_RETRIES,
                    exc,
                )

            if attempt < BRAIN_MAX_RETRIES:
                delay = BRAIN_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.info("Retrying in %.1fs...", delay)
                await asyncio.sleep(delay)

        elapsed_ms = (time.monotonic() - start_time) * 1000
        error_msg = f"Brain request failed after {BRAIN_MAX_RETRIES} attempts: {last_error}"
        logger.error(error_msg)

        return BrainResponse(
            request_id=request_id,
            text="",
            error=error_msg,
            latency_ms=elapsed_ms,
        )

    async def stream_message(
        self,
        text: str,
        mode: str = "conversation",
        request_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Stream a response from the Zeus brain via WebSocket.

        Yields dicts with keys: type ("token", "done", "error"), text, request_id.
        Falls back to HTTP POST if WS is unavailable.

        Args:
            text: The user's message text.
            mode: Conversation mode.
            request_id: Optional request ID.
            metadata: Additional metadata.

        Yields:
            Dicts with streaming response tokens.
        """
        request_id = request_id or str(uuid.uuid4())
        payload = build_canonical_message(text, mode=mode, metadata=metadata)
        payload["request_id"] = request_id

        if not self._ws_available:
            # Fall back to HTTP
            result = await self.send_message(text, mode, request_id, metadata)
            if result.error:
                yield {"type": "error", "text": result.error, "request_id": request_id}
            else:
                # Emit the full response as a single token batch
                yield {"type": "token", "text": result.text, "request_id": request_id}
                yield {"type": "done", "text": result.text, "request_id": request_id}
            return

        try:
            async with websockets.connect(
                ZEUS_BRAIN_WS_URL,
                open_timeout=10,
                close_timeout=5,
            ) as ws:
                await ws.send(json.dumps(payload))

                async for raw_msg in ws:
                    try:
                        msg = json.loads(raw_msg)
                    except json.JSONDecodeError:
                        # Treat raw text as a token
                        yield {"type": "token", "text": str(raw_msg), "request_id": request_id}
                        continue

                    msg_type = msg.get("type", "token")
                    if msg_type in ("token", "chunk"):
                        yield {
                            "type": "token",
                            "text": msg.get("text", msg.get("content", "")),
                            "request_id": request_id,
                        }
                    elif msg_type in ("done", "end", "complete"):
                        yield {
                            "type": "done",
                            "text": msg.get("text", msg.get("full_text", "")),
                            "request_id": request_id,
                        }
                        return
                    elif msg_type == "error":
                        yield {
                            "type": "error",
                            "text": msg.get("message", msg.get("error", "Unknown brain error")),
                            "request_id": request_id,
                        }
                        return

        except (ConnectionClosed, InvalidURI, WebSocketException, OSError) as exc:
            logger.warning("Brain WS unavailable (%s), falling back to HTTP", exc)
            self._ws_available = False

            # Fall back to HTTP
            result = await self.send_message(text, mode, request_id, metadata)
            if result.error:
                yield {"type": "error", "text": result.error, "request_id": request_id}
            else:
                yield {"type": "token", "text": result.text, "request_id": request_id}
                yield {"type": "done", "text": result.text, "request_id": request_id}

        except Exception as exc:
            logger.error("Brain stream error: %s", exc, exc_info=True)
            yield {
                "type": "error",
                "text": f"Brain stream error: {exc}",
                "request_id": request_id,
            }
