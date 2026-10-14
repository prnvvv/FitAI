"""Deterministic safety guardrails for FitAI.

This module is the first-line screen for sensitive or risky requests. It is NOT a
substitute for a full moderation model, but it provides fail-closed blocking for
clear categories before any tool, memory, or LLM call is made.
"""

from __future__ import annotations

import re
import unicodedata

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
    "prompt_injection": (
        "I'm here to help with fitness, nutrition, and recovery. I can't share my "
        "internal instructions or configuration, and I won't follow instructions "
        "embedded in messages or documents. What fitness goal can I help with?"
    ),
    "unsafe_training": (
        "Training through sharp pain or an injury can make it worse. Rest and have "
        "it assessed by a qualified professional; I'm glad to help you plan a safe, "
        "modified routine in the meantime."
    ),
    "medical_advice": (
        "I can't diagnose conditions. Please check with a qualified healthcare "
        "professional; I can still help with general training, nutrition, or "
        "recovery guidance."
    ),
    "off_topic": (
        "I'm FitAI, focused on fitness, nutrition, and recovery, so I can't help "
        "with that. Happy to help with your training, meals, or progress instead!"
    ),
    "capability_probe": (
        "I'm FitAI, focused on fitness, nutrition, and recovery. I can't help with "
        "coding or general programming questions. Happy to help with your training, "
        "meals, or progress instead!"
    ),
    "code_request": (
        "I can't write, debug, or explain code. I'm here to help with fitness, "
        "nutrition, and recovery. Want a workout plan, macro breakdown, or "
        "recovery tips instead?"
    ),
    "wrapper": (
        "I'm FitAI, focused on fitness, nutrition, and recovery. I can't write code, "
        "essays, or solve general-purpose tasks, but I'm happy to help with your "
        "training, nutrition, recovery, or your plan instead."
    ),
}


def _normalize(message: str) -> str:
    """Normalize message for matching: NFKC, strip zero-width/control, collapse whitespace, lowercase."""
    # NFKC normalization handles fullwidth chars, compatibility chars
    normalized = unicodedata.normalize("NFKC", message)
    # Remove zero-width and control characters (except newline/tab)
    normalized = "".join(ch for ch in normalized if ch == "\n" or ch == "\t" or not unicodedata.category(ch).startswith("C"))
    # Collapse whitespace
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip().lower()


