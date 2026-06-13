"""
Coqui TTS Engine for Zeus Live Avatar.

Uses the Coqui TTS library to synthesize speech from text. Supports
VITS, XTTS, and other models available in the Coqui TTS model zoo.
Audio is synthesized per-sentence and streamed as PCM chunks.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import AsyncGenerator, Optional, Union

import numpy as np

logger = logging.getLogger("tts-service.coqui")

# Sentence boundary regex: split on .!? followed by whitespace or end-of-string
_SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?])\s+')


class CoquiEngine:
    """
    TTS engine backed by Coqui TTS.

    Loads a Coqui TTS model at init time, then provides async streaming
    synthesis that yields PCM audio chunks interleaved with metadata dicts.

    Args:
        model_name: Coqui model identifier (e.g. 'tts_models/en/vctk/vits').
        speaker_id: Speaker ID for multi-speaker models (e.g. 'p225').
        use_cuda: Whether to use GPU acceleration.
        chunk_size: Number of PCM samples per output chunk.
    """

    def __init__(
        self,
        model_name: str = "tts_models/en/vctk/vits",
        speaker_id: Optional[str] = None,
        use_cuda: bool = True,
        chunk_size: int = 4096,
    ) -> None:
        self._model_name = model_name
        self._speaker_id = speaker_id
        self._use_cuda = use_cuda
        self._chunk_size = chunk_size
        self._tts = None
        self._abort = False
        self._sample_rate: int = 22050  # Default; updated after model load

    def load(self) -> None:
        """
        Load the Coqui TTS model. This is blocking and should be called
        before the async event loop starts, or inside run_in_executor.
        """
        from TTS.api import TTS

        logger.info(
            f"Loading Coqui TTS model: {self._model_name} "
            f"(speaker={self._speaker_id}, cuda={self._use_cuda})"
        )
        start = time.monotonic()

        self._tts = TTS(model_name=self._model_name, gpu=self._use_cuda)

        # Determine sample rate from the synthesizer config
        if hasattr(self._tts, "synthesizer") and self._tts.synthesizer is not None:
            config = getattr(self._tts.synthesizer, "output_sample_rate", None)
            if config:
                self._sample_rate = int(config)
            else:
                # Try to get from tts_config
                tts_config = getattr(self._tts.synthesizer, "tts_config", None)
                if tts_config and hasattr(tts_config, "audio"):
                    self._sample_rate = int(
                        getattr(tts_config.audio, "sample_rate", self._sample_rate)
                    )

        elapsed = time.monotonic() - start
        logger.info(
            f"Coqui model loaded in {elapsed:.2f}s "
            f"(sample_rate={self._sample_rate})"
        )

    async def synthesize_stream(
        self,
        text: str,
        stream_id: str,
    ) -> AsyncGenerator[Union[bytes, dict], None]:
        """
        Synthesize text to speech and yield PCM chunks + metadata.

        Splits input text into sentences and synthesizes each one progressively.
        Yields a mix of:
        - bytes: Raw PCM audio (16-bit signed LE) in chunk_size sample blocks
        - dict: JSON-serializable metadata events

        Args:
            text: The text to synthesize.
            stream_id: Unique identifier for this synthesis stream.

        Yields:
            bytes (PCM audio) or dict (metadata events).
        """
        if self._tts is None:
            raise RuntimeError("Coqui model not loaded — call load() first")

        self._abort = False
        loop = asyncio.get_event_loop()

        # Emit stream start
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

            # Run TTS synthesis in executor to avoid blocking the event loop
            try:
                wav_array = await loop.run_in_executor(
                    None, self._synthesize_sentence, sentence
                )
            except Exception as exc:
                logger.error(f"Synthesis error for sentence '{sentence[:50]}...': {exc}")
                continue

            if self._abort:
                break

            if wav_array is None or len(wav_array) == 0:
                continue

            # Convert float32 [-1, 1] to int16 PCM
            pcm_int16 = np.clip(wav_array * 32767, -32768, 32767).astype(np.int16)
            pcm_bytes = pcm_int16.tobytes()

            # Stream in chunks
            offset = 0
            chunk_byte_size = self._chunk_size * 2  # 2 bytes per int16 sample
            while offset < len(pcm_bytes):
                if self._abort:
                    break

                chunk = pcm_bytes[offset : offset + chunk_byte_size]
                offset += chunk_byte_size

                # Yield PCM audio chunk
                yield chunk

                # Yield chunk metadata
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

                # Yield to event loop between chunks for backpressure
                await asyncio.sleep(0)

        # Emit stream done
        duration_ms = int(total_samples / self._sample_rate * 1000) if self._sample_rate else 0
        yield {
            "type": "meta",
            "stream_id": stream_id,
            "status": "done",
            "duration_ms": duration_ms,
        }

    def _synthesize_sentence(self, sentence: str) -> Optional[np.ndarray]:
        """
        Synthesize a single sentence (blocking). Called in executor.

        Returns:
            numpy float32 array of audio samples, or None on failure.
        """
        assert self._tts is not None

        try:
            # Coqui TTS returns a list of float samples
            kwargs: dict = {}
            if self._speaker_id:
                kwargs["speaker"] = self._speaker_id

            wav = self._tts.tts(text=sentence, **kwargs)

            if isinstance(wav, list):
                return np.array(wav, dtype=np.float32)
            elif isinstance(wav, np.ndarray):
                return wav.astype(np.float32)
            else:
                logger.warning(f"Unexpected TTS output type: {type(wav)}")
                return None
        except Exception as exc:
            logger.error(f"Coqui TTS error: {exc}", exc_info=True)
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
        """
        Split text into sentences for progressive synthesis.

        Uses a simple regex to split on sentence-ending punctuation followed
        by whitespace. Falls back to the whole text if no splits are found.
        """
        sentences = _SENTENCE_SPLIT_RE.split(text.strip())
        return [s for s in sentences if s.strip()]
