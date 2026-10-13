"""Decide auto-apply vs pending proposal, and execute through an injected writer.

Contract for the persistence developer (`MemoryWriter`): each method must return
truthy ONLY after the write is durably committed. Raise or return False/None
otherwise. This module reports success solely from those return values.
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import Literal, Protocol

from pydantic import BaseModel

from .change_detector import ChangeKind, DetectedChange
from .extractor import StatementType, Tense
from .history import HistoryRecord, build_history_record

log = logging.getLogger(__name__)


class Action(str, Enum):
    AUTO_APPLY = "auto_apply"
    CREATE_PENDING = "create_pending"
    RECORD_HISTORY = "record_history"
    SKIP = "skip"


class ConfirmationPolicy(BaseModel):
    allow_auto_apply: bool = True
    min_confidence: float = 0.85
    auto_fields: frozenset[str] = frozenset({"weight", "height", "body_fat", "measurement"})


class Decision(BaseModel):
    change: DetectedChange
    action: Action
    reason: str


class MemoryWriter(Protocol):
    """Implemented by the existing memory/profile service (adapter)."""

    def apply_update(self, user_id: str, change: DetectedChange) -> bool:
        """Set the current value. True only once committed."""

    def create_pending(self, user_id: str, decision: Decision) -> str | None:
        """Store a pending proposal. Return its id once committed, else None."""

    def record_history(self, user_id: str, record: HistoryRecord) -> bool:
        """Append a history row. True only once committed."""


class ApplyResult(BaseModel):
    key: str
    action: Action
    status: Literal["applied", "pending_created", "history_recorded", "failed", "skipped"]
    summary: str = ""
    detail: str | None = None
    proposal_id: str | None = None
    history_recorded: bool = False


def decide(change: DetectedChange, policy: ConfirmationPolicy | None = None) -> Decision:
    """Pure policy decision for one change. Anything doubtful becomes a proposal."""
    policy = policy or ConfirmationPolicy()
    f, kind = change.fact, change.kind

    def d(action: Action, reason: str) -> Decision:
        return Decision(change=change, action=action, reason=reason)

    if kind in (ChangeKind.NOT_CURRENT, ChangeKind.UNCHANGED):
        return d(Action.SKIP, kind.value)
    if kind is ChangeKind.CONTRADICTION:
        return d(Action.CREATE_PENDING, f"contradiction: {change.reason}")

    confident = f.confidence >= policy.min_confidence
    if kind is ChangeKind.HISTORICAL_EVENT:
        if build_history_record(f) is None:
            return d(Action.CREATE_PENDING, "historical event without a verifiable date")
        if (policy.allow_auto_apply and confident
                and f.statement_type in (StatementType.EXPLICIT, StatementType.HISTORICAL)):
            return d(Action.RECORD_HISTORY, "dated, confident historical record")
        return d(Action.CREATE_PENDING, "historical record needs confirmation")

    # NEW / CHANGED current values
    if (policy.allow_auto_apply and f.field in policy.auto_fields and confident
            and f.statement_type is StatementType.EXPLICIT and f.tense is Tense.PRESENT):
        return d(Action.AUTO_APPLY, "explicit, validated, high-confidence")
    return d(Action.CREATE_PENDING, "needs confirmation (policy/confidence/certainty)")


def decide_all(changes: list[DetectedChange], policy: ConfirmationPolicy | None = None) -> list[Decision]:
    return [decide(c, policy) for c in changes]


def _summary(c: DetectedChange) -> str:
    f = c.fact
    return f"{f.key} = {f.value}{' ' + f.unit if f.unit else ''}"


def apply_decisions(user_id: str, decisions: list[Decision], writer: MemoryWriter) -> list[ApplyResult]:
    """Execute decisions via the writer. Service errors become `failed` results."""
    results: list[ApplyResult] = []
    for dec in decisions:
        c = dec.change
        res = ApplyResult(key=c.fact.key, action=dec.action, status="skipped", summary=_summary(c))
        try:
            if dec.action is Action.AUTO_APPLY:
                if writer.apply_update(user_id, c) is True:
                    res.status = "applied"
                    rec = build_history_record(c.fact)
                    if rec:
                        res.history_recorded = writer.record_history(user_id, rec) is True
                else:
                    res.status, res.detail = "failed", "service did not confirm update"
            elif dec.action is Action.RECORD_HISTORY:
                rec = build_history_record(c.fact)
                ok = rec is not None and writer.record_history(user_id, rec) is True
                res.status = "history_recorded" if ok else "failed"
                res.history_recorded = ok
                res.detail = None if ok else "service did not confirm history record"
            elif dec.action is Action.CREATE_PENDING:
                pid = writer.create_pending(user_id, dec)
                res.status = "pending_created" if pid else "failed"
                res.proposal_id = pid or None
                res.detail = None if pid else "service did not create proposal"
        except Exception as exc:  # service failure: never report success
            log.warning("memory write failed for %s: %s", res.key, exc)
            res.status, res.detail = "failed", f"{type(exc).__name__}"
        results.append(res)
    return results
