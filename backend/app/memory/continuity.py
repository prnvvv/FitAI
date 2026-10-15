"""Cross-chat continuity: recall shaping and prompt formatting.

Turns raw semantic recall (relevant memories + past-chat summaries) into a
bounded, deterministic context block. Kept free of database and vector-store
access so it is trivially testable; the retriever/store is injected by the
caller.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Rough character budgets (≈4 chars/token) for each recalled layer.
MEMORY_BUDGET_CHARS = 2000  # ~500 tokens
PAST_CHAT_BUDGET_CHARS = 2400  # ~600 tokens


@dataclass(frozen=True)
class ContinuityContext:
    """Relevant recalled facts for one turn."""

    memories: list[str] = field(default_factory=list)
    past_chats: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.memories and not self.past_chats


def _truncate(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + " …"


def format_continuity(context: ContinuityContext) -> str:
    """Render recalled memories and past-chat summaries within their budgets.

    Returns an empty string when there is nothing to inject, so the prompt shape
    is unchanged for users with no continuity data.
    """
    if context.is_empty:
        return ""
    parts: list[str] = []
    if context.memories:
        block = _truncate("\n".join(f"- {m}" for m in context.memories), MEMORY_BUDGET_CHARS)
        parts.append(f"Relevant saved facts:\n{block}")
    if context.past_chats:
        block = _truncate("\n".join(f"- {c}" for c in context.past_chats), PAST_CHAT_BUDGET_CHARS)
        parts.append(f"Relevant earlier conversations:\n{block}")
    return "\n\n".join(parts)
