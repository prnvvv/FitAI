"""Single-service deployment: the API process serves the built frontend safely."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.spa import resolve_dist_dir


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("<html>shell</html>", encoding="utf-8")
    (root / "assets" / "app-abc123.js").write_text("console.log(1)", encoding="utf-8")
    (root / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("outside", encoding="utf-8")
    return root


@pytest.fixture
def client(dist: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from app.main import create_app

    monkeypatch.setattr(settings, "frontend_dist_dir", str(dist))
    # No ``with``: the lifespan (migration check) is not needed to test routing.
    return TestClient(create_app())


def test_resolve_dist_dir_requires_an_index(tmp_path: Path) -> None:
    assert resolve_dist_dir(None) is None
    assert resolve_dist_dir("") is None
    assert resolve_dist_dir(str(tmp_path)) is None


def test_root_and_client_routes_fall_back_to_the_app_shell(client: TestClient) -> None:
    for path in ("/", "/login", "/chat/123e4567", "/plan"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert "shell" in response.text
        assert response.headers["cache-control"] == "no-cache"
        assert response.headers["x-content-type-options"] == "nosniff"


def test_hashed_assets_are_served_with_immutable_caching(client: TestClient) -> None:
    response = client.get("/assets/app-abc123.js")
    assert response.status_code == 200
    assert "immutable" in response.headers["cache-control"]
    assert client.get("/favicon.svg").status_code == 200


def test_api_health_and_docs_routes_are_not_shadowed(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/docs").status_code == 200


def test_unknown_api_paths_return_not_found_not_the_shell(client: TestClient) -> None:
    for path in ("/api/v1/does-not-exist", "/api", "/health/nope"):
        response = client.get(path)
        assert response.status_code == 404, path
        assert "shell" not in response.text


def test_authenticated_api_routes_still_require_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/conversations").status_code in {401, 403}


@pytest.mark.parametrize(
    "path", ["/../secret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt", "/..%2fsecret.txt"]
)
def test_path_traversal_never_leaks_files_outside_the_build(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert "outside" not in response.text


def test_post_to_unknown_path_is_not_swallowed_by_the_shell(client: TestClient) -> None:
    assert client.post("/login").status_code == 405


def test_without_a_build_core_stays_api_only(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.main import create_app

    monkeypatch.setattr(settings, "frontend_dist_dir", None)
    response = TestClient(create_app()).get("/")
    assert response.status_code == 404
