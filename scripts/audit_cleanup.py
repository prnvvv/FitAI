"""Delete the throwaway audit users created by scripts/audit_token.py.

Usage: backend/.venv/Scripts/python.exe scripts/audit_cleanup.py <session.json> [...]
"""

from __future__ import annotations

import json
import pathlib
import sys
import urllib.error
import urllib.request


def _env() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in pathlib.Path("backend/.env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: audit_cleanup.py <session.json> [...]", file=sys.stderr)
        return 1
    env = _env()
    url = env["SUPABASE_URL"].rstrip("/")
    service = env["SUPABASE_SERVICE_ROLE_KEY"]

    for session_path in sys.argv[1:]:
        session = json.loads(pathlib.Path(session_path).read_text(encoding="utf-8"))
        user_id = session["user_id"]
        req = urllib.request.Request(
            f"{url}/auth/v1/admin/users/{user_id}",
            headers={"apikey": service, "Authorization": f"Bearer {service}"},
            method="DELETE",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                print(f"deleted {session['email']} -> {response.status}")
        except urllib.error.HTTPError as exc:
            print(f"failed to delete {session['email']}: {exc.code} {exc.read().decode()[:200]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
