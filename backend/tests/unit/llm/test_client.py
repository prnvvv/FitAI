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


@patch("app.llm.client.Groq")
def test_groq_client_max_tokens_only_when_set(mock_groq_class: MagicMock) -> None:
    mock_client = MagicMock()
    mock_groq_class.return_value = mock_client
    mock_client.chat.completions.create.return_value.choices[0].message.content = "{}"

    # Unset by default: the parameter must not be sent.
    GroqClient(api_key="test-key")("system", "user")
    assert "max_tokens" not in mock_client.chat.completions.create.call_args.kwargs

    # When set (as the guard classifier does), it caps the completion.
    GroqClient(api_key="test-key", max_tokens=200)("system", "user")
    assert mock_client.chat.completions.create.call_args.kwargs["max_tokens"] == 200


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


@patch("app.llm.client.Groq")
def test_run_with_tools_returns_final_answer(mock_groq_class: MagicMock) -> None:
    mock_client = MagicMock()
    mock_groq_class.return_value = mock_client
    message = MagicMock()
    message.content = "final answer"
    message.tool_calls = None
    mock_client.chat.completions.create.return_value.choices[0].message = message

    client = GroqClient(api_key="test-key")
    result = client.run_with_tools(
        [{"role": "user", "content": "hello"}],
        tools=[{"type": "function", "function": {"name": "noop"}}],
        execute=lambda _name, _args: {},
    )

    assert result == "final answer"
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["tools"][0]["function"]["name"] == "noop"
    assert call_kwargs["tool_choice"] == "auto"


@patch("app.llm.client.Groq")
def test_run_with_tools_executes_tool_and_continues(mock_groq_class: MagicMock) -> None:
    mock_client = MagicMock()
    mock_groq_class.return_value = mock_client

    tool_call = MagicMock()
    tool_call.id = "call-1"
    tool_call.function.name = "web_search"
    tool_call.function.arguments = '{"query": "protein"}'

    first_message = MagicMock()
    first_message.content = ""
    first_message.tool_calls = [tool_call]

    final_message = MagicMock()
    final_message.content = "Protein is important."
    final_message.tool_calls = None

    mock_client.chat.completions.create.side_effect = [
        MagicMock(choices=[MagicMock(message=first_message)]),
        MagicMock(choices=[MagicMock(message=final_message)]),
    ]

    calls: list[tuple[str, dict[str, str]]] = []

    def execute(name: str, args: dict[str, str]) -> dict[str, str]:
        calls.append((name, args))
        return {"results": [{"title": "Protein"}]}

    client = GroqClient(api_key="test-key")
    result = client.run_with_tools(
        [{"role": "user", "content": "tell me about protein"}],
        tools=[{"type": "function", "function": {"name": "web_search"}}],
        execute=execute,
    )

    assert result == "Protein is important."
    assert calls == [("web_search", {"query": "protein"})]
    assert mock_client.chat.completions.create.call_count == 2
