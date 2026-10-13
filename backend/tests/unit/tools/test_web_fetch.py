"""Tests for the web page fetch helper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.tools.web.fetch import fetch_url


def test_fetch_url_extracts_title_and_text() -> None:
    html = """
    <html>
      <head><title>Protein Guide</title></head>
      <body>
        <nav>ignore me</nav>
        <p>Protein is essential for muscle repair.</p>
        <script>var x = 1;</script>
      </body>
    </html>
    """
    with patch("app.tools.web.fetch.httpx.Client") as mock_client:
        instance = MagicMock()
        instance.get.return_value.headers = {"content-type": "text/html"}
        instance.get.return_value.raise_for_status = MagicMock()
        instance.get.return_value.text = html
        instance.get.return_value.url = "https://example.com/protein"
        instance.__enter__ = MagicMock(return_value=instance)
        instance.__exit__ = MagicMock(return_value=False)
        mock_client.return_value = instance

        result = fetch_url("https://example.com/protein")

    assert result["url"] == "https://example.com/protein"
    assert result["title"] == "Protein Guide"
    assert "essential for muscle repair" in result["text"]
    assert "ignore me" not in result["text"]
    assert "var x" not in result["text"]


def test_fetch_url_handles_non_html() -> None:
    with patch("app.tools.web.fetch.httpx.Client") as mock_client:
        instance = MagicMock()
        instance.get.return_value.headers = {"content-type": "application/pdf"}
        instance.get.return_value.raise_for_status = MagicMock()
        instance.__enter__ = MagicMock(return_value=instance)
        instance.__exit__ = MagicMock(return_value=False)
        mock_client.return_value = instance

        result = fetch_url("https://example.com/file.pdf")

    assert "error" in result
    assert "Non-HTML" in result["error"]


def test_fetch_url_handles_request_error() -> None:
    with patch("app.tools.web.fetch.httpx.Client") as mock_client:
        instance = MagicMock()
        instance.get.side_effect = RuntimeError("connection failed")
        instance.__enter__ = MagicMock(return_value=instance)
        instance.__exit__ = MagicMock(return_value=False)
        mock_client.return_value = instance

        result = fetch_url("https://example.com/broken")

    assert "error" in result
    assert "connection failed" in result["error"]


def test_fetch_url_blocks_private_ip() -> None:
    result = fetch_url("http://192.168.1.1/admin")
    assert "error" in result
    assert "Private" in result["error"]


def test_fetch_url_blocks_non_http_scheme() -> None:
    result = fetch_url("file:///etc/passwd")
    assert "error" in result
    assert "Only http/https" in result["error"]
