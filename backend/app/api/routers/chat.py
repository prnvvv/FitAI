"""Chat endpoint: single-turn agent responses."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.chat import ChatActionResolution, ChatRequest, ChatResponse
from app.schemas.conversation import MessageOut
from app.services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse, status_code=status.HTTP_200_OK)
def send_message(
    payload: ChatRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> ChatResponse:
    """Send a message to FitAI and receive an assistant response.

    If `conversation_id` is omitted, a new conversation is created.
    """
    result = ChatService(db).chat(
        current_user,
        payload.message,
        payload.conversation_id,
    )
    return ChatResponse(**result)


@router.post("/actions/{action_id}/confirm", response_model=ChatActionResolution)
def confirm_action(
    action_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> ChatActionResolution:
    """Confirm a pending chat action and return the assistant's reply."""
    message = ChatService(db).confirm_action(current_user, action_id)
    return ChatActionResolution(message=MessageOut.model_validate(message))


@router.post("/actions/{action_id}/reject", response_model=ChatActionResolution)
def reject_action(
    action_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> ChatActionResolution:
    """Decline a pending chat action and return the assistant's reply."""
    message = ChatService(db).reject_action(current_user, action_id)
    return ChatActionResolution(message=MessageOut.model_validate(message))
