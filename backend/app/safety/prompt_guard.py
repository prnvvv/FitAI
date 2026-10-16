"""Prompt-injection screening with a dedicated guard model.

``meta-llama/llama-prompt-guard-2-86m`` is a *classifier*, not a chat model: it
accepts exactly one user message (no system prompt) and returns the probability
that the text is a jailbreak / prompt-injection attempt, where ``0`` is safe and
``1`` is unsafe. This module wraps that contract.

Two rules govern the integration:

* **Fail open on any problem.** A timeout, a provider error or an unparsable
  response degrades to "not unsafe" so a guard outage can never take chat down.
  The deterministic rules in :mod:`app.safety.guardrails` still run first and
  remain the fail-closed safety layer.
* **Treat the text as data.** The screened text is never interpolated into a
  prompt that asks the model to obey it; only the numeric verdict is used.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

#: Anything longer is truncated before screening: the guard scores a single
#: short instruction, and a huge document would only cost latency.
MAX_SCREEN_CHARS = 8000

_SCORE_RE = re.compile(r"(?<![\d.])(0(?:\.\d+)?|1(?:\.0+)?)(?![\d.])")


@dataclass(frozen=True)
class GuardVerdict:
    """Outcome of screening one piece of untrusted text."""

    score: float | None = None
    unsafe: bool = False
    error: str | None = None

    @property
    def screened(self) -> bool:
        """True when a real score came back (as opposed to a degraded pass)."""
        return self.score is not None


class PromptGuard:
    """Thin, replaceable wrapper around a guard-classification model."""

    def __init__(
        self,
        client: Any,
        model: str,
        *,
        threshold: float = 0.5,
        timeout: float = 2.0,
    ) -> None:
        self._client = client
        self._model = model
        self._threshold = threshold
        self._timeout = timeout

    @property
    def model(self) -> str:
        return self._model

    def screen(self, text: str) -> GuardVerdict:
        """Return the injection verdict for ``text``. Never raises."""
        cleaned = (text or "").strip()[:MAX_SCREEN_CHARS]
        if not cleaned:
            return GuardVerdict(score=0.0, unsafe=False)
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                # Guard classifiers accept a single user message and no system prompt.
                messages=[{"role": "user", "content": cleaned}],
                temperature=0.0,
                max_tokens=8,
            )
            raw = response.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001 - fail open, never break the turn
            log.warning("prompt_guard_unavailable error=%s", type(exc).__name__)
            return GuardVerdict(error=type(exc).__name__)
        score = parse_score(raw)
        if score is None:
            log.warning("prompt_guard_unreadable_response")
            return GuardVerdict(error="unparsable_response")
        return GuardVerdict(score=score, unsafe=score >= self._threshold)


def parse_score(raw: str) -> float | None:
    """Parse the guard's numeric probability; ``None`` when unusable."""
    match = _SCORE_RE.search((raw or "").strip())
    if match is None:
        return None
    try:
        value = float(match.group(1))
    except ValueError:
        return None
    return value if 0.0 <= value <= 1.0 else None


def build_prompt_guard() -> PromptGuard | None:
    """Build the configured guard, or None when it is disabled/unconfigured.

    Never falls back to a different model: without ``PROMPT_GUARD_MODEL`` there
    is simply no guard, and the existing deterministic rules keep working.
    """
    from app.core.config import settings

    if not settings.prompt_guard_enabled or not settings.prompt_guard_model:
        return None
    api_key = settings.prompt_guard_api_key or settings.groq_api_key
    if not api_key:
        return None
    try:
        from groq import Groq

        client = Groq(api_key=api_key, timeout=settings.prompt_guard_timeout_s)
    except Exception:
        log.warning("prompt_guard_client_unavailable", exc_info=True)
        return None
    return PromptGuard(
        client,
        settings.prompt_guard_model,
        threshold=settings.prompt_guard_threshold,
        timeout=settings.prompt_guard_timeout_s,
    )


__all__ = ["GuardVerdict", "MAX_SCREEN_CHARS", "PromptGuard", "build_prompt_guard", "parse_score"]
