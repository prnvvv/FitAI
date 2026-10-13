"""Rate limits and per-run budgets for web/location tools."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings

log = logging.getLogger(__name__)


@dataclass
class UserRateLimit:
    """Sliding-window per-user rate limit."""

    window_seconds: int = 60
    max_calls: int = 30

    def __post_init__(self) -> None:
        self._calls: dict[str, list[float]] = {}

    def is_allowed(self, user_id: str) -> bool:
        now = time.monotonic()
        window = self._calls.setdefault(user_id, [])
        cutoff = now - self.window_seconds
        # keep only recent calls
        recent = [t for t in window if t > cutoff]
        self._calls[user_id] = recent
        return len(recent) < self.max_calls

    def record(self, user_id: str) -> None:
        self._calls.setdefault(user_id, []).append(time.monotonic())


@dataclass
class ToolBudget:
    """Per-turn budget for web/location tool calls."""

    max_calls: int = 6
    _calls: list[dict[str, Any]] = field(default_factory=list)

    def can_run(self, tool_name: str) -> bool:
        if len(self._calls) >= self.max_calls:
            log.warning("tool budget exhausted; refusing %s", tool_name)
            return False
        return True

    def spend(self, tool_name: str, args: dict[str, Any]) -> None:
        self._calls.append({"tool": tool_name, "args": args})

    @property
    def used(self) -> int:
        return len(self._calls)


# Singleton per-user rate limiter.
web_rate_limiter = UserRateLimit(max_calls=settings.web_user_rate_limit_per_minute)
