"""Deterministic reconciliation of proposed insights against stored memory.

The extraction LLM only *proposes* facts. This module decides, in pure Python,
what should actually happen to the user's durable memory:

* nothing useful / hypothetical / planned       -> ignore (never a fact)
* low confidence or hedged                      -> keep flagged for confirmation
* same statement as something already stored     -> retain (refresh evidence)
* explicit correction of a stored fact          -> supersede current, keep history
* historical statement                          -> stored as historical, never current
* genuinely new                                -> create

Deduplication is token-signature + Jaccard similarity rather than exact string
equality, so "cycles every morning" and "cycling every morning" collapse into one
record, and a paraphrase never creates a second row.

Storage format (one authoritative location)::

    user_profiles.preferences["memory_insights"]       # live records
    user_profiles.preferences["memory_insight_history"] # superseded / corrections

Every stored record is a plain dict so it survives a JSON column unchanged::

    {"key": "insight:<sig>", "text": "...", "category": "activity_preference",
     "status": "current", "confidence": 0.9, "stated_at": "2026-01-01T00:00:00Z",
     "source_text": "...", "polarity": "affirm", "needs_confirmation": false}
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.extraction.schemas import (
    InsightStatus,
    MemoryInsight,
    ProposedAction,
    normalize_fact_text,
)

INSIGHTS_KEY = "memory_insights"
HISTORY_KEY = "memory_insight_history"

#: Below this similarity two statements are considered different facts.
SIMILARITY_THRESHOLD = 0.62
#: Tokens are truncated to this length for identity comparison (see `tokens`).
TOKEN_PREFIX = 4
#: Default confidence floor; weaker candidates are not stored as facts.
DEFAULT_MIN_CONFIDENCE = 0.5
#: Bounds so a long history can never grow the preferences JSON without limit.
MAX_LIVE_INSIGHTS = 40
MAX_HISTORY = 40

#: Words that carry no distinguishing meaning for fact identity.
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "the",
        "i",
        "im",
        "ive",
        "my",
        "me",
        "we",
        "our",
        "you",
        "your",
        "he",
        "she",
        "it",
        "they",
        "them",
        "his",
        "her",
        "its",
        "is",
        "are",
        "am",
        "was",
        "were",
        "be",
        "been",
        "being",
        "do",
        "does",
        "did",
        "doing",
        "done",
        "have",
        "has",
        "had",
        "usually",
        "often",
        "always",
        "every",
        "each",
        "day",
        "days",
        "morning",
        "night",
        "evening",
        "weekly",
        "really",
        "very",
        "much",
        "more",
        "most",
        "often",
        "sometimes",
        "like",
        "likes",
        "love",
        "loves",
        "enjoy",
        "enjoys",
        "enjoying",
        "enjoyed",
        "prefer",
        "prefers",
        "preference",
        "and",
        "or",
        "so",
        "to",
        "of",
        "in",
        "on",
        "at",
        "for",
        "with",
        "about",
        "from",
        "that",
        "this",
        "these",
        "those",
        "there",
        "here",
        "what",
        "which",
        "who",
        "when",
    ]
)
_TOKEN_RE = re.compile(r"[a-z0-9]+")
#: Retraction markers: they flip the polarity of an otherwise similar statement.
_NEGATION_RE = re.compile(
    r"\b(no longer|not|never|none|don'?t|do not|doesn'?t|didn'?t|can'?t|won'?t|"
    r"stopped|quit|gave up|used to|no more|dislike|hate|avoid)\b",
    re.I,
)


def normalize(text: str) -> str:
    """Return a lower-cased, punctuation-free, whitespace-collapsed form."""
    lowered = text.lower()
    lowered = re.sub(r"[^a-z0-9\s]", " ", lowered)
    return " ".join(lowered.split())


def tokens(text: str) -> frozenset[str]:
    """Return the meaningful tokens of a statement, stemmed for identity.

    Tokens are truncated to :data:`TOKEN_PREFIX` characters so morphological
    variants collapse ("cycles"/"cycling", "jogs"/"jogging") without a full
    stemmer. Paraphrases of the same fact therefore share an identity key.
    """
    out = set()
    for token in _TOKEN_RE.findall(normalize(text)):
        if token in _STOPWORDS:
            continue
        out.add(token[:TOKEN_PREFIX])
    return frozenset(out)


def signature(text: str) -> str:
    """Stable, order-independent fingerprint used as the durable memory key."""
    digest = hashlib.sha1("|".join(sorted(tokens(text))).encode()).hexdigest()
    return f"insight:{digest[:16]}"


def polarity(text: str) -> str:
    """``negate`` when the statement retracts/denies a subject, else ``affirm``."""
    return "negate" if _NEGATION_RE.search(text) else "affirm"


def similarity(left: str, right: str) -> float:
    """Blended similarity used for duplicate detection.

    Half Jaccard (both statements talk about the same thing) and half
    containment (one is an elaboration of the other, e.g. "enjoys jogging" vs
    "does not enjoy jogging anymore"). Exact shared tokens are required, so an
    unrelated statement never scores high.
    """
    a, b = tokens(left), tokens(right)
    if not a or not b:
        return 0.0
    shared = len(a & b)
    if shared == 0:
        return 0.0
    jaccard = shared / len(a | b)
    containment = shared / min(len(a), len(b))
    return (jaccard + containment) / 2


@dataclass(frozen=True)
class InsightDecision:
    """What the backend will do with one proposed insight."""

    action: ProposedAction
    key: str
    text: str
    status: InsightStatus
    reason: str
    #: Existing record replaced by this decision (kept in history, not deleted).
    supersedes: Mapping[str, Any] | None = None
    #: Existing record refreshed by this decision.
    retains: Mapping[str, Any] | None = None
    needs_confirmation: bool = False

    @property
    def should_store(self) -> bool:
        return self.action in (
            ProposedAction.CREATE,
            ProposedAction.UPDATE,
            ProposedAction.RETAIN,
            ProposedAction.CONFIRM,
        )


def _parse_ts(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _is_live(record: Mapping[str, Any]) -> bool:
    return record.get("status") != "superseded" and record.get("status") != "deleted"


def reconcile(
    candidate: MemoryInsight,
    existing: Sequence[Mapping[str, Any]],
    *,
    now: datetime | None = None,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> InsightDecision:
    """Decide how one candidate interacts with what is already remembered.

    Args:
        candidate: The validated candidate proposed by the extraction LLM.
        existing: All live insight records currently stored for the user.
        now: Timestamp used for the decision (message time, so backfill keeps
            the original ordering of statements).
        min_confidence: Candidates weaker than this are never stored as facts.
    """
    now = now or datetime.now(timezone.utc)
    key = signature(candidate.text)
    text = candidate.text

    if candidate.action is ProposedAction.IGNORE or candidate.status in (
        InsightStatus.HYPOTHETICAL,
        InsightStatus.PLANNED,
    ):
        return InsightDecision(
            ProposedAction.IGNORE,
            key,
            text,
            candidate.status,
            f"{candidate.status.value} statement is not a durable fact",
        )

    if candidate.confidence < min_confidence:
        return InsightDecision(
            ProposedAction.IGNORE,
            key,
            text,
            candidate.status,
            f"confidence {candidate.confidence:.2f} below floor {min_confidence:.2f}",
        )

    if candidate.status is InsightStatus.UNCERTAIN or candidate.action is ProposedAction.CONFIRM:
        return InsightDecision(
            ProposedAction.CONFIRM,
            key,
            text,
            candidate.status,
            "statement is hedged; needs user confirmation",
            needs_confirmation=True,
        )

    new_polarity = polarity(candidate.source_text or text)
    best: tuple[float, Mapping[str, Any]] | None = None
    for record in existing:
        if not _is_live(record):
            continue
        score = similarity(candidate.text, str(record.get("text", "")))
        if score >= SIMILARITY_THRESHOLD and (best is None or score > best[0]):
            best = (score, record)

    if best is not None:
        record = best[1]
        recorded_polarity = str(record.get("polarity", "affirm"))
        recorded_status = str(record.get("status", "current"))
        same_polarity = new_polarity == recorded_polarity

        # An older statement never overwrites a newer one just because it was
        # processed later (important for historical backfill).
        previous_at = _parse_ts(record.get("stated_at"))
        if previous_at is not None and previous_at > now and not candidate.corrects:
            return InsightDecision(
                ProposedAction.RETAIN,
                str(record.get("key", key)),
                str(record.get("text", text)),
                candidate.status,
                "newer statement already stored",
                retains=record,
            )

        if same_polarity:
            return InsightDecision(
                ProposedAction.RETAIN,
                str(record.get("key", key)),
                text,
                candidate.status,
                "already remembered",
                retains=record,
            )

        # Opposite polarity on the same subject: a correction. The previous
        # statement becomes history, the new one becomes the current fact.
        corrected = (
            candidate.corrects
            or recorded_status == "historical"
            or candidate.status is InsightStatus.HISTORICAL
        )
        if not corrected:
            return InsightDecision(
                ProposedAction.CONFIRM,
                key,
                text,
                InsightStatus.UNCERTAIN,
                "contradicts a remembered fact; needs confirmation",
                needs_confirmation=True,
            )
        return InsightDecision(
            ProposedAction.UPDATE,
            key,
            text,
            candidate.status,
            "corrects a remembered fact",
            supersedes=record,
        )

    action = ProposedAction.UPDATE if candidate.corrects else ProposedAction.CREATE
    return InsightDecision(action, key, text, candidate.status, "new durable fact")


@dataclass
class InsightStore:
    """In-memory view of the user's stored insights, used by the persister."""

    live: list[dict[str, Any]] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_preferences(cls, preferences: object) -> InsightStore:
        prefs = preferences if isinstance(preferences, Mapping) else {}
        live = [r for r in (prefs.get(INSIGHTS_KEY) or []) if isinstance(r, Mapping)]
        history = [r for r in (prefs.get(HISTORY_KEY) or []) if isinstance(r, Mapping)]
        return cls(live=[dict(r) for r in live], history=[dict(r) for r in history])

    def as_preferences(self) -> dict[str, list[dict[str, Any]]]:
        return {
            INSIGHTS_KEY: self.live[-MAX_LIVE_INSIGHTS:],
            HISTORY_KEY: self.history[-MAX_HISTORY:],
        }

    def record_for(self, decision: InsightDecision) -> Mapping[str, Any] | None:
        """Return the stored record a decision refers to (after applying)."""
        for entry in self.live:
            if entry.get("key") == decision.key:
                return entry
        return None

    def current_texts(self, limit: int = 12) -> list[str]:
        """Confirmed current facts, newest first (what retrieval may inject)."""
        out = [
            str(entry.get("text", ""))
            for entry in self.live
            if entry.get("status") == "current" and not entry.get("needs_confirmation")
        ]
        return [t for t in reversed(out) if t][:limit]


