"""Chat endpoint: single-turn agent responses."""
from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.chat import ChatRequest, ChatResponse
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
