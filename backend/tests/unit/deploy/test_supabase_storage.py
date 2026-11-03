"""Supabase Storage backend (HTTP mocked, fully offline)."""

from __future__ import annotations

import httpx
import pytest

from app.core.errors import ServiceUnavailableError
from app.services.document_storage import SupabaseDocumentStorage

# ---- Supabase Storage -------------------------------------------------------


def _storage(handler) -> SupabaseDocumentStorage:
    return SupabaseDocumentStorage(
        "https://proj.supabase.co",
        "service-key",
        "fitai-documents",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_save_read_delete_use_the_object_api_with_service_credentials() -> None:
    calls: list[httpx.Request] = []
    blob: dict[str, bytes] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        path = request.url.path
        assert path.startswith("/storage/v1/object/fitai-documents/")
        assert request.headers["authorization"] == "Bearer service-key"
        if request.method == "POST":
            assert request.headers["x-upsert"] == "false"  # never silently overwrite
            blob[path] = request.content
            return httpx.Response(200, json={"Key": path})
        if request.method == "GET":
            return httpx.Response(200, content=blob[path])
        return httpx.Response(200, json={})

    s = _storage(handler)
    s.save("user/doc", b"%PDF-bytes", "application/pdf")
    assert s.read("user/doc") == b"%PDF-bytes"
    s.delete("user/doc")
    assert [c.method for c in calls] == ["POST", "GET", "DELETE"]


def test_new_style_secret_key_is_sent_as_apikey_only() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b"x")

    s = SupabaseDocumentStorage(
        "https://proj.supabase.co",
        "sb_secret_test",
        "fitai-documents",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    s.read("u/d")
    assert seen[0].headers["apikey"] == "sb_secret_test"
    assert "authorization" not in seen[0].headers


def test_delete_of_a_missing_object_is_not_an_error() -> None:
    _storage(lambda r: httpx.Response(404, json={})).delete("u/d")


def test_read_of_a_missing_object_is_a_clear_error() -> None:
    with pytest.raises(ServiceUnavailableError, match="no longer available"):
        _storage(lambda r: httpx.Response(404, json={})).read("u/d")


def test_provider_failures_are_mapped_without_leaking_the_response() -> None:
    s = _storage(lambda r: httpx.Response(500, text="service-key leaked?"))
    with pytest.raises(ServiceUnavailableError) as exc:
        s.save("u/d", b"x", "application/pdf")
    assert "service-key" not in str(exc.value)


def test_network_errors_become_service_unavailable() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(ServiceUnavailableError, match="temporarily unavailable"):
        _storage(boom).read("u/d")


@pytest.mark.parametrize("key", ["", "/abs", "a/../b", "../x"])
def test_path_traversal_keys_are_refused(key) -> None:
    with pytest.raises(ServiceUnavailableError):
        _storage(lambda r: httpx.Response(200)).read(key)


def test_unconfigured_supabase_storage_fails_with_a_configuration_error() -> None:
    s = SupabaseDocumentStorage("", "", "")
    assert s.is_configured is False
    with pytest.raises(ServiceUnavailableError, match="not configured"):
        s.save("u/d", b"x", "application/pdf")
