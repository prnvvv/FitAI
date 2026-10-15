"""Tests for rolling conversation summarisation (cross-chat recall)."""

from __future__ import annotations

from app.memory.summarizer import MAX_SUMMARY_CHARS, build_summary


class _LLM:
    def __init__(self, response: str = "summary text", exc: Exception | None = None) -> None:
        self.response = response
        self.exc = exc
        self.calls: list[tuple[str, str]] = []

    def __call__(self, system: str, user: str, *, json_mode: bool = False) -> str:
        self.calls.append((system, user))
        if self.exc is not None:
            raise self.exc
        return self.response


def _ctx() -> list[dict[str, str]]:
    return [
        {"role": "user", "content": "I'm cutting to 72 kg"},
        {"role": "assistant", "content": "Got it."},
    ]


def test_build_summary_returns_model_text() -> None:
    llm = _LLM("User is cutting to 72 kg.")
    summary = build_summary(_ctx(), llm)
    assert summary == "User is cutting to 72 kg."
    assert llm.calls and "cutting" in llm.calls[0][1]


def test_build_summary_empty_conversation_returns_none() -> None:
    llm = _LLM()
    assert build_summary([], llm) is None
    assert llm.calls == []


def test_build_summary_skips_blocked_turns() -> None:
    llm = _LLM()
    ctx = [{"role": "user", "content": "[Blocked by safety filter]"}]
    assert build_summary(ctx, llm) is None
    assert llm.calls == []


def test_build_summary_llm_failure_returns_none() -> None:
    llm = _LLM(exc=RuntimeError("groq down"))
    assert build_summary(_ctx(), llm) is None


def test_build_summary_strips_code_fence() -> None:
    llm = _LLM("```\nUser is cutting.\n```")
    assert build_summary(_ctx(), llm) == "User is cutting."


def test_build_summary_caps_length() -> None:
    llm = _LLM("x" * (MAX_SUMMARY_CHARS + 500))
    summary = build_summary(_ctx(), llm)
    assert summary is not None
    assert len(summary) <= MAX_SUMMARY_CHARS


def test_build_summary_blank_response_returns_none() -> None:
    llm = _LLM("   ")
    assert build_summary(_ctx(), llm) is None
