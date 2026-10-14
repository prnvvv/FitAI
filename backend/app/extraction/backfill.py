"""Historical backfill of structured facts from existing conversations.

This is an ON-DEMAND maintenance operation (``python -m app.extraction.backfill``),
never run automatically on chat or startup. It re-reads a user's stored messages,
runs the dedicated extractor, and persists facts through the same idempotent
pipeline used for live messages, so re-running is safe (duplicates are detected,
never blindly overwritten) and each user's data is strictly isolated.

Bounded + checkpointed: it processes a maximum number of messages per invocation
and pages through conversations/messages, so a huge history can be processed in
controlled batches rather than all at once on every call.
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.extraction.extractor import RecordExtractor
from app.extraction.persistence import persist_extraction
from app.models.enums import MessageRole
from app.models.user import User
from app.repositories.conversation_repository import (
    ConversationRepository,
    MessageRepository,
)

log = logging.getLogger(__name__)


@dataclass
class BackfillReport:
    """Counts for one backfill run."""

    users_processed: int = 0
    messages_scanned: int = 0
    messages_with_facts: int = 0
    saved: int = 0
    duplicates: int = 0
    failed: int = 0

    def __str__(self) -> str:  # pragma: no cover - human-readable summary
        return (
            f"users={self.users_processed} scanned={self.messages_scanned} "
            f"with_facts={self.messages_with_facts} saved={self.saved} "
            f"duplicates={self.duplicates} failed={self.failed}"
        )


def _aware(dt: datetime) -> datetime:
    """Return a timezone-aware datetime (assume UTC when naive)."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


class BackfillService:
    """Re-extract and persist facts from a user's historical messages."""

    def __init__(self, db: Session, extractor: RecordExtractor | None) -> None:
        self._db = db
        self._extractor = extractor

    def backfill_user(
        self,
        user_id: UUID,
        *,
        max_messages: int = 400,
        page_size: int = 50,
    ) -> BackfillReport:
        report = BackfillReport(users_processed=1)
        if self._extractor is None:
            return report
        conversations = ConversationRepository(self._db)
        messages = MessageRepository(self._db)

        conv_page = 0
        while report.messages_scanned < max_messages:
            convs, _total = conversations.list_for_user(
                user_id, limit=page_size, offset=conv_page * page_size
            )
            if not convs:
                break
            for conversation in convs:
                if report.messages_scanned >= max_messages:
                    break
                msg_page = 0
                while report.messages_scanned < max_messages:
                    rows, _msg_total = messages.list_for_conversation(
                        conversation.id, limit=page_size, offset=msg_page * page_size
                    )
                    if not rows:
                        break
                    for message in rows:
                        if report.messages_scanned >= max_messages:
                            break
                        if message.role is MessageRole.USER and (message.content or "").strip():
                            self._process_message(
                                user_id, message.content, message.created_at, report
                            )
                        report.messages_scanned += 1
                    msg_page += 1
            conv_page += 1
        return report

    def backfill_all(self, *, max_messages_per_user: int = 400) -> BackfillReport:
        report = BackfillReport()
        if self._extractor is None:
            return report
        user_ids = list(self._db.scalars(select(User.id)))
        for user_id in user_ids:
            user_report = self.backfill_user(user_id, max_messages=max_messages_per_user)
            report.users_processed += user_report.users_processed
            report.messages_scanned += user_report.messages_scanned
            report.messages_with_facts += user_report.messages_with_facts
            report.saved += user_report.saved
            report.duplicates += user_report.duplicates
            report.failed += user_report.failed
        return report

    def _process_message(
        self, user_id: UUID, content: str, created_at: datetime, report: BackfillReport
    ) -> None:
        if self._extractor is None:
            return
        when = _aware(created_at)
        try:
            result = self._extractor.extract(content, now=when)
        except Exception:
            log.warning("backfill extraction failed", exc_info=True)
            report.failed += 1
            return
        if not result.has_any():
            return
        report.messages_with_facts += 1
        try:
            outcomes = persist_extraction(self._db, user_id, result, now=when)
        except Exception:
            log.warning("backfill persist failed", exc_info=True)
            report.failed += 1
            return
        for outcome in outcomes:
            if outcome.status == "saved":
                report.saved += 1
            elif outcome.status == "duplicate":
                report.duplicates += 1
            elif outcome.status == "failed":
                report.failed += 1


def build_backfill_service(db: Session) -> BackfillService:
    """Build a backfill service with the dedicated extractor from settings.

    Returns a service whose extractor is None when extraction is not configured,
    so ``backfill_user``/``backfill_all`` become safe no-ops.
    """
    from app.core.config import settings
    from app.extraction.extractor import GroqActivityExtractor

    if not settings.extraction_enabled:
        return BackfillService(db, None)
    try:
        extractor: RecordExtractor = GroqActivityExtractor(
            api_key=settings.extraction_api_key or "",
            model=settings.extraction_model,
        )
    except Exception:
        log.warning("could not initialise extraction for backfill", exc_info=True)
        return BackfillService(db, None)
    return BackfillService(db, extractor)


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill structured facts from chat history.")
    parser.add_argument("--user", help="Restrict to a single user id (UUID).", default=None)
    parser.add_argument("--max", type=int, default=400, help="Max messages per user.")
    args = parser.parse_args(argv)

    from app.db.session import SessionLocal

    with SessionLocal() as db:
        service = build_backfill_service(db)
        if args.user:
            report = service.backfill_user(UUID(args.user), max_messages=args.max)
        else:
            report = service.backfill_all(max_messages_per_user=args.max)
        print(f"Backfill complete: {report}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
