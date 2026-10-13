"""Groq-backed LLM client implementing the project's TextCompleter protocol."""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

from groq import Groq

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)

DEFAULT_MODEL = "llama-3.1-70b-versatile"
DEFAULT_TEMPERATURE = 0.0


class GroqClient:
    """Callable LLM wrapper compatible with `app.memory.extractor.TextCompleter`.

    The API key is read from the `GROQ_API_KEY` environment variable. Pass a key
    explicitly only in tests.
    """

    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL,
                 temperature: float = DEFAULT_TEMPERATURE, timeout: float = 60.0):
        key = api_key or os.getenv("GROQ_API_KEY")
        if not key:
            raise RuntimeError("GROQ_API_KEY is not set")
        self._client = Groq(api_key=key, timeout=timeout)
        self._model = model
        self._temperature = temperature

    def __call__(self, system: str, user: str, *, json_mode: bool = False) -> str:
        """Call the chat completions endpoint and return the message content."""
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user[:4000]},
        ]
        kwargs: dict[str, Any] = {
            "model": self._model,
            "temperature": self._temperature,
            "messages": messages,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            response = self._client.chat.completions.create(**kwargs)
        except Exception as exc:
            log.warning("groq completion failed: %s", exc)
            raise
        content = response.choices[0].message.content
        return content or ""


