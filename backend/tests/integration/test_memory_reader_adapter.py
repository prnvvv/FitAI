"""Integration tests for the agent's memory reader adapter.

Guards against a regression where the current-memory mapping was keyed by the
raw ``MemoryKey`` enum and rendered as ``MemoryKey.HEIGHT`` in the prompt, and
where canonical units were dropped.
"""

from __future__ import annotations

import uuid

from app.agent.nodes import _format_profile
from app.core.security import AuthUser
from app.models.enums import MemoryKey
from app.services.auth_service import AuthService
from app.services.chat_service import _MemoryReaderAdapter
from app.services.memory_service import MemoryService


def _user(db_session) -> uuid.UUID:
    auth_user = AuthUser(id=uuid.uuid4(), email="reader@example.com")
    return AuthService(db_session).ensure_user(auth_user).id


def test_reader_returns_clean_string_keys_and_units(db_session) -> None:
    user_id = _user(db_session)
    service = MemoryService(db_session)
    service.create(user_id, MemoryKey.HEIGHT, 163.0)
    service.create(user_id, MemoryKey.WEIGHT, 70.0)

    memory = _MemoryReaderAdapter(db_session, user_id).get_current_memory(str(user_id))

    assert set(memory) == {"height", "weight"}
    assert memory["height"].key == "height"
    assert memory["height"].value == 163.0
    assert memory["height"].unit == "cm"
    assert memory["weight"].unit == "kg"


def test_reader_output_is_readable_in_the_prompt(db_session) -> None:
    user_id = _user(db_session)
    service = MemoryService(db_session)
    service.create(user_id, MemoryKey.HEIGHT, 163.0)
    service.create(user_id, MemoryKey.WEIGHT, 70.0)

    memory = _MemoryReaderAdapter(db_session, user_id).get_current_memory(str(user_id))
    rendered = _format_profile(memory, None)

    assert "MemoryKey." not in rendered
    assert "height: 163.0 cm" in rendered
    assert "weight: 70.0 kg" in rendered
