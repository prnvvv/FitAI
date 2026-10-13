"""Tests for the Groq LLM client wrapper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.llm.client import DEFAULT_MODEL, DEFAULT_TEMPERATURE, GroqClient


@patch("app.llm.client.Groq")
def test_groq_client_calls_api(mock_groq_class: MagicMock) -> None:
    mock_client = MagicMock()
    mock_groq_class.return_value = mock_client
    mock_client.chat.completions.create.return_value.choices[0].message.content = "hello"

    client = GroqClient(api_key="test-key")
    result = client("system prompt", "user prompt")

    assert result == "hello"
    mock_groq_class.assert_called_once_with(api_key="test-key", timeout=60.0)
    mock_client.chat.completions.create.assert_called_once()
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == DEFAULT_MODEL
    assert call_kwargs["temperature"] == DEFAULT_TEMPERATURE
    messages = call_kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "system prompt"
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "user prompt"


@patch("app.llm.client.Groq")
def test_groq_client_json_mode(mock_groq_class: MagicMock) -> None:
    mock_client = MagicMock()
    mock_groq_class.return_value = mock_client
    mock_client.chat.completions.create.return_value.choices[0].message.content = '{"facts":[]}'

    client = GroqClient(api_key="test-key")
    client("system", "user", json_mode=True)

    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["response_format"] == {"type": "json_object"}


@patch("app.llm.client.os.getenv")
def test_groq_client_reads_env(mock_getenv: MagicMock) -> None:
    mock_getenv.return_value = "env-key"
    with patch("app.llm.client.Groq") as mock_groq_class:
        mock_groq_class.return_value = MagicMock()
        GroqClient()
        mock_groq_class.assert_called_once_with(api_key="env-key", timeout=60.0)


def test_groq_client_raises_when_key_missing() -> None:
    with (
        patch("app.llm.client.os.getenv", return_value=None),
        pytest.raises(RuntimeError, match="GROQ_API_KEY is not set"),
    ):
        GroqClient()
