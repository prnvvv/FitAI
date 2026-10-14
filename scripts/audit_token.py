"""Throwaway authenticated session for the live contract audit.

Creates one temporary Supabase auth user, signs in with the anon key to obtain a
real access token, and prints the token to stdout. Deletion is handled by
`scripts/audit_cleanup.py`.
"""

from __future__ import annotations

import json
import pathlib
import sys
import time
import urllib.error
import urllib.request

PASSWORD = "Audit-Temp-Passw0rd!"


def _env() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in pathlib.Path("backend/.env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def _request(url: str, data: dict[str, object] | None, headers: dict[str, str]) -> tuple[int, dict]:
    body = json.dumps(data).encode() if data is not None else None
    merged = {**headers, "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=body, headers=merged, method="POST" if body else "GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def main() -> int:
    env = _env()
    url = env["SUPABASE_URL"].rstrip("/")
    service = env["SUPABASE_SERVICE_ROLE_KEY"]
    anon = env["SUPABASE_ANON_KEY"]
    admin_headers = {"apikey": service, "Authorization": f"Bearer {service}"}
    user_headers = {"apikey": anon, "Authorization": f"Bearer {anon}"}

    email = f"fitai-audit-{int(time.time())}@example.com"
    status, created = _request(
        f"{url}/auth/v1/admin/users",
        {"email": email, "password": PASSWORD, "email_confirm": True},
        admin_headers,
    )
    if status not in (200, 201):
        print(json.dumps({"step": "create", "status": status, "body": created}), file=sys.stderr)
        return 1
    user_id = created["id"]

    status, session = _request(
        f"{url}/auth/v1/token?grant_type=password",
        {"email": email, "password": PASSWORD},
        user_headers,
    )
    if status != 200:
        print(json.dumps({"step": "signin", "status": status, "body": session}), file=sys.stderr)
        return 1

    print(json.dumps({"user_id": user_id, "email": email, "token": session["access_token"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
