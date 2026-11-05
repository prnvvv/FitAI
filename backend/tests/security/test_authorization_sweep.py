"""Every protected route rejects anonymous callers; indirect ownership holds."""

from __future__ import annotations

import uuid

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.core.security import AuthUser
from app.main import app

#: Routes that are intentionally public (no user data).
PUBLIC = {
    ("GET", "/api/v1/plan/templates"),
}

_ID_PARAMS = (
    "conversation_id",
    "document_id",
    "session_id",
    "memory_id",
    "update_id",
    "exercise_id",
    "measurement_id",
)


def _protected_routes() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith("/api/v1/"):
            continue
        for method in route.methods - {"HEAD", "OPTIONS"}:
            if (method, route.path) not in PUBLIC:
                found.append((method, route.path))
    return sorted(found)


@pytest.mark.parametrize(("method", "path"), _protected_routes())
def test_route_requires_authentication(anon_client, method: str, path: str) -> None:
    concrete = path
    for name in _ID_PARAMS:
        concrete = concrete.replace("{" + name + "}", str(uuid.uuid4()))
    response = anon_client.request(method, concrete, json={})
    assert response.status_code == 401, f"{method} {path} -> {response.status_code}"
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_public_allowlist_has_no_stale_entries() -> None:
    declared = {(m, r.path) for r in app.routes if isinstance(r, APIRoute) for m in r.methods}
    assert declared >= PUBLIC


def test_malformed_and_non_bearer_credentials_are_rejected(anon_client) -> None:
    for header in ("Basic abc", "Bearer", "Bearer not.a.jwt", "bearer "):
        r = anon_client.get("/api/v1/profile", headers={"Authorization": header})
        assert r.status_code == 401


def test_messages_of_another_users_conversation_are_hidden(make_client) -> None:
    owner = make_client(AuthUser(id=uuid.uuid4()))
    other = make_client(AuthUser(id=uuid.uuid4()))
    cid = owner.post("/api/v1/conversations", json={"title": "x"}).json()["id"]
    assert other.get(f"/api/v1/conversations/{cid}/messages").status_code == 404
    assert other.patch(f"/api/v1/conversations/{cid}", json={"title": "pwn"}).status_code == 404
    assert owner.get(f"/api/v1/conversations/{cid}").json()["title"] == "x"


def test_custom_exercises_are_private_to_their_creator(make_client) -> None:
    owner = make_client(AuthUser(id=uuid.uuid4()))
    other = make_client(AuthUser(id=uuid.uuid4()))
    made = owner.post("/api/v1/exercises", json={"name": "Secret Lift Z"})
    assert made.status_code == 201, made.text
    eid = made.json()["id"]
    assert other.get(f"/api/v1/exercises/{eid}").status_code == 404
    names = [e["name"] for e in other.get("/api/v1/exercises?limit=100").json()["items"]]
    assert "Secret Lift Z" not in names


def test_client_cannot_set_ownership_fields_via_payload(make_client) -> None:
    victim_id = uuid.uuid4()
    attacker = make_client(AuthUser(id=uuid.uuid4()))
    r = attacker.post("/api/v1/conversations", json={"title": "t", "user_id": str(victim_id)})
    assert r.status_code in (201, 422)
    if r.status_code == 201:
        assert r.json().get("user_id") != str(victim_id)
        assert attacker.get(f"/api/v1/conversations/{r.json()['id']}").status_code == 200


def test_pagination_limit_is_capped(client) -> None:
    assert client.get("/api/v1/conversations?limit=100000").status_code == 422
    assert client.get("/api/v1/conversations?limit=100").status_code == 200


def test_unexpected_errors_do_not_leak_internals(client, monkeypatch) -> None:
    from app.services import conversation_service

    def boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("SELECT secret FROM users; password=hunter2")

    monkeypatch.setattr(conversation_service.ConversationService, "list_conversations", boom)
    safe = TestClient(app, headers=dict(client.headers), raise_server_exceptions=False)
    r = safe.get("/api/v1/conversations")
    assert r.status_code == 500
    assert "hunter2" not in r.text and "SELECT" not in r.text and "Traceback" not in r.text
    assert r.json()["error"]["code"] == "INTERNAL_ERROR"
