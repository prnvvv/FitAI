"""LLM intent/scope classifier for the guardrail gate.

The classifier is deliberately small and isolated: a single JSON-only Groq call
at temperature 0. Its output is untrusted, so it is parsed and validated with
Pydantic. Any failure (network, timeout, malformed JSON, unknown label) returns
``None`` and the caller falls back to the deterministic safety rules.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.llm.prompts import INTENT_CLASSIFIER

log = logging.getLogger(__name__)

#: The one label that means "this is a legitimate fitness request".
IN_SCOPE_LABEL = "fitness"

#: Every label the classifier is allowed to return. Keep in sync with the prompt.
ALLOWED_LABELS = (
    "fitness",
    "off_topic",
    "code_request",
    "capability_probe",
    "wrapper",
    "prompt_injection",
    "self_harm",
    "medical_emergency",
    "extreme_restriction",
    "drug_dosing",
    "unsafe_training",
    "medical_advice",
)

IntentLabel = Literal[
    "fitness",
    "off_topic",
    "code_request",
    "capability_probe",
    "wrapper",
    "prompt_injection",
    "self_harm",
    "medical_emergency",
    "extreme_restriction",
    "drug_dosing",
    "unsafe_training",
    "medical_advice",
]

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.I)


class Intent(BaseModel):
    """Validated classifier output for one user message."""

    label: IntentLabel
    in_scope: bool
    wants_tool: bool
    confidence: float = Field(ge=0, le=1)
    reason: str = ""


def parse_intent(raw: str) -> Intent | None:
    """Parse a raw classifier response. Returns ``None`` when unusable."""
    if not raw or not raw.strip():
        return None
    try:
        text = _FENCE_RE.sub("", raw.strip())
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        log.warning("intent classifier returned malformed JSON")
        return None
    # Tolerate a wrapped object such as {"intent": {...}}.
    if isinstance(data, dict) and "label" not in data:
        for value in data.values():
            if isinstance(value, dict) and "label" in value:
                data = value
                break
    if not isinstance(data, dict):
        return None
    try:
        return Intent.model_validate(data)
    except (ValidationError, ValueError) as exc:
        log.warning("intent classifier output rejected: %s", type(exc).__name__)
        return None


class IntentClassifier:
    """Thin wrapper that turns a user message into a validated :class:`Intent`."""

    def __init__(self, complete: Callable[[str, str], str], *, model: str | None = None) -> None:
        """`complete(system, user)` must perform one JSON-mode completion."""
        self._complete = complete
        self.model = model

    def classify(self, message: str) -> Intent | None:
        """Classify one message. Never raises; returns ``None`` on any failure."""
        try:
            raw = self._complete(INTENT_CLASSIFIER, message[:1000])
        except Exception:  # noqa: BLE001 - any provider failure degrades to fallback
            log.warning("intent classifier call failed", exc_info=True)
            return None
        return parse_intent(raw)


__all__ = [
    "ALLOWED_LABELS",
    "IN_SCOPE_LABEL",
    "Intent",
    "IntentClassifier",
    "IntentLabel",
    "parse_intent",
]
