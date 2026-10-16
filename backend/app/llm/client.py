"""Groq-backed LLM client implementing the project's TextCompleter protocol.

Also supports a tool-calling loop so live search and places tools can be invoked
by the model when the request requires current information.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from groq import Groq

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)

DEFAULT_MODEL = "openai/gpt-oss-20b"
DEFAULT_TEMPERATURE = 0.0
MAX_TOOL_ITERATIONS = 3

#: Model families that expose a reasoning trace through Groq. They have two
#: API differences that break the default request shape:
#:   * sampling parameters must be 1.0 (any other value is rejected);
#:   * the completion budget covers reasoning tokens too, so a small cap makes
#:     every call fail with "Please reduce the length of the messages or
#:     completion", and an uncapped request is rejected as well.
#: They also reject the ``tools`` parameter entirely.
REASONING_MODEL_PREFIXES = ("openai/gpt-oss",)
#: Completion budget used for reasoning models when the caller sets none.
REASONING_DEFAULT_MAX_COMPLETION_TOKENS = 4096
#: Floor that leaves room for the reasoning trace plus the actual answer.
REASONING_MIN_MAX_COMPLETION_TOKENS = 2048


def _is_reasoning_model(model: str) -> bool:
    """True for model ids whose Groq API behaves differently (see above)."""
    name = (model or "").strip().lower()
    return any(name.startswith(prefix) for prefix in REASONING_MODEL_PREFIXES)


ToolExecutor = Callable[[str, dict[str, Any]], dict[str, Any]]


class GroqClient:
    """Callable LLM wrapper compatible with `app.memory.extractor.TextCompleter`.

    The API key is read from the `GROQ_API_KEY` environment variable. Pass a key
    explicitly only in tests.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        temperature: float = DEFAULT_TEMPERATURE,
        timeout: float = 60.0,
        max_tokens: int | None = None,
    ):
        key = api_key or os.getenv("GROQ_API_KEY")
        if not key:
            raise RuntimeError("GROQ_API_KEY is not set")
        self._client = Groq(api_key=key, timeout=timeout)
        self._model = model
        self._temperature = temperature
        self._timeout = timeout
        self._max_tokens = max_tokens
        self._reasoning = _is_reasoning_model(model)

    @property
    def model(self) -> str:
        """The configured model id."""
        return self._model

    @property
    def supports_tools(self) -> bool:
        """False for reasoning models, whose endpoint rejects ``tools``."""
        return not self._reasoning

    def _request_kwargs(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Build the completion parameters this model actually accepts."""
        kwargs: dict[str, Any] = {"model": self._model, "messages": messages}
        if self._reasoning:
            # gpt-oss on Groq requires default sampling and a budget that covers
            # the reasoning trace; omitting it (or capping it too low) is
            # rejected as "Please reduce the length of the messages or
            # completion". The SDK exposes this as ``max_tokens``.
            kwargs["temperature"] = 1.0
            kwargs["top_p"] = 1.0
            budget = self._max_tokens or REASONING_DEFAULT_MAX_COMPLETION_TOKENS
            kwargs["max_tokens"] = max(budget, REASONING_MIN_MAX_COMPLETION_TOKENS)
        else:
            kwargs["temperature"] = self._temperature
            if self._max_tokens is not None:
                kwargs["max_tokens"] = self._max_tokens
        return kwargs

    def __call__(self, system: str, user: str, *, json_mode: bool = False) -> str:
        """Call the chat completions endpoint and return the message content."""
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user[:4000]},
        ]
        kwargs = self._request_kwargs(messages)
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            response = self._client.chat.completions.create(**kwargs)
        except Exception as exc:
            log.warning("groq completion failed: %s", exc)
            raise
        content = response.choices[0].message.content
        return content or ""

    def run_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        execute: ToolExecutor,
        *,
        max_iterations: int = MAX_TOOL_ITERATIONS,
    ) -> str:
        """Run a chat completion loop that may invoke tools.

        Args:
            messages: OpenAI-style message list (system/user/tool).
            tools: OpenAI-style function definitions.
            execute: Callback that receives (tool_name, arguments) and returns a
                JSON-serialisable result dict.
            max_iterations: Safety cap on tool-turn iterations.

        Returns:
            The final assistant message content, or a safe fallback if the loop
            does not produce a final answer.
        """
        if not self.supports_tools:
            # The model rejects the ``tools`` parameter (e.g. gpt-oss). Answer
            # from the same context in one plain completion instead of failing.
            log.info("model %s does not support tool calling; answering without tools", self._model)
            kwargs = self._request_kwargs(list(messages))
            try:
                response = self._client.chat.completions.create(**kwargs)
            except Exception:
                log.warning("groq tool-less completion failed", exc_info=True)
                raise
            return str(response.choices[0].message.content or "").strip()

        kwargs = self._request_kwargs(list(messages))
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

        for iteration in range(max_iterations):
            try:
                response = self._client.chat.completions.create(**kwargs)
            except Exception:
                log.warning(
                    "groq tool-loop completion failed",
                    exc_info=True,
                    extra={"model": self._model, "iteration": iteration},
                )
                raise

            message = response.choices[0].message
            content = message.content
            tool_calls = message.tool_calls

            if content and not tool_calls:
                return str(content).strip()

            if not tool_calls:
                # Empty final message; return whatever we have.
                return str(content).strip() if content else ""

            # Execute requested tools and append results to the conversation.
            messages.append(
                {
                    "role": "assistant",
                    "content": content or "",
                    "tool_calls": [tc.model_dump() for tc in tool_calls],
                }
            )
            for tc in tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError as exc:
                    log.warning(
                        "malformed tool arguments from model", exc_info=True, extra={"tool": name}
                    )
                    result = {"error": f"Malformed arguments for {name}: {exc}"}
                else:
                    log.info("executing tool", extra={"tool": name, "iteration": iteration})
                    try:
                        result = execute(name, args)
                    except Exception as exc:
                        log.warning("tool execution failed", exc_info=True, extra={"tool": name})
                        result = {"error": f"Tool {name} failed: {type(exc).__name__}"}
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": name,
                        "content": json.dumps(result, default=str),
                    }
                )

        log.warning("tool-loop reached max iterations without final answer")
        return "I couldn't finish answering that. Please try rephrasing your question."