_SAFETY_RULES: list[tuple[str, re.Pattern[str]]] = [
    # Self-harm
    (
        "self_harm",
        re.compile(r"\b(kill myself|suicid\w*|self[-]harm|end my life)\b", re.I),
    ),
    # Medical emergency
    (
        "medical_emergency",
        re.compile(r"\b(chest pain|can't? breathe|heart attack|passed out|fainted)\b", re.I),
    ),
    # Extreme restriction / eating disorders
    (
        "extreme_restriction",
        re.compile(
            r"\b(anorexi\w*|bulimi\w*|thinspo|pro[-]?ana|purg\w+|starv\w+ myself|"
            r"(?:under|below|less than)\s*[1-8]\d\d\s*(?:calories|kcal))\b",
            re.I,
        ),
    ),
    # Drug dosing / steroid cycles
    (
        "drug_dosing",
        re.compile(
            r"\b(?:steroids?|trenbolone|clenbuterol|dnp|sarms?)\b.*\b(?:dos(?:e|age)|cycle|stack|inject\w*|mg)\b|"
            r"\b(?:dos(?:e|age)|cycle|stack|inject\w*)\b.*\b(?:steroids?|trenbolone|clenbuterol|dnp|sarms?)\b",
            re.I | re.S,
        ),
    ),
    # Prompt injection / jailbreak / instruction override
    (
        "prompt_injection",
        re.compile(
            r"(ignore (?:all |any )?(?:the |your |those |these |previous |prior |above )?"
            r"(?:instructions?|rules?|guidelines?|prompt)s?)|"
            r"(reveal|show|print|disclose|expose|leak|repeat|dump|give me)\b[^.\n]{0,40}\b"
            r"(system prompt|instructions?|api key|secret| credentials?|env(?:ironment)?|config\w*|prompts?)|"
            r"\b(what are|what's|whats|tell me) your (instructions?|rules?|system prompt)\b|"
            r"\b(you are now|act as|jailbreak|developer mode|dan mode|bypass (?:your|the) (?:rules?|safety|filters?|restrictions?))\b|"
            r"<\s*/?(?:system|prompt)\b",
            re.I,
        ),
    ),
    # Unsafe training through injury
    (
        "unsafe_training",
        re.compile(
            r"(ignore (?:my|the|that)\s+[a-z ]{0,12}(injur\w+|pain)|"
            r"train(?:ing)?\s+through\s+(?:the\s+)?(?:pain|injur\w+)|"
            r"(?:work|run|lift)\s+through\s+(?:the\s+)?(?:pain|injur\w+))",
            re.I,
        ),
    ),
    # Medical diagnosis requests
    (
        "medical_advice",
        re.compile(
            r"\b(diagnose (?:me|my)|do i have|am i diagnosed|what disease do i have)\b", re.I
        ),
    ),
    # Capability probes: "do you know coding?", "can you code?", "are you good at python?"
    (
        "capability_probe",
        re.compile(
            r"\b(do you know|can you|are you (?:good at|familiar with|able to))\b.{0,30}\b"
            r"(cod(?:e|ing)|program(?:ming)?|script(?:ing)?|algorithm|data structure|"
            r"leetcode|python|javascript|typescript|java|c\+\+|rust|go|html|css|sql|regex)\b",
            re.I,
        ),
    ),
    # Code/algorithm requests: "give sliding window code", "write a sliding window function",
    # "implement sliding window", "two pointers", "dijkstra", "leetcode", etc.
    (
        "code_request",
        re.compile(
            r"\b(write|implement|give|create|build|generate|code|debug|explain|show)\b.{0,50}\b"
            r"(function|algorithm|script|program|class|method|snippet|code|sliding window|"
            r"two pointers?|binary search|dynamic programming|dijkstra|bfs|dfs|backtracking|"
            r"topological sort|union find|trie|heap|graph|tree|linked list|array|string|"
            r"leetcode|codeforces|hackerrank|interview question|coding challenge|data structure|"
            r"regex|regular expression|sql query|api|endpoint|database schema|"
            r"python|javascript|typescript|java|c\+\+|rust|go|html|css)\b"
            r"|\b(sliding window|two pointers?|binary search|dynamic programming|dijkstra|bfs|dfs|"
            r"backtracking|topological sort|union find|trie|heap|graph traversal|linked list|"
            r"leetcode|codeforces|hackerrank|algorithm|data structure)\b.{0,30}\b"
            r"(python|javascript|typescript|java|c\+\+|rust|go|implementation|code|example)\b",
            re.I,
        ),
    ),
    # Off-topic: code requests (write code / in language) OR bare "code" mention
    (
        "off_topic",
        re.compile(
            r"\b(write|code|generate|create)\b[^\n]{0,30}\b(Python|Java|JavaScript|C\+\+|Ruby|Go|SQL)\b"
            r"|\b(code)\b",
            re.I,
        ),
    ),
    # Off-topic: coding platforms (leetcode, etc.)
    (
        "off_topic",
        re.compile(r"\b(leetcode|codewars|hackerrank)\b", re.I),
    ),
    # Off-topic: algorithm requests (dijkstra, etc.)
    (
        "off_topic",
        re.compile(r"\b(algorithm|dijkstra)\b", re.I),
    ),
    # Off-topic: 'write me a/an' + language
    (
        "off_topic",
        re.compile(
            r"\b(write me a|write an|code in|using|with)\b[^\n]{0,50}\b(Python|Java|JavaScript|C|Ruby)\b",
            re.I,
        ),
    ),
    # Wrapper: requests framed as fitness but actually asking for code/general tasks
    (
        "wrapper",
        re.compile(
            r"\b(as (?:my |the )?fitness (?:app|coach|trainer)|for (?:my |the )?fitness (?:app|coach|trainer)|in (?:my |the )?fitness (?:app|coach|trainer)|"
            r"for a fitness app|for a training app|to track .{3,30})\b.*\b(code|python|javascript|sql|html|css|algorithm|function|script|loop|data structure|linked list|array|api)\b",
            re.I,
        ),
    ),
    # Off-topic: homework/essay/trivia
    (
        "off_topic",
        re.compile(
            r"\b(write me an? essay|write an? essay|write a story|creative writing)\b", re.I
        ),
    ),
    (
        "off_topic",
        re.compile(r"\b(do my homework|do homework|school assignment|homework)\b", re.I),
    ),
    (
        "off_topic",
        re.compile(r"\b(who (?:won|should i vote)|translate (?:this|the following))\b", re.I),
    ),
    # Off-topic: finance/crypto
    (
        "off_topic",
        re.compile(
            r"\b(buy|invest in|sell)\b[^\n]{0,20}\b(bitcoin|crypto|ethereum|stocks?|shares|forex)\b",
            re.I,
        ),
    ),
    (
        "off_topic",
        re.compile(r"\b(give me (?:stock|crypto|shares|equities|market))\b", re.I),
    ),
    # Conservative off-domain redirect. Deliberately narrow to avoid blocking
    # legitimate fitness conversation (never fires on common fitness wording).
    (
        "off_topic",
        re.compile(
            r"\b(write|code|debug)\b[^.\n]{0,20}\b(python|java(?:script)?|c\+\+|ruby|golang|"
            r"code|a poem|song(?: lyrics)?|an essay|a script|a short story|an email|a cover letter|"
            r"html|css|sql|a query)\b|"
            r"\b(do (?:my|the) homework|solve (?:this|the) (?:equation|math|problem)|"
            r"help me (?:cheat|hack))\b|"
            r"\b(buy|invest in|sell)\b[^.\n]{0,20}\b(bitcoin|crypto|ethereum|stocks?|shares|forex)\b|"
            r"\b(who (?:won|should i vote)|translate (?:this|the following|this sentence)|"
            r"write me (?:a )?(?:poem|song))\b",
            re.I,
        ),
    ),
]


def run_safety_rules(message: str) -> SafetyResult:
    """Return a blocked result if the message matches a safety rule.

    Normalizes the message first to defeat basic obfuscation (zero-width chars,
    fullwidth chars, excessive whitespace, case variation).
    Rules are checked in order; the first match wins. This ensures safety-critical
    categories (self_harm, medical_emergency) take precedence over scope checks.
    """
    normalized = _normalize(message)
    for category, pattern in _SAFETY_RULES:
        if pattern.search(normalized):
            return SafetyResult(blocked=True, category=category, response=_SAFE_REPLIES[category])
    return SafetyResult()