"""Roll a conversation into a compact summary for cross-chat recall.

Pure logic only: the LLM is injected via the shared :class:`TextCompleter`
protocol and persistence is handled by the caller. The summarizer is best-effort
and never raises: any provider failure returns ``None`` so a chat turn is
unaffected.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from app.llm.prompts import CONVERSATION_SUMMARY

from .extractor import TextCompleter

log = logging.getLogger(__name__)

#: Most recent turns fed to the summarizer (older context is dropped).
MAX_INPUT_MESSAGES = 40
#: Hard cap on the stored summary length (characters).
MAX_SUMMARY_CHARS = 1200
#: Placeholder persisted for blocked user turns; never summarised.
_BLOCKED_PLACEHOLDER = "[Blocked by safety filter]"


def _role_and_content(message: Any) -> tuple[str, str]:
    if isinstance(message, dict):
        return str(message.get("role", "user")), str(message.get("content", ""))
    role, content = message
    return str(role), str(content)


def _clean(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    # Tolerate an accidental fenced block from the model.
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 2:
            lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
    return text[:MAX_SUMMARY_CHARS].strip()


def build_summary(
    messages: Sequence[Any],
    llm: TextCompleter,
    *,
    max_messages: int = MAX_INPUT_MESSAGES,
) -> str | None:
    """Return a compact summary of ``messages``, or ``None`` when unavailable.

    ``messages`` are dicts with ``role``/``content`` keys (the chat pipeline's
    context shape). Blocked turns are skipped, and an empty conversation yields
    ``None`` so nothing is stored or indexed.
    """
    lines: list[str] = []
    for message in messages[-max_messages:]:
        role, content = _role_and_content(message)
        content = content.strip()
        if not content:
            continue
        if role == "user" and content == _BLOCKED_PLACEHOLDER:
            continue
        lines.append(f"{role}: {content[:600]}")
    if not lines:
        return None
    transcript = "\n".join(lines)
    try:
        raw = llm(CONVERSATION_SUMMARY, transcript)
    except Exception:
        log.warning("conversation summary LLM failed", exc_info=True)
        return None
    summary = _clean(str(raw))
    return summary or None
