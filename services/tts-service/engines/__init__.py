"""
TTS Engine abstractions for Zeus Live Avatar.

Supported engines:
- CoquiEngine: Coqui TTS (VITS, XTTS, etc.) — GPU-accelerated
- PiperEngine: Piper TTS (ONNX) — CPU-friendly, low-latency
"""

from .coqui_engine import CoquiEngine
from .piper_engine import PiperEngine

__all__ = ["CoquiEngine", "PiperEngine"]
