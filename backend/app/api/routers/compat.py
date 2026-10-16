"""Compatibility stub for OpenAI-style client discovery.

Editor plugins, browser extensions and AI CLIs probe ``GET /v1/models`` on
whatever base URL they are configured with. When that base URL happens to be a
FitAI backend, the probe produced a 404 in the server log even though nothing
was wrong - which looks like a broken server during startup.

This route answers that probe honestly and without weakening security:

* the response is a valid, empty OpenAI catalogue, so a client that expects the
  shape gets one and stops retrying;
* it exposes **no** model ids, keys or configuration. FitAI does not serve the
  OpenAI API, so there is nothing to advertise;
* it requires no authentication and touches no user data, exactly like
  ``/health``.

``/v1/chat/completions`` is deliberately *not* implemented: pretending to be a
chat backend would fail later, in a more confusing way, than a clear 404.
"""

from __future__ import annotations

from fastapi import APIRouter, Response

router = APIRouter(tags=["compat"])


@router.get("/v1/models")
def list_models(response: Response) -> dict[str, object]:
    """Return an empty OpenAI-compatible model list.

    FitAI's API lives under ``/api/v1`` and is authenticated; this endpoint
    exists only so discovery probes stop erroring.
    """
    response.headers["X-FitAI-Api"] = "/api/v1 (authenticated); /v1 is not an OpenAI-compatible API"
    return {"object": "list", "data": []}


__all__ = ["router"]
