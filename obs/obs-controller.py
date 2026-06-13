#!/usr/bin/env python3
"""
Zeus Live Avatar — OBS Controller

Connects to OBS Studio via obs-websocket (built into OBS 28+) and automates
avatar streaming. Subscribes to Redis event channels for real-time control
and accepts manual stdin commands.

OBS 28+ includes obs-websocket by default.
See: https://github.com/obsproject/obs-websocket
No separate plugin installation needed for OBS 28+.

Usage:
    python obs-controller.py

Environment variables:
    OBS_WS_HOST       - OBS WebSocket host (default: localhost)
    OBS_WS_PORT       - OBS WebSocket port (default: 4455)
    OBS_WS_PASSWORD   - OBS WebSocket password
    OBS_SCENE_NAME    - Default scene name (default: ZeusAvatar)
    REDIS_HOST        - Redis host (default: localhost)
    REDIS_PORT        - Redis port (default: 6379)
    REDIS_PASSWORD    - Redis password (default: empty)

Opulent Bots LLC — All rights reserved
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
from typing import Optional

import redis

# OBS 28+ includes obs-websocket by default — use obsws-python to connect.
# See: https://github.com/obsproject/obs-websocket
try:
    import obsws_python as obsws
except ImportError:
    obsws = None
    print(
        "ERROR: obsws-python not installed. Run: pip install obsws-python\n"
        "This connects to OBS 28+'s built-in obs-websocket server.",
        file=sys.stderr,
    )
    sys.exit(1)

# ─── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "info").upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("zeus.obs")

# ─── Configuration ────────────────────────────────────────────────────────────

OBS_WS_HOST: str = os.environ.get("OBS_WS_HOST", "localhost")
OBS_WS_PORT: int = int(os.environ.get("OBS_WS_PORT", "4455"))
OBS_WS_PASSWORD: str = os.environ.get("OBS_WS_PASSWORD", "")
OBS_SCENE_NAME: str = os.environ.get("OBS_SCENE_NAME", "ZeusAvatar")

REDIS_HOST: str = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT: int = int(os.environ.get("REDIS_PORT", "6379"))
REDIS_PASSWORD: str = os.environ.get("REDIS_PASSWORD", "")

# Scene names (must match the OBS scene collection)
SCENE_AVATAR: str = OBS_SCENE_NAME
SCENE_SCREEN_SHARE: str = "ScreenShare"
SCENE_SPLIT_VIEW: str = "SplitView"

# Audio source names (must match OBS audio sources)
AUDIO_SOURCE_ZEUS: str = "Zeus TTS Audio"

# ─── OBS Connection Manager ──────────────────────────────────────────────────


class OBSConnection:
    """
    Manages the connection to OBS Studio via obs-websocket.
    Handles auto-reconnect with exponential backoff.
    """

    def __init__(self, host: str, port: int, password: str) -> None:
        self._host = host
        self._port = port
        self._password = password
        self._client: Optional[obsws.ReqClient] = None
        self._connected = False
        self._reconnect_delay = 1.0
        self._max_reconnect_delay = 30.0
        self._shutdown = False

    @property
    def connected(self) -> bool:
        return self._connected

    def connect(self) -> bool:
        """Attempt to connect to OBS. Returns True on success."""
        if self._shutdown:
            return False

        try:
            self._client = obsws.ReqClient(
                host=self._host,
                port=self._port,
                password=self._password,
                timeout=10,
            )
            self._connected = True
            self._reconnect_delay = 1.0

            # Log OBS version info
            version = self._client.get_version()
            logger.info(
                "Connected to OBS %s (obs-websocket %s, platform: %s)",
                version.obs_version,
                version.obs_web_socket_version,
                version.platform_description,
            )
            return True

        except Exception as exc:
            self._connected = False
            self._client = None
            logger.warning("OBS connection failed: %s", exc)
            return False

    def connect_with_retry(self) -> None:
        """Block until connected, with exponential backoff."""
        while not self._shutdown:
            if self.connect():
                return
            logger.info("Retrying OBS connection in %.1fs...", self._reconnect_delay)
            time.sleep(self._reconnect_delay)
            self._reconnect_delay = min(
                self._reconnect_delay * 2, self._max_reconnect_delay
            )

    def disconnect(self) -> None:
        """Disconnect from OBS."""
        self._shutdown = True
        if self._client:
            try:
                self._client.base_client.ws.close()
            except Exception:
                pass
            self._client = None
        self._connected = False
        logger.info("Disconnected from OBS")

    def _safe_call(self, method_name: str, *args, **kwargs):
        """
        Safely call an OBS method, handling disconnections.
        Returns None on failure.
        """
        if not self._connected or not self._client:
            logger.warning("OBS not connected — cannot execute: %s", method_name)
            return None

        try:
            method = getattr(self._client, method_name)
            result = method(*args, **kwargs)
            return result
        except (ConnectionError, BrokenPipeError, OSError) as exc:
            logger.error("OBS connection lost during %s: %s", method_name, exc)
            self._connected = False
            # Attempt reconnect in background
            threading.Thread(
                target=self.connect_with_retry, daemon=True, name="obs-reconnect"
            ).start()
            return None
        except Exception as exc:
            logger.error("OBS command failed (%s): %s", method_name, exc)
            return None

    # ─── Scene Commands ──────────────────────────────────────────────

    def switch_scene(self, scene_name: str) -> bool:
        """Switch to the specified OBS scene."""
        logger.info("Switching to scene: %s", scene_name)
        result = self._safe_call("set_current_program_scene", scene_name)
        return result is not None

    def get_current_scene(self) -> Optional[str]:
        """Get the current active scene name."""
        result = self._safe_call("get_current_program_scene")
        if result:
            return result.scene_name
        return None

    def get_scene_list(self) -> list[str]:
        """Get list of all scene names."""
        result = self._safe_call("get_scene_list")
        if result:
            return [s["sceneName"] for s in result.scenes]
        return []

    # ─── Audio Commands ──────────────────────────────────────────────

    def mute_source(self, source_name: str) -> bool:
        """Mute an audio source."""
        logger.info("Muting audio source: %s", source_name)
        result = self._safe_call("set_input_mute", source_name, True)
        return result is not None

    def unmute_source(self, source_name: str) -> bool:
        """Unmute an audio source."""
        logger.info("Unmuting audio source: %s", source_name)
        result = self._safe_call("set_input_mute", source_name, False)
        return result is not None

    def toggle_mute(self, source_name: str) -> bool:
        """Toggle mute on an audio source."""
        logger.info("Toggling mute: %s", source_name)
        result = self._safe_call("toggle_input_mute", source_name)
        return result is not None

    # ─── Recording Commands ──────────────────────────────────────────

    def start_recording(self) -> bool:
        """Start OBS recording."""
        logger.info("Starting recording")
        result = self._safe_call("start_record")
        return result is not None

    def stop_recording(self) -> bool:
        """Stop OBS recording."""
        logger.info("Stopping recording")
        result = self._safe_call("stop_record")
        return result is not None

    def toggle_recording(self) -> bool:
        """Toggle OBS recording."""
        logger.info("Toggling recording")
        result = self._safe_call("toggle_record")
        return result is not None

    # ─── Streaming Commands ──────────────────────────────────────────

    def start_streaming(self) -> bool:
        """Start OBS streaming."""
        logger.info("Starting stream")
        result = self._safe_call("start_stream")
        return result is not None

    def stop_streaming(self) -> bool:
        """Stop OBS streaming."""
        logger.info("Stopping stream")
        result = self._safe_call("stop_stream")
        return result is not None

    # ─── Virtual Camera ──────────────────────────────────────────────

    def start_virtual_camera(self) -> bool:
        """Start OBS virtual camera."""
        logger.info("Starting virtual camera")
        result = self._safe_call("start_virtual_cam")
        return result is not None

    def stop_virtual_camera(self) -> bool:
        """Stop OBS virtual camera."""
        logger.info("Stopping virtual camera")
        result = self._safe_call("stop_virtual_cam")
        return result is not None


# ─── Redis Event Listener ────────────────────────────────────────────────────


class RedisEventListener:
    """
    Subscribes to Zeus Redis event channels and dispatches OBS commands
    accordingly.
    """

    def __init__(self, obs: OBSConnection) -> None:
        self._obs = obs
        self._running = False
        self._pubsub: Optional[redis.client.PubSub] = None
        self._client: Optional[redis.Redis] = None

    def connect(self) -> bool:
        """Connect to Redis."""
        try:
            self._client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                password=REDIS_PASSWORD or None,
                decode_responses=True,
                socket_connect_timeout=5,
                retry_on_timeout=True,
            )
            self._client.ping()
            logger.info("Connected to Redis at %s:%d", REDIS_HOST, REDIS_PORT)
            return True
        except Exception as exc:
            logger.warning("Redis connection failed: %s", exc)
            return False

    def start(self) -> None:
        """Subscribe to channels and start listening."""
        if not self._client:
            if not self.connect():
                logger.error("Cannot start Redis listener — connection failed")
                return

        self._running = True
        self._pubsub = self._client.pubsub()
        self._pubsub.subscribe(
            "zeus:speaking",
            "zeus:stop_talking",
            "zeus:barge_in",
        )
        logger.info("Subscribed to Redis channels: zeus:speaking, zeus:stop_talking, zeus:barge_in")

        thread = threading.Thread(target=self._listen_loop, daemon=True, name="redis-listener")
        thread.start()

    def _listen_loop(self) -> None:
        """Process incoming Redis pub/sub messages."""
        while self._running and self._pubsub:
            try:
                message = self._pubsub.get_message(timeout=1.0)
                if message and message["type"] == "message":
                    self._handle_event(message["channel"], message["data"])
            except redis.ConnectionError:
                logger.warning("Redis connection lost — attempting reconnect")
                time.sleep(2)
                if self.connect():
                    self.start()
                return
            except Exception as exc:
                logger.error("Redis listener error: %s", exc)
                time.sleep(1)

    def _handle_event(self, channel: str, data: str) -> None:
        """Route Redis events to OBS actions."""
        logger.debug("Redis event: channel=%s data=%s", channel, data)

        if channel == "zeus:speaking":
            is_speaking = data.lower() in ("true", "1", "yes")
            if is_speaking:
                # Zeus started speaking — ensure audio source is unmuted
                self._obs.unmute_source(AUDIO_SOURCE_ZEUS)
                logger.info("Zeus speaking — audio unmuted")
            else:
                # Zeus stopped speaking
                logger.info("Zeus stopped speaking")

        elif channel == "zeus:stop_talking":
            # Mute Zeus audio immediately
            self._obs.mute_source(AUDIO_SOURCE_ZEUS)
            logger.info("STOP_TALKING — Zeus audio muted")

        elif channel == "zeus:barge_in":
            # User barged in — mute Zeus and optionally switch scene
            self._obs.mute_source(AUDIO_SOURCE_ZEUS)
            logger.info("BARGE_IN — Zeus audio muted (user interruption)")

    def stop(self) -> None:
        """Stop listening and clean up."""
        self._running = False
        if self._pubsub:
            try:
                self._pubsub.close()
            except Exception:
                pass
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass


# ─── Interactive CLI ─────────────────────────────────────────────────────────

HELP_TEXT = """
Zeus OBS Controller — Available Commands:
──────────────────────────────────────────
  scene <name>       Switch to scene (ZeusAvatar, ScreenShare, SplitView)
  scenes             List all scenes
  current            Show current scene

  mute               Mute Zeus audio
  unmute             Unmute Zeus audio
  toggle-mute        Toggle Zeus audio mute

  record-start       Start recording
  record-stop        Stop recording
  record-toggle      Toggle recording

  stream-start       Start streaming
  stream-stop        Stop streaming

  vcam-start         Start virtual camera
  vcam-stop          Stop virtual camera

  avatar             Switch to ZeusAvatar scene
  share              Switch to ScreenShare scene
  split              Switch to SplitView scene

  status             Show connection status
  reconnect          Force reconnect to OBS
  help               Show this help
  quit / exit        Exit controller
