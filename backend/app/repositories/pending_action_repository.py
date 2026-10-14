"""Pending chat action persistence."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import PendingActionStatus, PendingActionType
from app.models.pending_action import PendingChatAction


class PendingActionRepository:
    """Persistence operations for pending chat actions."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def create(
        self,
        user_id: UUID,
        conversation_id: UUID,
        action_type: PendingActionType,
        payload: dict[str, object],
        summary: str,
    ) -> PendingChatAction:
        """Create and persist a pending action."""
        action = PendingChatAction(
            user_id=user_id,
            conversation_id=conversation_id,
            action_type=action_type,
            payload=payload,
            summary=summary,
            status=PendingActionStatus.PENDING,
        )
        self._db.add(action)
        self._db.flush()
        return action

    def get_for_user(self, action_id: UUID, user_id: UUID) -> PendingChatAction | None:
        """Return an action only when it belongs to ``user_id``."""
        statement = select(PendingChatAction).where(
            PendingChatAction.id == action_id,
            PendingChatAction.user_id == user_id,
        )
        return self._db.scalar(statement)

    def get_for_update(self, action_id: UUID, user_id: UUID) -> PendingChatAction | None:
        """Lock and return an action for an atomic state transition."""
        statement = (
            select(PendingChatAction)
            .where(
                PendingChatAction.id == action_id,
                PendingChatAction.user_id == user_id,
            )
            .with_for_update()
        )
        return self._db.scalar(statement)

    def list_for_user(
        self,
        user_id: UUID,
        *,
        status: PendingActionStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[list[PendingChatAction], int]:
        """Return a page of actions for ``user_id`` and the total count."""
        filters = [PendingChatAction.user_id == user_id]
        if status is not None:
            filters.append(PendingChatAction.status == status)
        total = self._db.scalar(
            select(func.count()).select_from(PendingChatAction).where(*filters)
        )
        statement = (
            select(PendingChatAction)
            .where(*filters)
            .order_by(PendingChatAction.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self._db.scalars(statement)), int(total or 0)
