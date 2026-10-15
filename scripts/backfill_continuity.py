"""Backfill cross-chat continuity vectors from existing data.

Rebuilds the owner-scoped continuity index (``user_continuity``) from the
authoritative database: one summary vector per existing conversation and one
fact vector per current memory. Safe by default: it runs a **dry run** that only
reports what would be indexed. Pass ``--apply`` to actually summarise, persist,
and index. Nothing is deleted; ``sync_memories`` only prunes facts that no longer
exist.

Usage (from the repository root):

    python -m scripts.backfill_continuity                # dry run, all users
    python -m scripts.backfill_continuity --apply        # apply, all users
    python -m scripts.backfill_continuity --apply --user <uuid>

Requires ``CONTINUITY_ENABLED`` and configured LLM/embedding providers.
"""

from __future__ import annotations

import argparse
import multiprocessing
import sys
from pathlib import Path
from uuid import UUID

if sys.platform == "win32":
    multiprocessing.set_start_method("spawn", force=True)

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.user import User
from app.services.chat_service import ChatService
from app.services.conversation_service import ConversationService
from app.services.memory_service import MemoryService
from sqlalchemy import select

_PAGE = 100


def _target_users(db, user: str | None) -> list[UUID]:
    if user:
        return [UUID(user)]
    return list(db.scalars(select(User.id).order_by(User.created_at)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill continuity vectors.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually summarise and index (default: dry run).",
    )
    parser.add_argument("--user", default=None, help="Limit to one user UUID.")
    args = parser.parse_args(argv)

    if not settings.continuity_enabled:
        print("CONTINUITY_ENABLED is false; nothing to do.")
        return 1

    db = SessionLocal()
    try:
        users = _target_users(db, args.user)
        print(f"{'apply' if args.apply else 'dry-run'}: {len(users)} user(s)")
        for user_id in users:
            service = ChatService(db)
            conversations, _ = ConversationService(db).list_conversations(
                user_id, limit=_PAGE, offset=0
            )
            for conversation in conversations:
                try:
                    messages = ConversationService(db).list_recent_messages(
                        user_id, conversation.id, limit=40
                    )
                except Exception as exc:  # noqa: BLE001
                    print(
                        f"  skip conversation {conversation.id}: {type(exc).__name__}"
                    )
                    continue
                if not messages:
                    continue
                print(
                    f"  user={user_id} conversation={conversation.id} "
                    f"messages={len(messages)} -> summary"
                )
                if args.apply:
                    service._summarize_conversation(
                        user_id, conversation.id, conversation.title
                    )

            memories = MemoryService(db).list_current(user_id) if args.apply else []
            if args.apply:
                store = service._continuity_store()
                if store is not None:
                    service._index_memories(user_id, store)
            print(f"  user={user_id} memories={len(memories)} -> indexed")
        if not args.apply:
            print("dry-run complete; re-run with --apply to persist and index.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
