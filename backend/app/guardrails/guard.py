"""Guard decision gate: deterministic rules + optional LLM intent classifier.

This is the single choke point every user message passes through before it can
reach the agent, tools, memory, or persistence. Deterministic safety rules run
first (fast, fail-closed). When they don't fire and the classifier is enabled,
one JSON-only Groq call refines the decision. Any classifier failure degrades to
the deterministic allow path: safety stays fail-closed (the rules already
screened the message) while scope fails open to the current behaviour, so chat
never breaks because a classifier hiccup.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass

from app.core.config import settings
from app.guardrails.classifier import Intent, IntentClassifier
from app.safety import get_safe_reply, run_safety_rules

log = logging.getLogger(__name__)

#: Real (non-fallback) classifier decisions are reused for this long.
_CACHE_TTL_S = 60.0
#: Hard cap so the in-process cache can't grow without bound.
_CACHE_MAX_ENTRIES = 1000

#: decision key -> (monotonic timestamp, decision)
_CACHE: dict[str, tuple[float, GuardDecision]] = {}

#: Scope-only labels the classifier may use to refuse a message. A question about
#: the user's OWN stored data is never one of these: blocking it would deny
#: cross-chat memory recall (a real regression observed in live verification).
_SCOPE_LABELS = frozenset({"off_topic", "wrapper", "capability_probe", "code_request"})


@dataclass(frozen=True)
class GuardDecision:
    """The outcome of gating one user message."""

    blocked: bool = False
    category: str | None = None
    #: Fixed safe reply to return when ``blocked`` is True.
    response: str | None = None
    #: Whether live tools (web search / nearby / logged records) are plausibly needed.
    wants_tool: bool = True
    #: Where the decision came from: deterministic | classifier | fallback.
    source: str = "deterministic"
    reason: str = ""


def _cache_key(user_id: str, message: str) -> str:
    normalized = " ".join(message.lower().split())
    return hashlib.sha256(f"{user_id}|{normalized}".encode()).hexdigest()


def _get_cached(key: str) -> GuardDecision | None:
    entry = _CACHE.get(key)
    if entry is None:
        return None
    ts, decision = entry
    if time.monotonic() - ts > _CACHE_TTL_S:
        _CACHE.pop(key, None)
        return None
    return decision


def _set_cached(key: str, decision: GuardDecision) -> None:
    if len(_CACHE) >= _CACHE_MAX_ENTRIES:
        _CACHE.clear()
    _CACHE[key] = (time.monotonic(), decision)


def clear_decision_cache() -> None:
    """Reset the in-process decision cache (used by tests and hot reload)."""
    _CACHE.clear()


def _is_personal_data_question(message: str) -> bool:
    """True when the message asks about the user's OWN stored data.

    Imported lazily so the guardrails package never depends on the agent graph
    at import time.
    """
    from app.agent.nodes import wants_personal_data_answer

    return wants_personal_data_answer(message)


def _decide_from_intent(intent: Intent, threshold: float, message: str = "") -> GuardDecision:
    """Turn a validated classifier :class:`Intent` into a :class:`GuardDecision`.

    Fail-closed: a message is only allowed when the classifier both marks it
    ``in_scope`` AND labels it ``fitness``. Low confidence degrades to the
    deterministic fallback (allow, uncached) rather than block on a weak signal.

    One deterministic exception: a *scope* refusal (off_topic and friends) is
    overridden for questions about the user's own stored preferences, routines,
    memories or records. Those are core fitness-assistant requests answered from
    PostgreSQL, and a scope misclassification would silently hide the user's own
    memory. Safety labels are never overridden — those messages were already
    screened by the deterministic rules above.
    """
    if intent.confidence < threshold:
        return GuardDecision(blocked=False, source="fallback", reason="low confidence")
    if intent.in_scope and intent.label == "fitness":
        return GuardDecision(
            blocked=False,
            wants_tool=intent.wants_tool,
            source="classifier",
            reason=intent.reason,
        )
    if message and intent.label in _SCOPE_LABELS and _is_personal_data_question(message):
        return GuardDecision(
            blocked=False,
            wants_tool=False,
            source="deterministic",
            reason="own-data question; scope refusal overridden",
        )
    return GuardDecision(
        blocked=True,
        category=intent.label,
        response=get_safe_reply(intent.label),
        wants_tool=False,
        source="classifier",
        reason=intent.reason,
    )


def classify_and_decide(
    message: str,
    user_id: str,
    classifier: IntentClassifier | None = None,
    *,
    conf_threshold: float | None = None,
) -> GuardDecision:
    """Gate one message and return the decision. Never raises."""
    threshold = settings.guard_conf_threshold if conf_threshold is None else conf_threshold

    # 1. Deterministic rules first: fast, fail-closed, and they cover the
    #    safety-critical categories without any model call.
    rules = run_safety_rules(message)
    if rules.blocked:
        return GuardDecision(
            blocked=True,
            category=rules.category,
            response=rules.response or get_safe_reply(rules.category),
            wants_tool=False,
            source="deterministic",
            reason="deterministic rule match",
        )

    # 2. No classifier wired -> deterministic allow (current behaviour).
    if classifier is None:
        return GuardDecision(blocked=False, source="deterministic", reason="classifier disabled")

    # 3. Cache: reuse a recent real decision for the same (user, message).
    key = _cache_key(user_id, message)
    cached = _get_cached(key)
    if cached is not None:
        return cached

    # 4. One classifier call. ``classify`` never raises; ``None`` means the
    #    provider failed or the output was unusable -> fallback, do not cache.
    intent = classifier.classify(message)
    if intent is None:
        return GuardDecision(blocked=False, source="fallback", reason="classifier unavailable")

    decision = _decide_from_intent(intent, threshold, message)
    if decision.source == "classifier":
        _set_cached(key, decision)
    return decision


def log_guard_turn(
    user_id: str,
    decision: GuardDecision,
    *,
    latency_ms: float,
    mode: str,
) -> None:
    """Emit one structured, content-free log line for a gated turn."""
    log.info(
        "guard_turn user_id=%s category=%s source=%s blocked=%s wants_tool=%s "
        "latency_ms=%d mode=%s reason=%s",
        user_id,
        decision.category,
        decision.source,
        decision.blocked,
        decision.wants_tool,
        int(latency_ms),
        mode,
        decision.reason,
    )


def guarded_run(
    message: str,
    user_id: str,
    classifier: IntentClassifier | None = None,
    *,
    conf_threshold: float | None = None,
) -> GuardDecision:
    """Single choke point: gate a message, log the turn, return the decision.

    Callers enforce ``decision.blocked`` according to ``settings.guardrails_mode``
    (enforce blocks, monitor only logs). Refusals must never reach the model,
    tools, memory extraction, or persistence.
    """
    start = time.monotonic()
    decision = classify_and_decide(message, user_id, classifier, conf_threshold=conf_threshold)
    latency_ms = (time.monotonic() - start) * 1000
    log_guard_turn(user_id, decision, latency_ms=latency_ms, mode=settings.guardrails_mode)
    return decision


__all__ = [
    "GuardDecision",
    "classify_and_decide",
    "clear_decision_cache",
    "guarded_run",
    "log_guard_turn",
]