def apply_decision(
    store: InsightStore,
    decision: InsightDecision,
    candidate: MemoryInsight,
    *,
    now: datetime,
) -> None:
    """Mutate ``store`` in place according to a :func:`reconcile` decision."""
    stamp = now.isoformat()
    if not decision.should_store:
        return

    if decision.action is ProposedAction.RETAIN and decision.retains is not None:
        target = decision.retains
        target["stated_at"] = stamp
        target["confidence"] = max(
            float(target.get("confidence", 0.0)), float(candidate.confidence)
        )
        if candidate.source_text:
            target["source_text"] = candidate.source_text[:200]
        return

    record: dict[str, Any] = {
        "key": decision.key,
        "text": normalize_fact_text(decision.text),
        "category": candidate.category,
        "status": decision.status.value,
        "confidence": float(candidate.confidence),
        "stated_at": stamp,
        "source_text": (candidate.source_text or "")[:200],
        "polarity": polarity(candidate.source_text or decision.text),
        "needs_confirmation": decision.needs_confirmation,
    }

    if decision.supersedes is not None:
        replaced = dict(decision.supersedes)
        replaced["status"] = "superseded"
        replaced["superseded_at"] = stamp
        store.history.append(replaced)
        store.live = [r for r in store.live if r.get("key") != replaced.get("key")]

    store.live = [r for r in store.live if r.get("key") != decision.key]
    store.live.append(record)
