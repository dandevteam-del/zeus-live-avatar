"""
Human Timing Engine — Adds natural response delays to avoid robotic feel.

Classifies user queries as simple/complex, calculates appropriate delays,
and rate-limits conversational prefaces ("Okay—", "Sure—", etc.) to avoid
sounding repetitive.
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field

logger = logging.getLogger("zeus.timing")

# Words that signal a complex question requiring "thought"
COMPLEX_KEYWORDS: set[str] = {
    "explain", "how", "why", "compare", "difference", "analyze",
    "elaborate", "describe", "detail", "evaluate", "assess",
    "contrast", "justify", "reason", "implications", "consequences",
    "what if", "suppose", "imagine", "consider", "breakdown",
}

PREFACE_POOL: list[str] = [
    "Okay\u2014",
    "Got it\u2014",
    "Sure\u2014",
    "Right\u2014",
    "So\u2014",
    "Well\u2014",
    "Let me think\u2014",
]


@dataclass
class TimingResult:
    """Result of a timing calculation."""
    delay_ms: int
    use_preface: bool
    preface_text: str | None


@dataclass
class HumanTimingEngine:
    """
    Calculates human-like response delays based on message complexity.

    Simple questions (yes/no, short answers) get shorter delays.
    Complex questions (explanations, comparisons) get longer delays
    to simulate thoughtfulness.

    Prefaces are rate-limited to avoid repetition.
    """

    simple_range: tuple[int, int] = (200, 600)
    complex_range: tuple[int, int] = (700, 1200)
    preface_rate_limit: int = 3  # max prefaces per minute

    # Internal tracking
    _preface_timestamps: list[float] = field(default_factory=list)
    _last_preface_index: int = -1

    def _is_complex(self, response_text: str, user_text: str) -> bool:
        """Classify whether the exchange requires a complex-style delay."""
        user_lower = user_text.lower()

        # Check for complex keywords in user message
        for keyword in COMPLEX_KEYWORDS:
            if keyword in user_lower:
                return True

        # Multiple question marks suggest a multi-part question
        if user_text.count("?") > 1:
            return True

        # Long responses generally follow complex questions
        if len(response_text.split()) > 80:
            return True

        # Long user messages are usually complex
        if len(user_text.split()) > 25:
            return True

        return False

    def _prune_preface_timestamps(self) -> None:
        """Remove preface timestamps older than 60 seconds."""
        cutoff = time.monotonic() - 60.0
        self._preface_timestamps = [
            ts for ts in self._preface_timestamps if ts > cutoff
        ]

    def _can_use_preface(self) -> bool:
        """Check if we are under the preface rate limit."""
        self._prune_preface_timestamps()
        return len(self._preface_timestamps) < self.preface_rate_limit

    def get_preface(self) -> str | None:
        """
        Return a rate-limited conversational preface, or None if rate exceeded.

        Avoids repeating the same preface twice in a row.
        """
        if not self._can_use_preface():
            logger.debug("Preface rate limit reached, skipping")
            return None

        # Pick a random preface that differs from the last one used
        available = list(range(len(PREFACE_POOL)))
        if self._last_preface_index in available and len(available) > 1:
            available.remove(self._last_preface_index)

        idx = random.choice(available)
        self._last_preface_index = idx
        self._preface_timestamps.append(time.monotonic())

        return PREFACE_POOL[idx]

    def calculate_delay(self, response_text: str, user_text: str) -> TimingResult:
        """
        Calculate the appropriate response delay and optional preface.

        Args:
            response_text: The AI-generated response (used for length analysis).
            user_text: The user's input message.

        Returns:
            TimingResult with delay_ms, whether to use a preface, and the text.
        """
        is_complex = self._is_complex(response_text, user_text)

        if is_complex:
            delay_ms = random.randint(*self.complex_range)
            # Complex questions often benefit from a preface
            use_preface = random.random() < 0.6
        else:
            delay_ms = random.randint(*self.simple_range)
            # Simple responses occasionally get a preface
            use_preface = random.random() < 0.25

        preface_text: str | None = None
        if use_preface:
            preface_text = self.get_preface()
            if preface_text is None:
                use_preface = False

        logger.debug(
            "Timing: complex=%s delay=%dms preface=%s",
            is_complex,
            delay_ms,
            preface_text,
        )

        return TimingResult(
            delay_ms=delay_ms,
            use_preface=use_preface,
            preface_text=preface_text,
        )
