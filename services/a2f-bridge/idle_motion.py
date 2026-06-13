"""
Idle Motion Generator — Produces human-like idle animations.

When the avatar is not speaking, this generates subtle blinks, eye saccades,
head micro-movements, and breathing animations to avoid uncanny stillness.
Uses Perlin-like noise (via sine superposition) for organic feel.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field


def _simplex_1d(t: float, octaves: int = 3) -> float:
    """
    Simple 1D noise approximation using layered sine waves.

    Not true Perlin/simplex noise, but produces smooth organic-feeling
    pseudo-random motion suitable for idle animations.
    """
    value = 0.0
    amplitude = 1.0
    frequency = 1.0
    max_val = 0.0

    for _ in range(octaves):
        value += amplitude * math.sin(t * frequency + 0.7 * frequency)
        max_val += amplitude
        amplitude *= 0.5
        frequency *= 2.17  # Non-integer ratio avoids periodicity

    return value / max_val  # Normalize to [-1, 1]


@dataclass
class IdleMotionGenerator:
    """
    Generates human-like idle animations to avoid uncanny stillness.

    Features:
        - Eye blinks at random intervals (2-6 seconds)
        - Eye saccades (small random movements every 1-3 seconds)
        - Head micro-movements via noise function
        - Subtle breathing cycle at ~0.25 Hz
    """

    # Blink config
    blink_min_interval: float = 2.0
    blink_max_interval: float = 6.0
    blink_duration: float = 0.15  # seconds

    # Saccade config
    saccade_min_interval: float = 1.0
    saccade_max_interval: float = 3.0
    saccade_amplitude: float = 0.1  # max eye look offset

    # Head motion config
    head_amplitude_deg: float = 2.0  # max +-degrees

    # Breathing config
    breath_frequency: float = 0.25  # Hz (~15 breaths/min)
    breath_amplitude: float = 0.02  # subtle jaw/chest movement

    # Internal state
    _time_offset: float = field(default_factory=lambda: random.uniform(0, 1000))
    _next_blink_time: float = 0.0
    _blink_start_time: float = -1.0
    _is_blinking: bool = False
    _next_saccade_time: float = 0.0
    _saccade_target_x: float = 0.0
    _saccade_target_y: float = 0.0
    _saccade_current_x: float = 0.0
    _saccade_current_y: float = 0.0
    _elapsed: float = 0.0

    def __post_init__(self) -> None:
        self._schedule_next_blink()
        self._schedule_next_saccade()

    def _schedule_next_blink(self) -> None:
        self._next_blink_time = self._elapsed + random.uniform(
            self.blink_min_interval, self.blink_max_interval
        )

    def _schedule_next_saccade(self) -> None:
        self._next_saccade_time = self._elapsed + random.uniform(
            self.saccade_min_interval, self.saccade_max_interval
        )

    def generate_frame(self, dt: float) -> dict:
        """
        Generate one frame of idle animation.

        Args:
            dt: Delta time in seconds since last frame.

        Returns:
            Dict with 'blendshapes' and 'head_rotation' keys.
        """
        self._elapsed += dt
        t = self._elapsed + self._time_offset

        blendshapes: dict[str, float] = {}

        # --- Eye Blinks ---
        blink_value = 0.0

        if not self._is_blinking and self._elapsed >= self._next_blink_time:
            self._is_blinking = True
            self._blink_start_time = self._elapsed

        if self._is_blinking:
            blink_progress = (self._elapsed - self._blink_start_time) / self.blink_duration
            if blink_progress >= 1.0:
                self._is_blinking = False
                blink_value = 0.0
                self._schedule_next_blink()
            else:
                # Smooth blink curve: up then down
                blink_value = math.sin(blink_progress * math.pi)

        blendshapes["eyeBlinkLeft"] = blink_value
        blendshapes["eyeBlinkRight"] = blink_value

        # --- Eye Saccades ---
        if self._elapsed >= self._next_saccade_time:
            self._saccade_target_x = random.uniform(
                -self.saccade_amplitude, self.saccade_amplitude
            )
            self._saccade_target_y = random.uniform(
                -self.saccade_amplitude, self.saccade_amplitude
            )
            self._schedule_next_saccade()

        # Smooth interpolation toward saccade target
        lerp_speed = 8.0 * dt
        self._saccade_current_x += (self._saccade_target_x - self._saccade_current_x) * min(lerp_speed, 1.0)
        self._saccade_current_y += (self._saccade_target_y - self._saccade_current_y) * min(lerp_speed, 1.0)

        # Map saccade to ARKit eye look shapes
        if self._saccade_current_x > 0:
            blendshapes["eyeLookOutLeft"] = abs(self._saccade_current_x)
            blendshapes["eyeLookInRight"] = abs(self._saccade_current_x)
            blendshapes["eyeLookInLeft"] = 0.0
            blendshapes["eyeLookOutRight"] = 0.0
        else:
            blendshapes["eyeLookInLeft"] = abs(self._saccade_current_x)
            blendshapes["eyeLookOutRight"] = abs(self._saccade_current_x)
            blendshapes["eyeLookOutLeft"] = 0.0
            blendshapes["eyeLookInRight"] = 0.0

        if self._saccade_current_y > 0:
            blendshapes["eyeLookUpLeft"] = abs(self._saccade_current_y)
            blendshapes["eyeLookUpRight"] = abs(self._saccade_current_y)
            blendshapes["eyeLookDownLeft"] = 0.0
            blendshapes["eyeLookDownRight"] = 0.0
        else:
            blendshapes["eyeLookDownLeft"] = abs(self._saccade_current_y)
            blendshapes["eyeLookDownRight"] = abs(self._saccade_current_y)
            blendshapes["eyeLookUpLeft"] = 0.0
            blendshapes["eyeLookUpRight"] = 0.0

        # --- Head Micro-Movements (noise-driven) ---
        pitch = _simplex_1d(t * 0.3) * self.head_amplitude_deg
        yaw = _simplex_1d(t * 0.25 + 100) * self.head_amplitude_deg
        roll = _simplex_1d(t * 0.15 + 200) * (self.head_amplitude_deg * 0.3)

        head_rotation = {
            "pitch": round(pitch, 3),
            "yaw": round(yaw, 3),
            "roll": round(roll, 3),
        }

        # --- Breathing ---
        breath_phase = math.sin(2.0 * math.pi * self.breath_frequency * t)
        breath_value = max(0.0, breath_phase * self.breath_amplitude)
        blendshapes["jawOpen"] = breath_value

        # Subtle brow movement tied to breathing
        blendshapes["browInnerUp"] = max(0.0, breath_phase * 0.01)

        # --- Squint (subtle, adds life) ---
        squint = max(0.0, _simplex_1d(t * 0.1 + 50) * 0.05)
        blendshapes["eyeSquintLeft"] = squint
        blendshapes["eyeSquintRight"] = squint

        # Round all values
        blendshapes = {k: round(max(0.0, min(1.0, v)), 4) for k, v in blendshapes.items()}

        return {
            "blendshapes": blendshapes,
            "head_rotation": head_rotation,
        }
