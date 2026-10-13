"""Deterministic safety guardrails for FitAI.

This module is the first-line screen for sensitive or risky requests. It is NOT a
substitute for a full moderation model, but it provides fail-closed blocking for
clear categories before any tool, memory, or LLM call is made.
"""

from __future__ import annotations

import re

from pydantic import BaseModel


class SafetyResult(BaseModel):
    blocked: bool = False
    category: str | None = None
    response: str | None = None  # fixed safe reply when blocked


_SAFE_REPLIES = {
    "self_harm": (
        "I'm really sorry you're going through this. I can't help with this here, but please "
        "contact local emergency services or a crisis line right now, or reach out to someone you trust."
    ),
    "medical_emergency": (
        "That could be a medical emergency. Please contact local emergency services "
        "or get urgent medical help now rather than relying on a chatbot."
    ),
    "extreme_restriction": (
        "I can't help with extreme restriction or disordered-eating approaches. "
        "If this is about you, a doctor or registered dietitian can help; I'm glad to "
        "support safe, sustainable nutrition instead."
    ),
    "drug_dosing": (
        "I can't provide dosing or cycle guidance for steroids or similar drugs. "
        "A licensed clinician is the right source for that."
    ),
}

_SAFETY_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("self_harm", re.compile(r"\b(kill myself|suicid\w*|self[- ]harm|end my life)\b", re.I)),
    (
        "medical_emergency",
        re.compile(r"\b(chest pain|can'?t breathe|heart attack|passed out|fainted)\b", re.I),
    ),
    (
        "extreme_restriction",
        re.compile(
            r"\b(anorexi\w*|bulimi\w*|thinspo|pro[- ]?ana|purg\w+|starv\w+ myself|"
            r"(?:under|below|less than)\s*[1-8]\d\d\s*(?:calories|kcal))\b",
            re.I,
        ),
    ),
    (
        "drug_dosing",
        re.compile(
            r"\b(?:steroids?|trenbolone|clenbuterol|dnp|sarms?)\b.*\b(?:dos(?:e|age)|cycle|stack|inject\w*|mg)\b|"
            r"\b(?:dos(?:e|age)|cycle|stack|inject\w*)\b.*\b(?:steroids?|trenbolone|clenbuterol|dnp|sarms?)\b",
            re.I | re.S,
        ),
    ),
]


def run_safety_rules(message: str) -> SafetyResult:
    """Return a blocked result if the message matches a safety rule."""
    for category, pattern in _SAFETY_RULES:
        if pattern.search(message):
            return SafetyResult(blocked=True, category=category, response=_SAFE_REPLIES[category])
    return SafetyResult()
