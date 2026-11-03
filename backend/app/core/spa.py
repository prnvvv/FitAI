"""Serve the built single-page frontend from the API process (one-service deploy).

Registered after every API router, so API, health and docs routes always win; the
catch-all only answers GET/HEAD for paths no other route claimed. Unknown ``/api``
paths still return the API's own JSON 404, never ``index.html``.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response

from app.core.config import settings

_RESERVED_PREFIXES = ("api/", "health", "docs", "redoc", "openapi.json")
_IMMUTABLE = "public, max-age=31536000, immutable"
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Frame-Options": "DENY",
}


def resolve_dist_dir(value: str | None) -> Path | None:
    """Return the frontend build directory if configured and it has an index.html."""
    if not value:
        return None
    path = Path(value).expanduser().resolve()
    return path if (path / "index.html").is_file() else None


def mount_frontend(app: FastAPI, dist_dir: Path) -> None:
    """Add the SPA fallback routes for ``dist_dir`` to ``app``."""
    root = dist_dir.resolve()
    index = root / "index.html"

    def _file(candidate: Path, *, cache: str | None = None) -> FileResponse:
        headers = dict(_SECURITY_HEADERS)
        if cache:
            headers["Cache-Control"] = cache
        return FileResponse(candidate, headers=headers)

    @app.get("/{full_path:path}", include_in_schema=False)
    @app.head("/{full_path:path}", include_in_schema=False)
    def serve_frontend(full_path: str) -> Response:
        if full_path.startswith(_RESERVED_PREFIXES) or full_path == "api":
            raise HTTPException(status_code=404, detail="Not Found")
        if full_path:
            candidate = (root / full_path).resolve()
            # Containment check blocks ``..`` traversal and symlink escapes.
            if candidate.is_file() and candidate.is_relative_to(root):
                hashed = full_path.startswith("assets/")
                return _file(candidate, cache=_IMMUTABLE if hashed else None)
        # Client-side routes (/chat/:id, /plan, ...) fall back to the app shell,
        # which must never be cached so a new deploy is picked up immediately.
        return _file(index, cache="no-cache")


def configure_frontend(app: FastAPI) -> bool:
    """Mount the frontend when ``FRONTEND_DIST_DIR`` points at a build. Returns True if mounted."""
    dist = resolve_dist_dir(settings.frontend_dist_dir)
    if dist is None:
        return False
    mount_frontend(app, dist)
    return True
