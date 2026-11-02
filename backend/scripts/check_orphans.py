"""Read-only report of rows that violate foreign keys (SQLite only).

Usage (from any directory):  python backend/scripts/check_orphans.py

Never modifies the database. If orphans are reported, copy the database file
first (e.g. ``copy data.db data.db.bak``) and review the rows before deciding
whether to remove them manually.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.schema_check import find_foreign_key_violations  # noqa: E402
from app.db.session import engine  # noqa: E402


def main() -> int:
    violations = find_foreign_key_violations(engine)
    if not violations:
        print("No foreign-key violations found.")
        return 0
    counts = Counter((v["table"], v["parent_table"]) for v in violations)
    for (table, parent), n in sorted(counts.items()):
        print(f"{n} row(s) in {table!r} reference a missing row in {parent!r}")
    print("Back up the database file before any manual cleanup. Nothing was changed.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
