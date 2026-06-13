"""
VAD (Voice Activity Detection) processor wrapping webrtcvad.

Provides smoothed speech detection with configurable thresholds to avoid
flickering between speech/silence states. Uses a ring buffer of frame
decisions for hysteresis.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

import webrtcvad


@dataclass
class VADResult:
    """Result from processing a single audio frame."""
    speaking: bool
    speech_start: bool
    speech_end: bool
    silence_duration_ms: int


class VADProcessor:
    """
    Voice Activity Detection processor with smoothing.

    Uses webrtcvad for per-frame VAD decisions, then applies hysteresis
    via ring buffers to avoid rapid state toggling.

    Args:
        sample_rate: Audio sample rate in Hz. Must be 8000, 16000, 32000, or 48000.
        frame_duration_ms: Frame duration in ms. Must be 10, 20, or 30.
        aggressiveness: webrtcvad aggressiveness mode (0-3). Higher = more
            aggressive at filtering non-speech.
        speech_frames_threshold: Consecutive speech frames needed to trigger
            speech_start event.
        silence_frames_threshold: Consecutive silence frames needed to trigger
            speech_end event. Derived from silence_threshold_ms if not set.
        silence_threshold_ms: Silence duration in ms before declaring speech_end.
            Used to compute silence_frames_threshold.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        frame_duration_ms: int = 30,
        aggressiveness: int = 2,
        speech_frames_threshold: int = 5,
        silence_frames_threshold: Optional[int] = None,
        silence_threshold_ms: int = 800,
    ) -> None:
        if sample_rate not in (8000, 16000, 32000, 48000):
            raise ValueError(f"sample_rate must be 8000, 16000, 32000, or 48000, got {sample_rate}")
        if frame_duration_ms not in (10, 20, 30):
            raise ValueError(f"frame_duration_ms must be 10, 20, or 30, got {frame_duration_ms}")
        if not 0 <= aggressiveness <= 3:
            raise ValueError(f"aggressiveness must be 0-3, got {aggressiveness}")

        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.aggressiveness = aggressiveness
        self.speech_frames_threshold = speech_frames_threshold

        # Compute silence frames threshold from ms if not explicitly given
        if silence_frames_threshold is not None:
            self.silence_frames_threshold = silence_frames_threshold
        else:
            self.silence_frames_threshold = max(1, silence_threshold_ms // frame_duration_ms)

        # Expected byte length for a single frame
        # 16-bit samples = 2 bytes per sample
        self.frame_byte_length = (sample_rate * frame_duration_ms // 1000) * 2

        # webrtcvad instance
        self._vad = webrtcvad.Vad(aggressiveness)

        # State tracking
        self._is_speaking = False
        self._speech_frame_count = 0
        self._silence_frame_count = 0
        self._last_speech_time: Optional[float] = None
        self._silence_start_time: Optional[float] = None

    def reset(self) -> None:
        """Reset all internal state."""
        self._is_speaking = False
        self._speech_frame_count = 0
        self._silence_frame_count = 0
        self._last_speech_time = None
        self._silence_start_time = None

    def process_frame(self, pcm_bytes: bytes) -> VADResult:
        """
        Process a single audio frame and return VAD result.

        Args:
            pcm_bytes: Raw PCM audio bytes (16-bit signed LE). Must be exactly
                frame_byte_length bytes.

        Returns:
            VADResult with current speaking state and transition events.

        Raises:
            ValueError: If pcm_bytes length doesn't match expected frame size.
        """
        if len(pcm_bytes) != self.frame_byte_length:
            raise ValueError(
                f"Expected {self.frame_byte_length} bytes for {self.frame_duration_ms}ms "
                f"frame at {self.sample_rate}Hz, got {len(pcm_bytes)}"
            )

        now = time.monotonic()
        is_speech = self._vad.is_speech(pcm_bytes, self.sample_rate)

        speech_start = False
        speech_end = False

        if is_speech:
            self._speech_frame_count += 1
            self._silence_frame_count = 0
            self._silence_start_time = None

            if not self._is_speaking and self._speech_frame_count >= self.speech_frames_threshold:
                # Transition: silence -> speaking
                self._is_speaking = True
                speech_start = True
                self._last_speech_time = now

        else:
            self._silence_frame_count += 1
            self._speech_frame_count = 0

            if self._silence_start_time is None:
                self._silence_start_time = now

            if self._is_speaking and self._silence_frame_count >= self.silence_frames_threshold:
                # Transition: speaking -> silence
                self._is_speaking = False
                speech_end = True

        # Compute how long silence has lasted (in ms)
        silence_duration_ms = 0
        if self._silence_start_time is not None and not self._is_speaking:
            silence_duration_ms = int((now - self._silence_start_time) * 1000)

        return VADResult(
            speaking=self._is_speaking,
            speech_start=speech_start,
            speech_end=speech_end,
            silence_duration_ms=silence_duration_ms,
        )

    @property
    def is_speaking(self) -> bool:
        """Current speaking state."""
        return self._is_speaking
