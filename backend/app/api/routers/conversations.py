"""Conversation and message endpoints.

Chat orchestration is owned by Person 2. These endpoints expose persistence and
ownership-scoped retrieval only.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession, Pagination
from app.schemas.common import Page
from app.schemas.conversation import (
    ConversationCreate,
    ConversationOut,
    ConversationUpdate,
    MessageOut,
)
from app.services.conversation_service import ConversationService

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
def create_conversation(
    payload: ConversationCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> ConversationOut:
    """Create a new conversation for the authenticated user."""
    service = ConversationService(db)
    conversation = service.create(current_user.id, payload.title)
    return ConversationOut.model_validate(conversation)


@router.get("", response_model=Page[ConversationOut])
def list_conversations(
    current_user: CurrentUser,
    db: DbSession,
    pagination: Pagination,
) -> Page[ConversationOut]:
    """List the authenticated user's conversations, newest first."""
    service = ConversationService(db)
    items, total = service.list_conversations(
        current_user.id, limit=pagination.limit, offset=pagination.offset
    )
    return Page[ConversationOut](
        items=[ConversationOut.model_validate(item) for item in items],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get("/{conversation_id}", response_model=ConversationOut)
def get_conversation(
    conversation_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> ConversationOut:
    """Return one of the authenticated user's conversations."""
    service = ConversationService(db)
    conversation = service.get(current_user.id, conversation_id)
    return ConversationOut.model_validate(conversation)


@router.patch("/{conversation_id}", response_model=ConversationOut)
def rename_conversation(
    conversation_id: UUID,
    payload: ConversationUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> ConversationOut:
    """Rename one of the authenticated user's conversations."""
    service = ConversationService(db)
    conversation = service.rename(current_user.id, conversation_id, payload.title)
    return ConversationOut.model_validate(conversation)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    """Delete a conversation and its messages.

    The user's profile, memory, measurements, and workouts are unaffected.
    """
    ConversationService(db).delete(current_user.id, conversation_id)


@router.get("/{conversation_id}/messages", response_model=Page[MessageOut])
def list_messages(
    conversation_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
    pagination: Pagination,
) -> Page[MessageOut]:
    """Return a chronological page of messages for a conversation."""
    service = ConversationService(db)
    items, total = service.list_messages(
        current_user.id,
        conversation_id,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return Page[MessageOut](
        items=[MessageOut.model_validate(item) for item in items],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )
