"""The extraction LLM must be isolated from the primary chat LLM.

Covers: independent keys/models, no silent fallback to the primary key, and
safe skipping when extraction credentials are missing.
"""

from __future__ import annotations

from app.core.config import Settings, settings
from app.extraction.extractor import GroqActivityExtractor
from app.services import chat_service as chat_service_module


class _RecordingGroqClient:
    """Records how GroqClient was constructed (never calls the network)."""

    instances: list[tuple[str | None, str]] = []

    def __init__(self, api_key: str | None = None, model: str = "x", **kwargs) -> None:
        _RecordingGroqClient.instances.append((api_key, model))


def test_extraction_settings_use_dedicated_variables() -> None:
    configured = Settings(
        groq_api_key="primary-key",
        groq_model="primary-model",
        extraction_api_key="extraction-key",
        extraction_model="extraction-model",
    )
    assert configured.groq_api_key == "primary-key"
    assert configured.groq_model == "primary-model"
    assert configured.extraction_api_key == "extraction-key"
    assert configured.extraction_model == "extraction-model"
    assert configured.extraction_enabled is True


def test_missing_extraction_key_never_falls_back_to_primary(monkeypatch) -> None:
    monkeypatch.setattr(settings, "groq_api_key", "primary-key")
    monkeypatch.setattr(settings, "extraction_api_key", None)
    monkeypatch.setattr(settings, "agent_activity_extraction", True)
    # No dedicated key => extraction is disabled, even though chat has a key.
    assert settings.extraction_enabled is False

    _RecordingGroqClient.instances.clear()
    monkeypatch.setattr(chat_service_module, "GroqActivityExtractor", _RecordingGroqClient)
    service = chat_service_module.ChatService.__new__(chat_service_module.ChatService)
    assert service._build_extractor() is None
    assert _RecordingGroqClient.instances == []


def test_flag_off_disables_extraction(monkeypatch) -> None:
    monkeypatch.setattr(settings, "extraction_api_key", "extraction-key")
    monkeypatch.setattr(settings, "agent_activity_extraction", False)
    assert settings.extraction_enabled is False


def test_extractor_uses_its_own_key_and_model(monkeypatch) -> None:
    monkeypatch.setattr("app.llm.client.Groq", _RecordingGroqClient)
    _RecordingGroqClient.instances.clear()
    extractor = GroqActivityExtractor(api_key="extraction-key", model="extraction-model")
    assert _RecordingGroqClient.instances == [("extraction-key", "x")]
    # The model is carried by the client, verified without any network call.
    assert extractor._llm._model == "extraction-model"


def test_primary_llm_uses_the_primary_key_and_model(monkeypatch) -> None:
    monkeypatch.setattr(settings, "groq_api_key", "primary-key")
    monkeypatch.setattr(settings, "groq_model", "primary-model")
    _RecordingGroqClient.instances.clear()
    monkeypatch.setattr("app.llm.client.Groq", _RecordingGroqClient)
    llm = chat_service_module.ChatService._build_llm()
    assert _RecordingGroqClient.instances == [("primary-key", "x")]
    assert llm._model == "primary-model"