""".strip()


def run_interactive(obs: OBSConnection) -> None:
    """Run the interactive CLI in a separate thread."""
    print("\nZeus OBS Controller — Type 'help' for commands.\n")

    while True:
        try:
            cmd = input("obs> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting...")
            break

        if not cmd:
            continue

        parts = cmd.split(maxsplit=1)
        command = parts[0]
        arg = parts[1] if len(parts) > 1 else ""

        if command in ("quit", "exit", "q"):
            break
        elif command == "help":
            print(HELP_TEXT)
        elif command == "status":
            print(f"  OBS connected: {obs.connected}")
            scene = obs.get_current_scene()
            print(f"  Current scene: {scene or 'unknown'}")
        elif command == "reconnect":
            print("  Reconnecting to OBS...")
            obs.connect_with_retry()
        elif command == "scene" and arg:
            ok = obs.switch_scene(arg)
            print(f"  {'Switched' if ok else 'Failed'} to scene: {arg}")
        elif command == "scenes":
            scenes = obs.get_scene_list()
            for s in scenes:
                print(f"  - {s}")
        elif command == "current":
            scene = obs.get_current_scene()
            print(f"  Current scene: {scene or 'unknown'}")
        elif command == "mute":
            ok = obs.mute_source(AUDIO_SOURCE_ZEUS)
            print(f"  {'Muted' if ok else 'Failed to mute'}: {AUDIO_SOURCE_ZEUS}")
        elif command == "unmute":
            ok = obs.unmute_source(AUDIO_SOURCE_ZEUS)
            print(f"  {'Unmuted' if ok else 'Failed to unmute'}: {AUDIO_SOURCE_ZEUS}")
        elif command == "toggle-mute":
            ok = obs.toggle_mute(AUDIO_SOURCE_ZEUS)
            print(f"  {'Toggled' if ok else 'Failed to toggle'} mute: {AUDIO_SOURCE_ZEUS}")
        elif command == "record-start":
            ok = obs.start_recording()
            print(f"  Recording {'started' if ok else 'failed to start'}")
        elif command == "record-stop":
            ok = obs.stop_recording()
            print(f"  Recording {'stopped' if ok else 'failed to stop'}")
        elif command == "record-toggle":
            ok = obs.toggle_recording()
            print(f"  Recording {'toggled' if ok else 'failed to toggle'}")
        elif command == "stream-start":
            ok = obs.start_streaming()
            print(f"  Stream {'started' if ok else 'failed to start'}")
        elif command == "stream-stop":
            ok = obs.stop_streaming()
            print(f"  Stream {'stopped' if ok else 'failed to stop'}")
        elif command == "vcam-start":
            ok = obs.start_virtual_camera()
            print(f"  Virtual camera {'started' if ok else 'failed to start'}")
        elif command == "vcam-stop":
            ok = obs.stop_virtual_camera()
            print(f"  Virtual camera {'stopped' if ok else 'failed to stop'}")
        elif command == "avatar":
            obs.switch_scene(SCENE_AVATAR)
        elif command == "share":
            obs.switch_scene(SCENE_SCREEN_SHARE)
        elif command == "split":
            obs.switch_scene(SCENE_SPLIT_VIEW)
        else:
            print(f"  Unknown command: {cmd}. Type 'help' for available commands.")


# ─── Main ────────────────────────────────────────────────────────────────────


def main() -> None:
    """Entry point: connect to OBS + Redis, start event listener and CLI."""
    logger.info("Zeus OBS Controller starting...")
    logger.info("OBS target: %s:%d", OBS_WS_HOST, OBS_WS_PORT)
    logger.info("Redis target: %s:%d", REDIS_HOST, REDIS_PORT)

    # Connect to OBS
    obs = OBSConnection(OBS_WS_HOST, OBS_WS_PORT, OBS_WS_PASSWORD)
    logger.info("Connecting to OBS Studio...")
    obs.connect_with_retry()

    # Connect to Redis and start event listener
    listener = RedisEventListener(obs)
    if listener.connect():
        listener.start()
    else:
        logger.warning(
            "Redis not available — running without event listener. "
            "OBS will only respond to manual CLI commands."
        )

    # Register signal handlers
    def handle_shutdown(signum, frame):
        logger.info("Received signal %d, shutting down...", signum)
        listener.stop()
        obs.disconnect()
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    # Run interactive CLI (blocking)
    try:
        run_interactive(obs)
    finally:
        logger.info("Shutting down...")
        listener.stop()
        obs.disconnect()
        logger.info("OBS Controller stopped.")


if __name__ == "__main__":
    main()
