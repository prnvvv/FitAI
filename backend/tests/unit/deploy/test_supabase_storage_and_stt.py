"""Supabase Storage backend and the remote STT provider (HTTP mocked, fully offline)."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.errors import ServiceUnavailableError
from app.services.document_storage import SupabaseDocumentStorage
from app.stt.remote_service import (
    RemoteTranscriber,
    UnsupportedAudioFormatError,
    set_remote_transcriber,
    sniff_audio_format,
)
from app.stt.speech_service import ModelLoadError, TranscriptionError

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


# ---- remote STT -------------------------------------------------------------

WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 64


@pytest.mark.parametrize(
    ("data", "kind"),
    [
        (b"RIFF\x00\x00\x00\x00WAVE", "wav"),
        (WEBM, "webm"),
        (b"OggS\x00\x02", "ogg"),
        (b"\x00\x00\x00\x18ftypmp42", "mp4"),
        (b"ID3\x03\x00", "mp3"),
        (b"\xff\xfb\x90\x00", "mp3"),
    ],
)
def test_audio_container_sniffing(data, kind) -> None:
    assert sniff_audio_format(data) == kind


def test_non_audio_is_rejected() -> None:
    with pytest.raises(UnsupportedAudioFormatError):
        sniff_audio_format(b"MZ\x90\x00 an executable")


def _transcriber(handler) -> RemoteTranscriber:
    return RemoteTranscriber(
        "https://stt.test/v1/audio/transcriptions",
        "stt-key",
        "whisper-x",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_remote_transcription_posts_multipart_and_returns_text() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["ctype"] = request.headers["content-type"]
        seen["body"] = request.content
        return httpx.Response(200, json={"text": " hello world "})

    result = _transcriber(handler).transcribe(WEBM, "clip.webm", "audio/webm")
    assert result.text == "hello world" and result.device == "remote"
    assert seen["auth"] == "Bearer stt-key" and "multipart/form-data" in seen["ctype"]
    assert b"whisper-x" in seen["body"]


def test_unconfigured_remote_stt_fails_gracefully() -> None:
    with pytest.raises(ModelLoadError, match="STT_REMOTE_URL"):
        RemoteTranscriber("", "", "").transcribe(WEBM, "c.webm", "audio/webm")


def test_provider_error_does_not_leak_the_key() -> None:
    t = _transcriber(lambda r: httpx.Response(401, text="invalid key stt-key"))
    with pytest.raises(TranscriptionError) as exc:
        t.transcribe(WEBM, "c.webm", "audio/webm")
    assert "stt-key" not in str(exc.value)


@pytest.fixture
def remote_client(monkeypatch, client):
    from app.core.config import settings

    monkeypatch.setattr(settings, "stt_provider", "remote")
    monkeypatch.setattr(settings, "stt_max_upload_mb", 1)
    yield client
    set_remote_transcriber(None)


def test_endpoint_remote_flow_never_loads_a_local_model(remote_client, monkeypatch) -> None:
    import sys

    set_remote_transcriber(
        _transcriber(lambda r: httpx.Response(200, json={"text": "squats today"}))
    )
    r = remote_client.post("/api/v1/stt/transcribe", files={"file": ("a.webm", WEBM, "audio/webm")})
    assert r.status_code == 200
    assert r.json()["text"] == "squats today" and r.json()["device"] == "remote"
    assert "torch" not in sys.modules and "transformers" not in sys.modules
    status = remote_client.get("/api/v1/stt/status").json()
    assert status["provider"] == "remote" and status["state"] == "ready"


def test_endpoint_rejects_oversize_non_audio_and_empty(remote_client) -> None:
    post = lambda data: remote_client.post(  # noqa: E731
        "/api/v1/stt/transcribe", files={"file": ("a.webm", data, "audio/webm")}
    )
    assert post(WEBM + b"\x00" * (1024 * 1024)).status_code == 413
    assert post(b"MZ not audio").status_code == 415
    assert post(b"").status_code in (400, 422)


def test_endpoint_reports_missing_provider_configuration_as_503(remote_client) -> None:
    set_remote_transcriber(RemoteTranscriber("", "", ""))
    r = remote_client.post("/api/v1/stt/transcribe", files={"file": ("a.webm", WEBM, "audio/webm")})
    assert r.status_code == 503
    assert "STT_REMOTE_URL" in r.json()["error"]["message"]


def test_endpoint_provider_failure_is_a_clean_error(remote_client) -> None:
    set_remote_transcriber(_transcriber(lambda r: httpx.Response(500)))
    r = remote_client.post("/api/v1/stt/transcribe", files={"file": ("a.webm", WEBM, "audio/webm")})
    assert r.status_code >= 500 and "stt-key" not in r.text


def test_transcribe_requires_authentication() -> None:
    from app.main import app

    assert TestClient(app).post("/api/v1/stt/transcribe").status_code == 401
