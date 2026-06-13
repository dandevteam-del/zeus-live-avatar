"""
Piper TTS Engine for Zeus Live Avatar.

Uses Piper TTS (ONNX-based) for fast, CPU-friendly speech synthesis.
Piper is designed for low-latency, single-speaker TTS with small model
footprints.

NOTE: rhasspy/piper is archived. This uses the maintained fork at
https://github.com/rhasspy/piper -- check the repo for the current
recommended installation path. As of this writing, the piper-tts PyPI
package may need to be installed from the fork's releases or built from
source depending on your platform.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import re
import time
import wave
from pathlib import Path
from typing import AsyncGenerator, Optional, Union

import numpy as np

logger = logging.getLogger("tts-service.piper")

_SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?])\s+')


class PiperEngine:
    """
    TTS engine backed by Piper TTS (ONNX).

    Loads a Piper ONNX voice model at init time, then provides async
    streaming synthesis that yields PCM chunks interleaved with metadata.

    Args:
        model_path: Path to the Piper ONNX model file.
        config_path: Path to the model's JSON config file.
        speaker_id: Speaker ID for multi-speaker models.
        chunk_size: Number of PCM samples per output chunk.
    """

    def __init__(
        self,
        model_path: str = "/models/en_US-lessac-medium.onnx",
        config_path: Optional[str] = None,
        speaker_id: int = 0,
        chunk_size: int = 4096,
    ) -> None:
        self._model_path = model_path
        self._config_path = config_path or f"{model_path}.json"
        self._speaker_id = speaker_id
        self._chunk_size = chunk_size
        self._voice = None
        self._abort = False
        self._sample_rate: int = 22050  # Default; updated from config

    def load(self) -> None:
        """
        Load the Piper voice model. Blocking — call before the async
        event loop starts or inside run_in_executor.
        """
        try:
            from piper import PiperVoice
        except ImportError:
            raise ImportError(
                "piper-tts is not installed. Install it via: "
                "pip install piper-tts  (or build from the rhasspy/piper fork)"
            )

        logger.info(
            f"Loading Piper model: {self._model_path} "
            f"(config={self._config_path}, speaker_id={self._speaker_id})"
        )
        start = time.monotonic()

        self._voice = PiperVoice.load(self._model_path, config_path=self._config_path)

        # Read sample rate from the config
        config_path = Path(self._config_path)
        if config_path.exists():
            try:
                with open(config_path) as f:
                    config = json.load(f)
                self._sample_rate = config.get("audio", {}).get("sample_rate", self._sample_rate)
            except Exception as exc:
                logger.warning(f"Could not read Piper config for sample_rate: {exc}")

        elapsed = time.monotonic() - start
        logger.info(
            f"Piper model loaded in {elapsed:.2f}s (sample_rate={self._sample_rate})"
        )

    async def synthesize_stream(
        self,
        text: str,
        stream_id: str,
    ) -> AsyncGenerator[Union[bytes, dict], None]:
        """
        Synthesize text to speech and yield PCM chunks + metadata.

        Splits input text into sentences and synthesizes each one.
        Yields a mix of:
        - bytes: Raw PCM audio (16-bit signed LE)
        - dict: JSON-serializable metadata events

        Args:
            text: The text to synthesize.
            stream_id: Unique identifier for this synthesis stream.
        """
        if self._voice is None:
            raise RuntimeError("Piper model not loaded — call load() first")

        self._abort = False
        loop = asyncio.get_event_loop()

        yield {
            "type": "meta",
            "stream_id": stream_id,
            "status": "started",
            "sample_rate": self._sample_rate,
        }

        sentences = self._split_sentences(text)
        if not sentences:
            yield {
                "type": "meta",
                "stream_id": stream_id,
                "status": "done",
                "duration_ms": 0,
            }
            return

        chunk_index = 0
        total_samples = 0
        stream_start_time = time.monotonic()

        for sentence in sentences:
            if self._abort:
                logger.info(f"Synthesis aborted for stream {stream_id}")
                break

            sentence = sentence.strip()
            if not sentence:
                continue

            try:
                pcm_bytes = await loop.run_in_executor(
                    None, self._synthesize_sentence, sentence
                )
            except Exception as exc:
                logger.error(f"Piper synthesis error for '{sentence[:50]}...': {exc}")
                continue

            if self._abort:
                break

            if pcm_bytes is None or len(pcm_bytes) == 0:
                continue

            # Stream in chunks
            offset = 0
            chunk_byte_size = self._chunk_size * 2  # 2 bytes per int16
            while offset < len(pcm_bytes):
                if self._abort:
                    break

                chunk = pcm_bytes[offset : offset + chunk_byte_size]
                offset += chunk_byte_size

                yield chunk

                timestamp_ms = int((time.monotonic() - stream_start_time) * 1000)
                yield {
                    "type": "meta",
                    "stream_id": stream_id,
                    "status": "chunk",
                    "chunk_index": chunk_index,
                    "timestamp_ms": timestamp_ms,
                }
                chunk_index += 1
                total_samples += len(chunk) // 2

                await asyncio.sleep(0)

        duration_ms = int(total_samples / self._sample_rate * 1000) if self._sample_rate else 0
        yield {
            "type": "meta",
            "stream_id": stream_id,
            "status": "done",
            "duration_ms": duration_ms,
        }

    def _synthesize_sentence(self, sentence: str) -> Optional[bytes]:
        """
        Synthesize a single sentence via Piper (blocking). Called in executor.

        Returns raw 16-bit signed LE PCM bytes, or None on failure.
        """
        assert self._voice is not None

        try:
            # Piper synthesize_stream_raw yields audio chunks
            # We collect them into a single buffer
            audio_buffer = bytearray()

            for audio_bytes in self._voice.synthesize_stream_raw(
                sentence,
                speaker_id=self._speaker_id,
            ):
                if self._abort:
                    return None
                audio_buffer.extend(audio_bytes)

            return bytes(audio_buffer)
        except Exception as exc:
            logger.error(f"Piper TTS error: {exc}", exc_info=True)
            return None

    def stop(self) -> None:
        """Signal the current synthesis to abort."""
        self._abort = True

    @property
    def sample_rate(self) -> int:
        """Output sample rate of the loaded model."""
        return self._sample_rate

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """Split text into sentences for progressive synthesis."""
        sentences = _SENTENCE_SPLIT_RE.split(text.strip())
        return [s for s in sentences if s.strip()]
