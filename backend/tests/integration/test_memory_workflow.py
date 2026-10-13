"""Service-level integration tests for the memory confirmation workflow."""

from __future__ import annotations

import uuid

import pytest

from app.core.errors import ConflictError, NotFoundError
from app.core.security import AuthUser
from app.models.enums import MemoryChangeType, MemoryKey
from app.services.auth_service import AuthService
from app.services.memory_service import MemoryService


def _user(db_session) -> uuid.UUID:
    auth_user = AuthUser(id=uuid.uuid4(), email="workflow@example.com")
    return AuthService(db_session).ensure_user(auth_user).id


def test_confirm_creates_memory_and_history(db_session) -> None:
    user_id = _user(db_session)
    service = MemoryService(db_session)

    proposal = service.create_proposal(user_id, MemoryKey.GOAL, "build muscle")
    memory = service.confirm(proposal.id, user_id)

    assert memory.value == "build muscle"
    assert memory.status.value == "active"

    history, total = service.list_history(user_id, limit=10, offset=0)
    assert total == 1
    assert history[0].change_type == MemoryChangeType.CREATE
    assert history[0].memory_id == memory.id
    assert history[0].previous_value is None
    assert history[0].new_value == "build muscle"


def test_update_appends_update_history(db_session) -> None:
    user_id = _user(db_session)
    service = MemoryService(db_session)

    first = service.create_proposal(user_id, MemoryKey.WEIGHT, {"value": 72, "unit": "kg"})
    service.confirm(first.id, user_id)

    second = service.create_proposal(user_id, MemoryKey.WEIGHT, {"value": 71, "unit": "kg"})
    memory = service.confirm(second.id, user_id)

    assert memory.value == {"value": 71, "unit": "kg"}
    _, total = service.list_history(user_id, limit=10, offset=0)
    assert total == 2


def test_correction_preserves_previous_value_in_history(db_session) -> None:
    user_id = _user(db_session)
    service = MemoryService(db_session)

    proposal = service.create_proposal(user_id, MemoryKey.HEIGHT, {"value": 180, "unit": "cm"})
    memory = service.confirm(proposal.id, user_id)

    corrected = service.correct(memory.id, user_id, {"value": 181, "unit": "cm"})
    assert corrected.value == {"value": 181, "unit": "cm"}

    history, total = service.list_history(user_id, limit=10, offset=0)
    assert total == 2
    update_record = [entry for entry in history if entry.change_type == MemoryChangeType.CORRECTION]
    assert update_record[0].previous_value == {"value": 180, "unit": "cm"}
    assert update_record[0].new_value == {"value": 181, "unit": "cm"}


def test_delete_soft_deletes_and_keeps_history(db_session) -> None:
    user_id = _user(db_session)
    service = MemoryService(db_session)

    proposal = service.create_proposal(user_id, MemoryKey.GOAL, "maintain")
    memory = service.confirm(proposal.id, user_id)
    service.delete(memory.id, user_id)

    assert service.list_current(user_id) == []
    _, total = service.list_history(user_id, limit=10, offset=0)
    assert total == 2
    with pytest.raises(ConflictError):
        service.delete(memory.id, user_id)


def test_confirmation_is_scoped_to_owner(db_session) -> None:
    owner_id = _user(db_session)
    other_id = _user(db_session)
    service = MemoryService(db_session)

    proposal = service.create_proposal(owner_id, MemoryKey.GOAL, "cut")
    with pytest.raises(NotFoundError):
        service.confirm(proposal.id, other_id)


def test_reject_does_not_touch_current_memory(db_session) -> None:
    user_id = _user(db_session)
    service = MemoryService(db_session)

    proposal = service.create_proposal(user_id, MemoryKey.GOAL, "bulk")
    rejected = service.reject(proposal.id, user_id)
    assert rejected.status.value == "rejected"
    assert service.list_current(user_id) == []
    with pytest.raises(ConflictError):
        service.confirm(proposal.id, user_id)


def test_stale_proposal_is_refused(db_session) -> None:
    user_id = _user(db_session)
    service = MemoryService(db_session)

    original = service.create_proposal(user_id, MemoryKey.ACTIVITY_LEVEL, "moderate")
    service.confirm(original.id, user_id)

    stale = service.create_proposal(user_id, MemoryKey.ACTIVITY_LEVEL, "active")
    newer = service.create_proposal(user_id, MemoryKey.ACTIVITY_LEVEL, "sedentary")
    service.confirm(newer.id, user_id)

    with pytest.raises(ConflictError):
        service.confirm(stale.id, user_id)