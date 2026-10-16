"""Unit tests for deterministic insight reconciliation.

These cover the required memory rules: durable preference, routine, project,
hypothetical, historical, correction, low confidence and duplicate handling.
No LLM, no database, no network.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.extraction.reconciliation import (
    InsightStore,
    apply_decision,
    reconcile,
    signature,
    similarity,
)
from app.extraction.schemas import InsightStatus, MemoryInsight, ProposedAction

NOW = datetime(2026, 5, 20, 9, 0, tzinfo=timezone.utc)


def _insight(text: str, source_text: str = "", **kw) -> MemoryInsight:
    payload = {
        "text": text,
        "confidence": 0.9,
        "source_text": source_text or text,
        **kw,
    }
    return MemoryInsight.model_validate(payload)


def _stored(insights: InsightStore, text: str, **overrides) -> dict:
    """Simulate a previously stored current insight."""
    record = {
        "key": signature(text),
        "text": text,
        "category": "activity_preference",
        "status": "current",
        "confidence": 0.9,
        "stated_at": (NOW - timedelta(days=1)).isoformat(),
        "source_text": text,
        "polarity": "affirm",
        "needs_confirmation": False,
    }
    record.update(overrides)
    return record


# --- Example A/B/C: new durable facts ----------------------------------------
def test_durable_preference_is_created() -> None:
    fact = _insight("likes jogging", source_text="I like jogging")
    decision = reconcile(fact, [], now=NOW)
    assert decision.action is ProposedAction.CREATE
    assert decision.status is InsightStatus.CURRENT
    assert decision.should_store


def test_routine_is_created_as_current_fact() -> None:
    fact = _insight("cycles every morning", source_text="I usually cycle every morning")
    assert reconcile(fact, [], now=NOW).action is ProposedAction.CREATE


def test_learning_project_is_created() -> None:
    fact = _insight(
        "learning machine learning for a final-year project",
        source_text="I am learning machine learning for my final-year project",
        category="learning",
    )
    decision = reconcile(fact, [], now=NOW)
    assert decision.action is ProposedAction.CREATE
    assert decision.status is InsightStatus.CURRENT


# --- Example D: hypothetical must never become a fact ------------------------
def test_hypothetical_is_ignored() -> None:
    fact = _insight("might try swimming someday", source_text="I might try swimming someday")
    assert fact.status is InsightStatus.HYPOTHETICAL
    decision = reconcile(fact, [], now=NOW)
    assert decision.action is ProposedAction.IGNORE
    assert not decision.should_store


def test_planned_insight_is_ignored() -> None:
    fact = _insight("will start swimming in March", source_text="I will start swimming in March")
    fact = fact.model_copy(
        update={"status": InsightStatus.PLANNED, "action": ProposedAction.IGNORE}
    )
    assert not reconcile(fact, [], now=NOW).should_store


# --- Example E: historical keeps its status ---------------------------------
def test_historical_statement_stays_historical() -> None:
    fact = _insight("used to run every morning", source_text="I used to run every morning")
    assert fact.status is InsightStatus.HISTORICAL
    decision = reconcile(fact, [], now=NOW)
    assert decision.action is ProposedAction.CREATE
    assert decision.status is InsightStatus.HISTORICAL


def test_historical_fact_is_never_reported_as_current() -> None:
    store = InsightStore()
    fact = _insight("used to run every morning", source_text="I used to run every morning")
    apply_decision(store, reconcile(fact, store.live, now=NOW), fact, now=NOW)
    assert store.current_texts() == []


# --- Example F: correction --------------------------------------------------
def test_correction_supersedes_and_keeps_history() -> None:
    store = InsightStore(live=[_stored(InsightStore(), "enjoys jogging")])
    correction = _insight(
        "no longer enjoys jogging",
        source_text="I no longer enjoy jogging",
        corrects=True,
    )
    assert correction.status is InsightStatus.CURRENT  # a retraction happens now
    decision = reconcile(correction, store.live, now=NOW)
    assert decision.action is ProposedAction.UPDATE

    apply_decision(store, decision, correction, now=NOW)
    # The old preference is preserved as history, never silently dropped...
    superseded = [r for r in store.history if r["status"] == "superseded"]
    assert len(superseded) == 1
    assert superseded[0]["text"] == "enjoys jogging"
    # ...and the live fact is no longer the retracted one.
    assert [r["text"] for r in store.live] == ["no longer enjoys jogging"]


def test_contradiction_without_explicit_correction_requires_confirmation() -> None:
    existing = [_stored(InsightStore(), "enjoys jogging")]
    claim = _insight("does not enjoy jogging", source_text="jogging is not for me")
    claim = claim.model_copy(update={"corrects": False})
    decision = reconcile(claim, existing, now=NOW)
    assert decision.action is ProposedAction.CONFIRM
    assert decision.needs_confirmation


# --- Example: low confidence -------------------------------------------------
def test_low_confidence_is_skipped() -> None:
    weak = _insight("likes rowing", source_text="maybe rowing", confidence=0.2)
    weak = weak.model_copy(update={"status": InsightStatus.CURRENT})
    decision = reconcile(weak, [], now=NOW)
    assert decision.action is ProposedAction.IGNORE
    assert not decision.should_store


def test_uncertain_is_kept_flagged_not_asserted() -> None:
    hedged = _insight("weighs about 74 kg", source_text="I think I weigh about 74 kg")
    assert hedged.status is InsightStatus.UNCERTAIN
    decision = reconcile(hedged, [], now=NOW)
    assert decision.action is ProposedAction.CONFIRM
    assert decision.needs_confirmation
    store = InsightStore()
    apply_decision(store, decision, hedged, now=NOW)
    assert store.current_texts() == []  # never presented as a current fact


# --- duplicates / paraphrases -----------------------------------------------
def test_paraphrase_is_retained_not_duplicated() -> None:
    existing = [_stored(InsightStore(), "cycles every morning")]
    fact = _insight("cycling every morning", source_text="I cycle every morning")
    decision = reconcile(fact, existing, now=NOW)
    assert decision.action is ProposedAction.RETAIN
    assert decision.should_store


def test_signature_is_order_and_punctuation_insensitive() -> None:
    assert signature("Cycles every morning!") == signature("every morning, cycles")
    assert similarity("cycles every morning", "cycling in the morning") > 0.3


def test_retain_refreshes_evidence_without_adding_a_record() -> None:
    store = InsightStore(live=[_stored(InsightStore(), "cycles every morning")])
    fact = _insight("cycles every morning", source_text="I cycle every morning", confidence=0.95)
    apply_decision(store, reconcile(fact, store.live, now=NOW), fact, now=NOW)
    assert len(store.live) == 1
    assert store.live[0]["confidence"] == 0.95


# --- ordering: an old statement never wins ----------------------------------
def test_older_statement_does_not_replace_newer_fact() -> None:
    store = InsightStore(live=[_stored(InsightStore(), "cycles every morning")])
    store.live[0]["stated_at"] = NOW.isoformat()
    older = _insight("cycles every morning", source_text="I cycle every morning")
    decision = reconcile(older, store.live, now=NOW - timedelta(days=5))
    assert decision.action is ProposedAction.RETAIN
    assert decision.reason == "newer statement already stored"


def test_store_bounds_are_applied() -> None:
    store = InsightStore()
    for i in range(80):
        fact = _insight(f"likes activity number {i}", source_text=f"i like activity {i}")
        apply_decision(store, reconcile(fact, store.live, now=NOW), fact, now=NOW)
    prefs = store.as_preferences()
    assert len(prefs["memory_insights"]) <= 40


def test_store_reads_only_wellformed_records() -> None:
    store = InsightStore.from_preferences(
        {"memory_insights": [{"text": "a"}, "garbage"], "memory_insight_history": None}
    )
    assert store.live == [{"text": "a"}]
    assert store.history == []


# --- normalization of echoed first-person sentences -------------------------
def test_echoed_sentence_is_normalized_into_a_fact() -> None:
    from app.extraction.schemas import normalize_fact_text

    assert normalize_fact_text("I like cycling every day.") == "like cycling every day"
    assert normalize_fact_text("I'm learning machine learning.") == "learning machine learning"
    assert normalize_fact_text("My usual routine is cycling!") == "usual routine is cycling"
    # Already-normalized text and proper nouns are left alone.
    assert normalize_fact_text("likes cycling") == "likes cycling"
    assert normalize_fact_text("Swimming on Mondays") == "swimming on Mondays"


def test_normalized_insight_dedupes_against_the_echoed_form() -> None:
    from app.extraction.schemas import normalize_fact_text

    assert signature(normalize_fact_text("I like jogging.")) == signature("like jogging")
