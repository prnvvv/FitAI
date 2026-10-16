"""Dedicated structured extractor backed by a separate Groq configuration.

The extractor is a thin, replaceable component: it calls the injected LLM
(default: a Groq client built from ``GROQ_EXTRACTION_API_KEY`` /
``GROQ_EXTRACTION_MODEL``), parses the JSON, and validates every candidate with
Pydantic. It never raises on provider or parse errors; those are captured in
``ExtractionResult.error`` so the caller can distinguish "nothing extracted"
from "saved".

This component is intentionally independent of the LangGraph agent so the
primary assistant, its prompts, and its tools are unaffected.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Protocol

from app.extraction.prompts import ACTIVITY_EXTRACTION
from app.extraction.schemas import ExtractionResult
from app.memory.extractor import TextCompleter

log = logging.getLogger(__name__)


class RecordExtractor(Protocol):
    """Narrow interface the chat flow depends on. Replaceable in tests."""

    def extract(self, message: str, now: datetime | None = None) -> ExtractionResult: ...


_ARRAY_FIELDS: dict[str, str] = {
    "completed_workouts": "CompletedWorkout",
    "planned_workouts": "PlannedWorkout",
    "progress_records": "ProgressRecord",
    "user_preferences": "UserPreference",
    "fitness_goals": "FitnessGoal",
    "profile_facts": "ProfileFact",
    "memory_insights": "MemoryInsight",
}

_MAX_ITEMS = 25


def _parse_json(raw: str) -> object:
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    return json.loads(s)


class GroqActivityExtractor:
    """Default extractor that uses a dedicated Groq client.

    The client is built from the extraction-specific key/model, which is kept
    separate from the primary assistant's credentials.
    """

    def __init__(self, api_key: str, model: str, *, llm: TextCompleter | None = None) -> None:
        # A completer can be injected (tests / alternate providers). Otherwise a
        # dedicated Groq client is built from this component's OWN key + model.
        if llm is not None:
            self._llm = llm
        else:
            # Imported lazily so constructing the class never requires groq.
            from app.llm.client import GroqClient

            self._llm = GroqClient(api_key=api_key, model=model)

    def extract(self, message: str, now: datetime | None = None) -> ExtractionResult:
        now = now or datetime.now(timezone.utc)
        try:
            raw = self._llm(
                ACTIVITY_EXTRACTION.replace("{today}", now.date().isoformat()),
                message[:4000],
                json_mode=True,
            )
            data = _parse_json(raw)
        except Exception as exc:  # provider failure or malformed JSON
            log.warning("activity extraction failed: %s", type(exc).__name__)
            return ExtractionResult(error=type(exc).__name__)

        if not isinstance(data, dict):
            return ExtractionResult(error="unexpected_payload")
        return _validate_result(data)


def _validate_result(data: dict[str, object]) -> ExtractionResult:
    from pydantic import ValidationError

    from app.extraction import schemas

    result = ExtractionResult()
    for field_name, model_name in _ARRAY_FIELDS.items():
        model = getattr(schemas, model_name)
        items = data.get(field_name, [])
        if items is None:
            continue
        if not isinstance(items, list):
            result.rejected.append(f"{field_name}: not a list")
            continue
        for item in items[:_MAX_ITEMS]:
            if not isinstance(item, dict):
                result.rejected.append(f"{field_name}: item is not an object")
                continue
            try:
                getattr(result, field_name).append(model.model_validate(item))
            except ValidationError as exc:
                reason = str(exc).splitlines()[0][:200]
                result.rejected.append(f"{field_name}: {reason}")
    return result
