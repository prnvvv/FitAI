"""Live verification for Library, Plan, Progress and cross-user isolation.

Usage: backend/.venv/Scripts/python.exe scripts/audit_live.py <session.json> <second-session.json>
"""

from __future__ import annotations

import io
import json
import pathlib
import sys
import urllib.error
import urllib.request
import uuid
import zipfile

BASE = "http://127.0.0.1:8000"


def _token(session_path: str) -> str:
    return json.loads(pathlib.Path(session_path).read_text(encoding="utf-8"))["token"]


def call(token: str, method: str, path: str, payload: object | None = None) -> tuple[int, dict, dict]:
    headers = {"Authorization": f"Bearer {token}"}
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode()
    req = urllib.request.Request(f"{BASE}{path}", data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw else {}), dict(response.headers)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"raw": raw.decode(errors="replace")[:200]}
        return exc.code, parsed, dict(exc.headers)


def upload(token: str, filename: str, data: bytes, content_type: str) -> tuple[int, dict, dict]:
    boundary = f"----fitai{uuid.uuid4().hex}"
    parts = [
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
        f"Content-Type: {content_type}\r\n\r\n".encode(),
        data,
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    body = b"".join(parts)
    req = urllib.request.Request(
        f"{BASE}/api/v1/documents",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw else {}), dict(response.headers)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"raw": raw.decode(errors="replace")[:200]}
        return exc.code, parsed, dict(exc.headers)


def _header(headers: dict[str, str], name: str) -> str | None:
    """Header lookup is case-insensitive on HTTP."""
    return next((v for k, v in headers.items() if k.lower() == name.lower()), None)


def jpeg_bytes() -> bytes:
    """Smallest valid JPEG-ish payload: SOI + APP0 + EOI."""
    return (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        + b"\xff\xdb\x00C" + bytes(64) + b"\xff\xd9"
    )


def png_bytes() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + bytes(64)


def webp_bytes() -> bytes:
    return b"RIFF" + (32).to_bytes(4, "little") + b"WEBP" + bytes(24)


def docx_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<w:document/>")
    return buffer.getvalue()


def main() -> int:
    token = _token(sys.argv[1])
    other_token = _token(sys.argv[2]) if len(sys.argv) > 2 else None
    failures: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        print(f"{'PASS' if ok else 'FAIL'}  {label}{(' :: ' + detail) if detail else ''}")
        if not ok:
            failures.append(label)

    # --- Library uploads -----------------------------------------------------
    files = [
        ("WhatsApp Image 2026-10-14 at 12.40.14 PM.jpeg", jpeg_bytes(), "image/jpeg"),
        ("diagram.png", png_bytes(), "image/png"),
        ("chart.webp", webp_bytes(), "image/webp"),
        ("upper.JPEG", jpeg_bytes() + b"\x00", "image/jpeg"),
        ("plan.pdf", b"%PDF-1.4\nminimal", "application/pdf"),
        ("notes.docx", docx_bytes(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("readme.md", b"# Notes\nsquat 3x8", "text/markdown"),
    ]
    uploaded: list[dict] = []
    for name, data, mime in files:
        status, body, _ = upload(token, name, data, mime)
        ok = status in (200, 201) and "error" not in body
        detail = f"{status} status={body.get('status')} reason={body.get('failure_reason')}"
        check(f"upload {name}", ok, detail)
        if ok:
            uploaded.append(body)

    # Duplicate detection
    status, body, headers = upload(token, "notes-again.md", b"# Notes\nsquat 3x8", "text/markdown")
    check(
        "duplicate upload returns the existing item",
        status == 200 and _header(headers, "X-Duplicate") == "true",
        f"{status} duplicate={headers.get('X-Duplicate')} id={body.get('id')}",
    )

    # Image failure reason must be specific, never a traceback
    images = [d for d in uploaded if d["content_type"].startswith("image/")]
    for image in images:
        reason = image.get("failure_reason") or ""
        check(
            f"image {image['filename'][:24]} has a readable reason",
            image["status"] == "failed" and bool(reason) and "Traceback" not in reason,
            f"status={image['status']} reason={reason!r}",
        )

    # Retry re-runs ingestion for the same row
    if images:
        target = images[0]
        status, body, _ = call(token, "POST", f"/api/v1/documents/{target['id']}/retry")
        check(
            "retry keeps the same document row",
            status == 200 and body.get("id") == target["id"],
            f"{status} id={body.get('id')}",
        )

    # Rename
    if uploaded:
        status, body, _ = call(
            token, "PATCH", f"/api/v1/documents/{uploaded[-1]['id']}", {"filename": "Squat notes.md"}
        )
        check("rename document", status == 200 and body.get("filename") == "Squat notes.md", f"{status}")

    # Library list exposes failure_reason
    status, body, _ = call(token, "GET", "/api/v1/documents?limit=50&offset=0")
    check(
        "library list exposes failure_reason",
        status == 200 and any("failure_reason" in item for item in body.get("items", [])),
        f"{status} items={len(body.get('items', []))}",
    )

    # Spoofed extension is rejected
    status, body, _ = upload(token, "notreally.jpg", b"MZ\x90\x00binary", "image/jpeg")
    check("spoofed image rejected", body.get("status") == "failed", f"{status} reason={body.get('failure_reason')}")

    # Delete removes row + vectors
    if uploaded:
        victim = uploaded[-1]
        status, _, _ = call(token, "DELETE", f"/api/v1/documents/{victim['id']}")
        status2, _, _ = call(token, "GET", f"/api/v1/documents/{victim['id']}")
        check("delete removes the document", status == 204 and status2 == 404, f"{status}/{status2}")

    # --- Plan ----------------------------------------------------------------
    status, body, _ = call(
        token, "GET", "/api/v1/plan/summary?from=2026-10-12&to=2026-10-18"
    )
    unplanned = [d for d in body if d["day_type"] == "none"] if status == 200 else []
    check("plan summary 200 with unplanned days marked none", status == 200 and bool(unplanned), f"{status}")

    # --- Progress ------------------------------------------------------------
    status, body, _ = call(token, "GET", "/api/v1/progress/bmi")
    check("bmi series readable", status == 200, f"{status} points={len(body) if isinstance(body, list) else '?'}")

    # --- Cross-user isolation ------------------------------------------------
    if other_token:
        status, body, _ = call(other_token, "GET", "/api/v1/documents?limit=50&offset=0")
        check("second user sees none of the first user's files", status == 200 and body.get("total") == 0, f"{status} total={body.get('total')}")
        if uploaded:
            status, _, _ = call(other_token, "GET", f"/api/v1/documents/{uploaded[0]['id']}")
            check("second user gets 404 on the first user's document", status == 404, f"{status}")
        status, body, _ = call(other_token, "GET", "/api/v1/progress/series?type=weight")
        check("second user sees no first-user measurements", status == 200 and body == [], f"{status} {len(body)}")
        status, body, _ = call(other_token, "GET", "/api/v1/activity?limit=100&offset=0")
        check("second user sees no first-user activity", status == 200 and body.get("total") == 0, f"{status} total={body.get('total')}")

    print()
    print(f"{len(failures)} failing check(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
