"""
Open-Source Audio-to-Blendshape Engine (SDK Backend).

Converts audio amplitude and frequency features to ARKit-compatible facial
blendshapes. This is the standalone audio analysis engine that produces
blendshape weights from raw PCM audio without requiring NVIDIA hardware.

Audio analysis pipeline:
    1. Energy envelope: RMS energy per frame -> drives jawOpen
    2. Spectral features: FFT -> frequency bands -> vowel-like shapes
    3. Smoothing: EMA on all blendshape values for natural motion
    4. Transition blending: Smooth transitions between speaking/idle (200ms)

For production quality, use the NVIDIA Audio2Face-3D UE plugin which runs
ML-based lip sync directly in Unreal Engine.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.signal import butter, lfilter


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Audio format expectations
SAMPLE_RATE: int = 16000  # 16kHz
SAMPLE_WIDTH: int = 2     # 16-bit = 2 bytes
CHANNELS: int = 1         # Mono

# Frequency band boundaries (Hz) for spectral feature extraction
BAND_LOW = (200, 500)       # O/U vowel shapes
BAND_MID = (500, 1500)      # A/E vowel shapes
BAND_HIGH = (1500, 4000)    # I/EE shapes
BAND_SIBILANCE = (4000, 8000)  # S/SH consonant shapes

# Smoothing
EMA_ALPHA: float = 0.3     # Exponential moving average alpha
TRANSITION_DURATION: float = 0.2  # seconds for speaking<->idle transition

# Energy thresholds
SILENCE_THRESHOLD: float = 0.005    # Below this = silence
SPEECH_THRESHOLD: float = 0.015     # Above this = definite speech

# ARKit blendshape names (52 total)
ARKIT_BLENDSHAPES: list[str] = [
    # Jaw
    "jawOpen", "jawForward", "jawLeft", "jawRight",
    # Mouth
    "mouthClose", "mouthFunnel", "mouthPucker", "mouthLeft", "mouthRight",
    "mouthSmileLeft", "mouthSmileRight", "mouthFrownLeft", "mouthFrownRight",
    "mouthDimpleLeft", "mouthDimpleRight", "mouthStretchLeft", "mouthStretchRight",
    "mouthRollLower", "mouthRollUpper", "mouthShrugLower", "mouthShrugUpper",
    "mouthPressLeft", "mouthPressRight", "mouthLowerDownLeft", "mouthLowerDownRight",
    "mouthUpperUpLeft", "mouthUpperUpRight",
    # Brow
    "browDownLeft", "browDownRight", "browInnerUp", "browOuterUpLeft", "browOuterUpRight",
    # Eye
    "eyeBlinkLeft", "eyeBlinkRight", "eyeSquintLeft", "eyeSquintRight",
    "eyeWideLeft", "eyeWideRight",
    "eyeLookDownLeft", "eyeLookDownRight", "eyeLookInLeft", "eyeLookInRight",
    "eyeLookOutLeft", "eyeLookOutRight", "eyeLookUpLeft", "eyeLookUpRight",
    # Cheek
    "cheekPuff", "cheekSquintLeft", "cheekSquintRight",
    # Nose
    "noseSneerLeft", "noseSneerRight",
    # Tongue
    "tongueOut",
]


# ---------------------------------------------------------------------------
# Bandpass filter helper
# ---------------------------------------------------------------------------

def _bandpass_energy(
    samples: NDArray[np.float64],
    low_hz: float,
    high_hz: float,
    sample_rate: int = SAMPLE_RATE,
    order: int = 4,
) -> float:
    """
    Compute RMS energy of audio within a specific frequency band.

    Uses a Butterworth bandpass filter to isolate the band, then
    computes RMS of the filtered signal.
    """
    nyquist = sample_rate / 2.0
    low = max(low_hz / nyquist, 0.001)
    high = min(high_hz / nyquist, 0.999)

    if low >= high:
        return 0.0

    try:
        b, a = butter(order, [low, high], btype="band")
        filtered = lfilter(b, a, samples)
        rms = float(np.sqrt(np.mean(filtered ** 2)))
        return rms
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

@dataclass
class AudioToBlendshapeEngine:
    """
    Converts audio amplitude/frequency features to facial blendshapes.

    Uses audio energy, formant estimation, and phoneme-like classification
    to drive the 52 ARKit-compatible blendshapes used by MetaHuman.

    This is the open-source fallback. For production quality, use the
    NVIDIA Audio2Face-3D UE plugin which runs ML-based lip sync directly
    in Unreal Engine.
    """

    sample_rate: int = SAMPLE_RATE
    ema_alpha: float = EMA_ALPHA

    # Smoothed blendshape state
    _smoothed: dict[str, float] = field(default_factory=dict)
    _is_speaking: bool = False
    _speaking_blend: float = 0.0  # 0=idle, 1=fully speaking
    _frame_count: int = 0

    def __post_init__(self) -> None:
        # Initialize all blendshapes to 0
        self._smoothed = {name: 0.0 for name in ARKIT_BLENDSHAPES}

    def _smooth(self, name: str, target: float) -> float:
        """Apply exponential moving average smoothing."""
        current = self._smoothed.get(name, 0.0)
        smoothed = current + self.ema_alpha * (target - current)
        self._smoothed[name] = smoothed
        return smoothed

    def _clamp(self, value: float, low: float = 0.0, high: float = 1.0) -> float:
        return max(low, min(high, value))

    def process_audio_chunk(
        self,
        pcm_bytes: bytes,
        dt: float = 1.0 / 60.0,
    ) -> dict[str, Any]:
        """
        Process a chunk of PCM audio and return blendshape weights.

        Args:
            pcm_bytes: Raw PCM audio (16kHz, 16-bit signed LE, mono).
            dt: Time delta for transition blending.

        Returns:
            Dict with 'blendshapes' (52 ARKit shapes) and 'head_rotation'.
        """
        self._frame_count += 1

        # Decode PCM bytes to numpy float array
        samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float64)
        samples = samples / 32768.0  # Normalize to [-1, 1]

        if len(samples) == 0:
            return self._build_silent_frame()

        # --- Step 1: Overall energy envelope ---
        rms_energy = float(np.sqrt(np.mean(samples ** 2)))

        # Determine if speaking
        was_speaking = self._is_speaking
        if rms_energy > SPEECH_THRESHOLD:
            self._is_speaking = True
        elif rms_energy < SILENCE_THRESHOLD:
            self._is_speaking = False

        # Blend speaking state smoothly (200ms transition)
        target_blend = 1.0 if self._is_speaking else 0.0
        blend_speed = dt / TRANSITION_DURATION
        self._speaking_blend += (target_blend - self._speaking_blend) * min(blend_speed, 1.0)
        self._speaking_blend = self._clamp(self._speaking_blend)

        if rms_energy < SILENCE_THRESHOLD:
            return self._build_silent_frame()

        # --- Step 2: Spectral features ---
        low_energy = _bandpass_energy(samples, *BAND_LOW, self.sample_rate)
        mid_energy = _bandpass_energy(samples, *BAND_MID, self.sample_rate)
        high_energy = _bandpass_energy(samples, *BAND_HIGH, self.sample_rate)
        sibilance_energy = _bandpass_energy(samples, *BAND_SIBILANCE, self.sample_rate)

        # Normalize energies relative to overall RMS
        if rms_energy > 0:
            low_norm = min(low_energy / rms_energy, 2.0)
            mid_norm = min(mid_energy / rms_energy, 2.0)
            high_norm = min(high_energy / rms_energy, 2.0)
            sib_norm = min(sibilance_energy / rms_energy, 2.0)
        else:
            low_norm = mid_norm = high_norm = sib_norm = 0.0

        # Scale energy for mapping (amplify for visible movement)
        energy_scale = min(rms_energy * 8.0, 1.0)

        # --- Step 3: Map to blendshapes ---
        raw: dict[str, float] = {}

        # Primary jaw opening driven by overall energy
        raw["jawOpen"] = self._clamp(energy_scale * 0.8)

        # Low frequency dominant -> O/U mouth shapes
        raw["mouthFunnel"] = self._clamp(low_norm * energy_scale * 0.6)
        raw["mouthPucker"] = self._clamp(low_norm * energy_scale * 0.3)
        raw["mouthRollLower"] = self._clamp(low_norm * energy_scale * 0.15)
        raw["mouthRollUpper"] = self._clamp(low_norm * energy_scale * 0.1)

        # Mid frequency -> A/E open mouth shapes
        raw["mouthStretchLeft"] = self._clamp(mid_norm * energy_scale * 0.3)
        raw["mouthStretchRight"] = self._clamp(mid_norm * energy_scale * 0.3)
        raw["mouthLowerDownLeft"] = self._clamp(mid_norm * energy_scale * 0.25)
        raw["mouthLowerDownRight"] = self._clamp(mid_norm * energy_scale * 0.25)
        raw["mouthUpperUpLeft"] = self._clamp(mid_norm * energy_scale * 0.15)
        raw["mouthUpperUpRight"] = self._clamp(mid_norm * energy_scale * 0.15)

        # High frequency -> I/EE smile/wide shapes
        raw["mouthSmileLeft"] = self._clamp(high_norm * energy_scale * 0.4)
        raw["mouthSmileRight"] = self._clamp(high_norm * energy_scale * 0.4)
        raw["cheekSquintLeft"] = self._clamp(high_norm * energy_scale * 0.1)
        raw["cheekSquintRight"] = self._clamp(high_norm * energy_scale * 0.1)

        # Sibilance -> tight/pursed lip shapes
        raw["mouthPressLeft"] = self._clamp(sib_norm * energy_scale * 0.3)
        raw["mouthPressRight"] = self._clamp(sib_norm * energy_scale * 0.3)
        raw["mouthShrugLower"] = self._clamp(sib_norm * energy_scale * 0.2)
        raw["mouthShrugUpper"] = self._clamp(sib_norm * energy_scale * 0.15)
        raw["mouthClose"] = self._clamp(sib_norm * energy_scale * 0.2)

        # Mouthfunnel reduces jawOpen (can't have both fully)
        if raw.get("mouthFunnel", 0) > 0.3:
            raw["jawOpen"] *= 0.6

        # Subtle sympathetic brow movement during speech
        raw["browInnerUp"] = self._clamp(energy_scale * 0.08)
        raw["browOuterUpLeft"] = self._clamp(energy_scale * 0.04)
        raw["browOuterUpRight"] = self._clamp(energy_scale * 0.04)

        # Subtle nose movement during speech
        raw["noseSneerLeft"] = self._clamp(energy_scale * 0.03)
        raw["noseSneerRight"] = self._clamp(energy_scale * 0.03)

        # Eye squint correlated with speech intensity
        raw["eyeSquintLeft"] = self._clamp(energy_scale * 0.06)
        raw["eyeSquintRight"] = self._clamp(energy_scale * 0.06)

        # --- Step 4: Apply EMA smoothing ---
        blendshapes: dict[str, float] = {}
        for name in ARKIT_BLENDSHAPES:
            target_val = raw.get(name, 0.0)
            # Blend with speaking blend factor
            target_val *= self._speaking_blend
            smoothed = self._smooth(name, target_val)
            blendshapes[name] = round(self._clamp(smoothed), 4)

        # --- Head rotation: slight movement correlated with speech ---
        head_rotation = {
            "pitch": round(math.sin(self._frame_count * 0.05) * energy_scale * 1.5, 3),
            "yaw": round(math.cos(self._frame_count * 0.03 + 1.0) * energy_scale * 1.0, 3),
            "roll": 0.0,
        }

        return {
            "blendshapes": blendshapes,
            "head_rotation": head_rotation,
        }

    def _build_silent_frame(self) -> dict[str, Any]:
        """Build a frame with all blendshapes decaying toward zero."""
        blendshapes: dict[str, float] = {}
        for name in ARKIT_BLENDSHAPES:
            smoothed = self._smooth(name, 0.0)
            blendshapes[name] = round(self._clamp(smoothed), 4)

        return {
            "blendshapes": blendshapes,
            "head_rotation": {"pitch": 0.0, "yaw": 0.0, "roll": 0.0},
        }

    def reset(self) -> None:
        """Reset all smoothed state."""
        self._smoothed = {name: 0.0 for name in ARKIT_BLENDSHAPES}
        self._is_speaking = False
        self._speaking_blend = 0.0
        self._frame_count = 0
