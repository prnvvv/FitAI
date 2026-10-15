"""Tests for cross-chat continuity formatting and budgets."""

from __future__ import annotations

from app.memory.continuity import (
    MEMORY_BUDGET_CHARS,
    PAST_CHAT_BUDGET_CHARS,
    ContinuityContext,
    format_continuity,
)


def test_empty_context_is_empty() -> None:
    assert ContinuityContext().is_empty
    assert format_continuity(ContinuityContext()) == ""


def test_format_includes_memories_and_past_chats() -> None:
    ctx = ContinuityContext(memories=["weight: 72 kg"], past_chats=["Cutting plan: cut to 72 kg"])
    text = format_continuity(ctx)
    assert "Relevant saved facts:" in text
    assert "weight: 72 kg" in text
    assert "Relevant earlier conversations:" in text
    assert "Cutting plan: cut to 72 kg" in text


def test_format_only_memories_when_no_past_chats() -> None:
    ctx = ContinuityContext(memories=["goal: build muscle"])
    text = format_continuity(ctx)
    assert "Relevant saved facts:" in text
    assert "Relevant earlier conversations:" not in text


def test_memory_block_is_truncated_to_budget() -> None:
    ctx = ContinuityContext(memories=["y" * 500] * 20)
    text = format_continuity(ctx)
    memory_section = text.split("Relevant earlier conversations:")[0]
    assert len(memory_section) <= MEMORY_BUDGET_CHARS + 200


def test_past_chat_block_is_truncated_to_budget() -> None:
    ctx = ContinuityContext(past_chats=["z" * 500] * 20)
    text = format_continuity(ctx)
    assert len(text) <= PAST_CHAT_BUDGET_CHARS + 200
