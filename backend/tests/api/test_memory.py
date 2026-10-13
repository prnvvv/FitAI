"""API tests for memory endpoints and confirmation workflows."""

from __future__ import annotations

import uuid

from app.core.security import AuthUser
from app.models.enums import MemoryKey
from app.services.memory_service import MemoryService


def _provision(make_client, user: AuthUser):
    client = make_client(user)
    client.get("/api/v1/auth/me")
    return client


def test_memory_list_is_empty_initially(client) -> None:
    response = client.get("/api/v1/memory")
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_correct_missing_memory_returns_404(client) -> None:
    response = client.patch(f"/api/v1/memory/{uuid.uuid4()}", json={"value": 70})
    assert response.status_code == 404


def test_confirm_pending_update_creates_current_memory(make_client, db_session) -> None:
    user = AuthUser(id=uuid.uuid4(), email="memory@example.com")
    client = _provision(make_client, user)

    service = MemoryService(db_session)
    proposal = service.create_proposal(user.id, MemoryKey.WEIGHT, {"value": 72.0, "unit": "kg"})

    confirmed = client.post(f"/api/v1/memory/pending/{proposal.id}/confirm")
    assert confirmed.status_code == 200
    assert confirmed.json()["key"] == "weight"

    current = client.get("/api/v1/memory")
    assert current.json()["total"] == 1


def test_duplicate_confirmation_returns_409(make_client, db_session) -> None:
    user = AuthUser(id=uuid.uuid4())
    client = _provision(make_client, user)
    proposal = MemoryService(db_session).create_proposal(user.id, MemoryKey.GOAL, "build muscle")

    assert client.post(f"/api/v1/memory/pending/{proposal.id}/confirm").status_code == 200
    second = client.post(f"/api/v1/memory/pending/{proposal.id}/confirm")
    assert second.status_code == 409


def test_reject_pending_update_leaves_memory_unchanged(make_client, db_session) -> None:
    user = AuthUser(id=uuid.uuid4())
    client = _provision(make_client, user)
    proposal = MemoryService(db_session).create_proposal(user.id, MemoryKey.GOAL, "cut")

    rejected = client.post(f"/api/v1/memory/pending/{proposal.id}/reject")
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert client.get("/api/v1/memory").json()["total"] == 0


def test_stale_confirmation_returns_409(make_client, db_session) -> None:
    user = AuthUser(id=uuid.uuid4())
    client = _provision(make_client, user)
    service = MemoryService(db_session)

    first = service.create_proposal(user.id, MemoryKey.GOAL, "cut")
    service.confirm(first.id, user.id)

    stale = service.create_proposal(user.id, MemoryKey.GOAL, "bulk")
    # A newer proposal is confirmed first, changing the current value.
    newer = service.create_proposal(user.id, MemoryKey.GOAL, "recomp")
    service.confirm(newer.id, user.id)

    response = client.post(f"/api/v1/memory/pending/{stale.id}/confirm")
    assert response.status_code == 409


def test_memory_ownership_is_enforced(make_client, db_session) -> None:
    owner_user = AuthUser(id=uuid.uuid4())
    other_user = AuthUser(id=uuid.uuid4())
    owner = _provision(make_client, owner_user)
    other = make_client(other_user)

    service = MemoryService(db_session)
    memory = service.create(owner_user.id, MemoryKey.WEIGHT, {"value": 72.0, "unit": "kg"})
    proposal = service.create_proposal(owner_user.id, MemoryKey.GOAL, "build muscle")

    assert other.get("/api/v1/memory").json()["total"] == 0
    assert other.patch(f"/api/v1/memory/{memory.id}", json={"value": 70}).status_code == 404
    assert other.delete(f"/api/v1/memory/{memory.id}").status_code == 404
    assert other.post(f"/api/v1/memory/pending/{proposal.id}/confirm").status_code == 404
    assert other.post(f"/api/v1/memory/pending/{proposal.id}/reject").status_code == 404

    assert owner.get("/api/v1/memory").json()["total"] == 1
