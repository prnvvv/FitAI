"""State schema for the multi-agent orchestrator."""

from __future__ import annotations

from typing import Any

from app.agent.state import AgentState


class MultiAgentState(AgentState):
    """Extended state used by the multi-agent graph.

    Added keys have safe defaults so old checkpoints still load.
    """

    route: str  # direct | personal | web | local | mixed
    web_brief: dict[str, Any] | None
    local_brief: dict[str, Any] | None
    personal_context: str
    final_response: str
    final_sources: list[dict[str, Any]]
