"""OpenAI-style discovery probes must not look like a broken server.

A valid, empty catalogue is returned for ``GET /v1/models`` and nothing about the
deployment (model ids, keys, configuration) is disclosed.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_models_probe_returns_an_empty_catalogue(anon_client: TestClient) -> None:
    resp = anon_client.get("/v1/models")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == {"object": "list", "data": []}


def test_models_probe_needs_no_authentication(anon_client: TestClient) -> None:
    """Public, like /health: a client with no token must not get a 401."""
    assert anon_client.get("/v1/models").status_code == 200


def test_models_probe_discloses_no_configuration(anon_client: TestClient) -> None:
    from app.core.config import settings

    text = anon_client.get("/v1/models").text
    for secret in (
        settings.groq_model,
        settings.extraction_model,
        settings.prompt_guard_model,
        settings.groq_api_key or "unset",
        settings.extraction_api_key or "unset",
    ):
        assert secret not in text


def test_models_probe_points_at_the_real_api(anon_client: TestClient) -> None:
    header = anon_client.get("/v1/models").headers.get("X-FitAI-Api")
    assert header is not None
    assert "/api/v1" in header


def test_chat_completions_is_not_faked(anon_client: TestClient) -> None:
    """We do not pretend to be an OpenAI chat backend."""
    resp = anon_client.post(
        "/v1/chat/completions",
        json={"model": "anything", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 404


def test_real_api_still_requires_authentication(anon_client: TestClient) -> None:
    """The probe must not weaken the authenticated surface."""
    assert anon_client.get("/api/v1/memory").status_code in (401, 403)
