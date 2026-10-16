#!/usr/bin/env python3
"""Set the Groq API key everywhere it is used, without ever printing it.

The key currently appears three times in ``backend/.env``:

* ``GROQ_API_KEY``            - primary chat client
* ``GROQ_EXTRACTION_API_KEY`` - dedicated extraction client
* ``PROMPT_GUARD_API_KEY``    - prompt-injection guard

Rotating by hand means editing three lines, and missing one leaves a revoked key
in use. This script takes the key once (hidden input, or from an environment
variable) and updates all three atomically.

Usage (from the repository root)::

    python -m scripts.set_groq_key              # prompts, input hidden
    GROQ_NEW_KEY=gsk_... python -m scripts.set_groq_key
    python -m scripts.set_groq_key --env-file backend/.env

The key is never echoed, logged or written to the repository. A timestamped
backup of the previous file is placed in the system temp directory, not next to
the ``.env``.
"""

from __future__ import annotations

import argparse
import contextlib
import getpass
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

KEY_VARIABLES = ("GROQ_API_KEY", "GROQ_EXTRACTION_API_KEY", "PROMPT_GUARD_API_KEY")

DEFAULT_ENV_FILE = Path(__file__).resolve().parents[1] / "backend" / ".env"


def looks_like_groq_key(value: str) -> bool:
    """Cheap sanity check so a pasted sentence is rejected before it is written."""
    candidate = value.strip()
    return len(candidate) >= 20 and candidate.startswith(("gsk_", "gsk-"))


def update_env(text: str, key: str, variables: tuple[str, ...] = KEY_VARIABLES) -> str:
    """Return ``text`` with every variable in ``variables`` set to ``key``.

    Existing assignments are replaced in place (comments and ordering survive);
    missing ones are appended under a single comment block.
    """
    lines = text.splitlines()
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        name = line.split("=", 1)[0].strip() if "=" in line else ""
        if not line.lstrip().startswith("#") and name in variables:
            out.append(f"{name}={key}")
            seen.add(name)
        else:
            out.append(line)
    missing = [name for name in variables if name not in seen]
    if missing:
        if out and out[-1].strip():
            out.append("")
        out.append("# Groq key (set by scripts/set_groq_key.py)")
        out.extend(f"{name}={key}" for name in missing)
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE))
    parser.add_argument(
        "--env-var",
        default="GROQ_NEW_KEY",
        help="environment variable to read the key from instead of prompting",
    )
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args(argv)

    env_file = Path(args.env_file)
    if not env_file.exists():
        print(f"No env file at {env_file}", file=sys.stderr)
        return 2

    key = os.getenv(args.env_var, "").strip()
    if not key:
        key = getpass.getpass("New Groq API key (input hidden): ").strip()
    if not looks_like_groq_key(key):
        print("That does not look like a Groq key (expected gsk_... ).", file=sys.stderr)
        return 2

    original = env_file.read_text(encoding="utf-8")
    updated = update_env(original, key)
    env_file.write_text(updated, encoding="utf-8")
    # Narrow the permissions on the file we just rewrote (best effort on Windows).
    with contextlib.suppress(OSError):
        os.chmod(env_file, 0o600)

    if not args.no_backup:
        backup = Path(tempfile.gettempdir()) / f"fitai-env-{int(time.time())}.bak"
        shutil.copy2(env_file, backup)
        print(f"previous file backed up to {backup}")

    print(f"updated {len(KEY_VARIABLES)} variables in {env_file}: " + ", ".join(KEY_VARIABLES))
    print("value not printed; restart the backend for it to take effect")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
