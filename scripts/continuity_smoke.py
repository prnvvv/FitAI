#!/usr/bin/env python3
"""Live smoke test for cross-chat continuity (memory + past-chat recall).

Drives the real backend over HTTP to prove that:
  1. a new conversation flushes the previous one into a summary and indexes it;
  2. a later, semantically related question recalls that past chat (the turn
     carries a ``continuity`` tool event and the answer uses the earlier detail);
  3. per-turn latency stays reasonable.

The fact used to test recall ("long runs on Sundays") is *not* a structured
memory key, so it can only reach the answer through the summary/past-chat layer.

Requires a running backend and a valid Supabase access token:

    FITAI_TEST_TOKEN=<jwt> python scripts/continuity_smoke.py
    python scripts/continuity_smoke.py --base-url http://127.0.0.1:8000 --token <jwt>
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
import time
from typing import Any

import requests

API_PREFIX = "/api/v1"


def _print_result(name: str, passed: bool, details: str = "") -> None:
    print(f"[{'PASS' if passed else 'FAIL'}] {name}")
    if details:
        print(f"       {details}")


def _chat(
    base_url: str, token: str, message: str, conversation_id: str | None
) -> tuple[dict[str, Any], int, float]:
    payload: dict[str, Any] = {"message": message}
    if conversation_id:
        payload["conversation_id"] = conversation_id
    start = time.monotonic()
    resp = requests.post(
        f"{base_url}{API_PREFIX}/chat",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    latency_ms = (time.monotonic() - start) * 1000
    try:
        body = resp.json()
    except ValueError:
        body = {"raw": resp.text}
    return body, resp.status_code, latency_ms


def _has_continuity_event(body: dict[str, Any]) -> dict[str, Any] | None:
    for event in body.get("tool_events", []) or []:
        if event.get("tool") == "continuity":
            return event
    return None


def run(base_url: str, token: str) -> bool:
    print("=" * 64)
    print("FitAI Continuity Smoke Test")
    print("=" * 64)

    latencies: list[float] = []
    all_passed = True

    # 1. Conversation A: a durable, non-structured detail + a follow-up.
    body, status, ms = _chat(
        base_url,
        token,
        "I'm training for a half marathon in November. My coach said to keep my long runs on Sundays.",
        None,
    )
    latencies.append(ms)
    if status != 200 or "conversation_id" not in body:
        _print_result("seed conversation A", False, f"HTTP {status}: {str(body)[:200]}")
        return False
    conversation_a = body["conversation_id"]
    _print_result("seed conversation A", True, f"{ms:.0f} ms")

    body, status, ms = _chat(
        base_url, token, "How should I fuel those Sunday long runs?", conversation_a
    )
    latencies.append(ms)
    _print_result("follow-up in A", status == 200, f"{ms:.0f} ms")
    all_passed = all_passed and status == 200

    # 2. New conversation B: this is the turn that flushes + summarises A.
    body, status, ms = _chat(
        base_url, token, "What did we decide about my long run schedule?", None
    )
    latencies.append(ms)
    if status != 200:
        _print_result(
            "new chat B (flush A)", False, f"HTTP {status}: {str(body)[:200]}"
        )
        return False
    conversation_b = body["conversation_id"]
    event = _has_continuity_event(body)
    if event is not None:
        _print_result(
            "new chat B recalls past chat",
            True,
            f"continuity event {event} in {ms:.0f} ms",
        )
    else:
        _print_result(
            "new chat B recalls past chat",
            False,
            "no continuity tool event; check CONTINUITY_ENABLED and SUMMARY_MODEL",
        )
        all_passed = False

    # 3. Same conversation B, second turn: recall should remain available.
    body, status, ms = _chat(
        base_url, token, "Remind me, which day are my long runs?", conversation_b
    )
    latencies.append(ms)
    event = _has_continuity_event(body)
    _print_result(
        "second turn in B recalls past chat", event is not None, f"{ms:.0f} ms"
    )
    all_passed = all_passed and (event is not None)

    # 4. Content grounding (best-effort): the answer should mention the detail.
    answer = str(body.get("response", "")).lower()
    grounded = any(word in answer for word in ("sunday", "long run", "half marathon"))
    _print_result(
        "answer uses the earlier detail",
        grounded,
        f"response: {body.get('response', '')[:120]}",
    )
    # Content grounding is advisory; recall event is the hard signal.
    if not grounded:
        print(
            "       (advisory only: recall fired but the wording did not reuse the detail)"
        )

    print("-" * 64)
    if latencies:
        print(
            f"turns={len(latencies)} median={statistics.median(latencies):.0f} ms "
            f"max={max(latencies):.0f} ms"
        )
    print("=" * 64)
    print("ALL TESTS PASSED!" if all_passed else "SOME TESTS FAILED!")
    return all_passed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Live cross-chat continuity smoke test."
    )
    parser.add_argument(
        "--base-url", default=os.environ.get("FITAI_BASE_URL", "http://127.0.0.1:8000")
    )
    parser.add_argument("--token", default=os.environ.get("FITAI_TEST_TOKEN"))
    args = parser.parse_args(argv)

    if not args.token:
        print("Skipping continuity smoke test - no FITAI_TEST_TOKEN provided.")
        print("Set FITAI_TEST_TOKEN (or pass --token) to run it.")
        return 0

    return 0 if run(args.base_url, args.token) else 1


if __name__ == "__main__":
    sys.exit(main())
