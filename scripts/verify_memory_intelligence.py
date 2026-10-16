"""Live end-to-end verification of automatic memory intelligence.

Drives the **real** ``ChatService`` in-process against the configured
PostgreSQL database, the dedicated Groq extraction model and the primary Groq
chat model. No HTTP server, no frontend and no auth server is started: the
authenticated user is a real row resolved through the same repositories the API
uses, so identity, ownership and persistence all run for real.

What it proves (each check prints PASS/FAIL and never prints credentials):

1. a fact stated in conversation A is extracted by the **dedicated** client and
   persisted in PostgreSQL under that authenticated user;
2. a semantically equivalent question in a **new** conversation receives the
   persisted fact in the prompt actually sent to the primary model, and the
   answer identifies it;
3. the same holds after the store is rebuilt from scratch, i.e. the fact lives in
   PostgreSQL, not in process memory;
4. duplicate messages do not duplicate records;
5. hypothetical preferences are not stored as facts;
6. a correction supersedes the current fact and preserves history;
7. another user cannot see or recall the fact;
8. per-stage latency (extraction vs total turn) and continuity-index cost.

Usage (from the repository root)::

    python -m scripts.verify_memory_intelligence              # live run
    python -m scripts.verify_memory_intelligence --user-id <uuid>  # reuse a user
    python -m scripts.verify_memory_intelligence --purge      # clean up after

Exit code is 0 only when every check passes.
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.core.config import settings  # noqa: E402
from app.extraction.reconciliation import HISTORY_KEY, INSIGHTS_KEY  # noqa: E402
from app.services import chat_service as chat_service_module  # noqa: E402
from app.services.chat_service import ChatService, _confirmed_insights  # noqa: E402
from app.services.profile_service import ProfileService  # noqa: E402

#: The exact stored wording depends on what the extraction model proposes (and is
#: normalized), so the harness matches on the activity and on the *stored* text.
FACT_SUBJECT = "cycling"
QUESTION = "What do I like to do every day?"

_RESULTS: list[tuple[str, bool, str]] = []


def _record(name: str, passed: bool, detail: str = "") -> None:
    _RESULTS.append((name, passed, detail))
    print(f"[{'PASS' if passed else 'FAIL'}] {name}")
    if detail:
        print(f"       {detail}")


class _ExtractionSpy:
    """Wraps the real dedicated extractor to prove which client ran.

    Records the model id and whether a key was present — never the key itself.
    """

    instances: list[dict[str, Any]] = []
    real_cls: Any = None

    def __init__(self, api_key: str, model: str, **kwargs: Any) -> None:
        self._inner = _ExtractionSpy.real_cls(api_key=api_key, model=model, **kwargs)
        self.calls: list[str] = []
        self._model = model
        _ExtractionSpy.instances.append({"model": model, "key_present": bool(api_key)})

    def extract(self, message: str, now=None) -> Any:
        start = time.perf_counter()
        try:
            result = self._inner.extract(message, now=now)
            if getattr(result, "error", None):
                _Providers.extraction_errors.append(str(result.error))
            elif not getattr(result, "has_any", lambda: False)():
                _Providers.extraction_empty += 1
            return result
        finally:
            _Timings.extraction_ms.append((time.perf_counter() - start) * 1000)
            self.calls.append(message)


class _PrimarySpy:
    """Wraps the real primary chat client to capture the exact prompt sent."""

    prompts: list[str] = []
    model: str | None = None
    key_present: bool | None = None

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        _PrimarySpy.model = getattr(inner, "_model", None)
        _PrimarySpy.key_present = bool(getattr(inner, "_client", None))

    def __call__(self, system: str, user: str, *, json_mode: bool = False) -> str:
        _PrimarySpy.prompts.append(user)
        return self._inner(system, user, json_mode=json_mode)

    def run_with_tools(self, messages: Any, tools: Any, execute: Any, **kw: Any) -> str:
        _PrimarySpy.prompts.append(str(messages[-1].get("content", "")))
        try:
            return self._inner.run_with_tools(messages, tools, execute, **kw)
        except Exception as exc:
            _Providers.primary_errors.append(type(exc).__name__)
            raise


class _Timings:
    extraction_ms: list[float] = []
    index_ms: list[float] = []
    turn_ms: list[float] = []


class _Providers:
    """Provider health, so a quota outage is never mistaken for a code defect."""

    extraction_errors: list[str] = []
    primary_errors: list[str] = []
    extraction_empty: int = 0


class _OutputGuardSpy:
    """Records whether the output guard replaced a model answer.

    A silently replaced answer is the single most common cause of "the model
    ignored the retrieved memory", so the harness must show it.
    """

    events: list[tuple[str, bool]] = []

    def __enter__(self) -> _OutputGuardSpy:
        from app.agent import nodes

        self._real = nodes._output_violates_guard
        spy = self

        def wrapper(text: str, canary: str | None = None) -> bool:
            verdict = spy._real(text, canary)
            spy.events.append((text or "", verdict))
            return verdict

        nodes._output_violates_guard = wrapper
        return self

    def __exit__(self, *exc: object) -> None:
        from app.agent import nodes

        nodes._output_violates_guard = self._real

    def replaced(self) -> list[str]:
        return [text for text, violated in self.events if violated]


def _install_spies() -> None:
    _ExtractionSpy.real_cls = chat_service_module.GroqActivityExtractor

    def factory(api_key: str, model: str, **kwargs: Any) -> Any:
        return _ExtractionSpy(api_key=api_key, model=model, **kwargs)

    chat_service_module.GroqActivityExtractor = factory  # type: ignore[assignment]
    ChatService._build_llm = staticmethod(  # type: ignore[method-assign]
        lambda: _PrimarySpy(
            chat_service_module.GroqClient(api_key=settings.groq_api_key, model=settings.groq_model)
        )
    )

    real_index = ChatService._index_memories

    def timed_index(self: ChatService, user_id: Any, store: Any) -> None:
        start = time.perf_counter()
        try:
            real_index(self, user_id, store)
        finally:
            _Timings.index_ms.append((time.perf_counter() - start) * 1000)

    ChatService._index_memories = timed_index  # type: ignore[method-assign]


def _chat(db: Any, user: Any, message: str, conversation_id: Any = None) -> dict[str, Any]:
    start = time.perf_counter()
    out = ChatService(db).chat(user, message, conversation_id)
    _Timings.turn_ms.append((time.perf_counter() - start) * 1000)
    return out


def _prefs(db: Any, user_id: Any) -> dict[str, Any]:
    profile = ProfileService(db).get(user_id)
    return (profile.preferences or {}) if profile is not None else {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--user-id", default=None, help="Verify an existing user instead of a new one."
    )
    parser.add_argument(
        "--purge", action="store_true", help="Delete the created user's profile first."
    )
    args = parser.parse_args(argv)

    print("=== configuration (no secrets printed) ===")
    print(f"extraction configured : {settings.extraction_enabled}")
    print(f"extraction model      : {settings.extraction_model}")
    print(f"primary model         : {settings.groq_model}")
    print(f"database              : {settings.database_url.split('@')[-1]}")
    print(f"chroma persist dir    : {settings.chromadb_persist_dir}")
    if not settings.extraction_enabled:
        print("\nExtraction is not configured; live verification cannot run.")
        return 2

    from app.db.session import SessionLocal
    from app.repositories.user_repository import UserRepository

    _install_spies()
    guard_spy = _OutputGuardSpy()
    guard_spy.__enter__()

    with SessionLocal() as db:
        users = UserRepository(db)
        if args.user_id:
            user_id = uuid.UUID(args.user_id)
            if users.get(user_id) is None:
                print(f"user {user_id} not found")
                return 2
        else:
            user_id = uuid.uuid4()
            users.get_or_create(user_id, f"memory-verify-{user_id.hex[:8]}@fitai.local")
        if args.purge:
            ProfileService(db).update(user_id, {"preferences": {}}, partial=True)
        user = users.get(user_id)
        assert user is not None
        print(f"\nauthenticated user   : {user_id}")

        # ---- 1. conversation A: extract + persist -----------------------------
        first = _chat(db, user, "I like cycling every day.")
        prefs = _prefs(db, user_id)
        insights = prefs.get(INSIGHTS_KEY) or []
        _record(
            "dedicated extraction client invoked",
            bool(_ExtractionSpy.instances)
            and _ExtractionSpy.instances[-1]["model"] == settings.extraction_model,
            f"model={_ExtractionSpy.instances[-1]['model'] if _ExtractionSpy.instances else None} "
            f"key_present={_ExtractionSpy.instances[-1]['key_present'] if _ExtractionSpy.instances else None}",
        )
        stored_facts = [i["text"] for i in insights]
        fact_text = next((t for t in stored_facts if FACT_SUBJECT in t.lower()), "")
        _record(
            "fact persisted in PostgreSQL for this user",
            bool(fact_text),
            f"conversation A id={first['conversation_id']} stored={stored_facts}",
        )
        _record(
            "stored fact is normalized, not an echoed sentence",
            bool(fact_text) and not fact_text.lower().startswith(("i ", "i'm", "my ")),
            f"stored_fact={fact_text!r}",
        )
        _record(
            "extraction outcome reported as saved (not queued)",
            any(
                e["tool"] == "extract_memory_insight" and e["status"] in {"saved", "updated"}
                for e in first["tool_events"]
            ),
            f"tool_events={[(e['tool'], e['status']) for e in first['tool_events']]}",
        )

        # ---- 2. conversation B: retrieval + answer ---------------------------
        _PrimarySpy.prompts.clear()
        second = _chat(db, user, QUESTION)
        last_prompt = _PrimarySpy.prompts[-1] if _PrimarySpy.prompts else ""
        _record(
            "retrieved fact reached the primary LLM",
            bool(fact_text) and fact_text in last_prompt,
            f"stored fact present in prompt: {bool(fact_text) and fact_text in last_prompt}",
        )
        _record(
            "answer identifies cycling",
            FACT_SUBJECT in second["response"].lower(),
            f"answer={second['response'][:160]!r}",
        )
        _record(
            "different conversation used",
            second["conversation_id"] != first["conversation_id"],
            f"A={first['conversation_id']} B={second['conversation_id']}",
        )

        # ---- 3. duplicate message -------------------------------------------
        _chat(db, user, "I like cycling every day.")
        after_duplicate = _prefs(db, user_id).get(INSIGHTS_KEY) or []
        _record(
            "duplicate message creates no second record",
            len([i for i in after_duplicate if FACT_SUBJECT in i["text"].lower()]) == 1,
            f"records={[i['text'] for i in after_duplicate]}",
        )

        # ---- 4. hypothetical -------------------------------------------------
        _chat(db, user, "I might try swimming someday.")
        hypothetical_saved = any(
            "swim" in i["text"].lower() for i in (_prefs(db, user_id).get(INSIGHTS_KEY) or [])
        )
        _record("hypothetical preference not stored as a fact", not hypothetical_saved)

        # ---- 5. correction ---------------------------------------------------
        _chat(db, user, "I no longer enjoy cycling every day.")
        corrected = _prefs(db, user_id)
        live_texts = _confirmed_insights(corrected)
        superseded = [r for r in corrected.get(HISTORY_KEY, []) if r.get("status") == "superseded"]
        # The affirmative fact must no longer stand as a current fact, and the
        # retraction must be kept as history.
        original = next(
            (t for t in stored_facts if t.lower().startswith(("like ", "likes "))), ""
        )
        _record(
            "correction supersedes the current fact and keeps history",
            bool(superseded)
            and any(r["text"] == original for r in superseded)
            and all(t != original for t in live_texts),
            f"current={live_texts} history={[r['text'] for r in superseded]}",
        )

        # ---- 6. cross-user isolation -----------------------------------------
        other_id = uuid.uuid4()
        users.get_or_create(other_id, f"memory-verify-{other_id.hex[:8]}@fitai.local")
        _PrimarySpy.prompts.clear()
        _chat(db, users.get(other_id), QUESTION)
        other_prefs = _prefs(db, other_id)
        leaked = bool(fact_text) and fact_text in (
            _PrimarySpy.prompts[-1] if _PrimarySpy.prompts else ""
        )
        _record(
            "another user cannot retrieve the fact",
            not leaked and not (other_prefs.get(INSIGHTS_KEY) or []),
            f"other_user_prompt_has_fact={leaked} other_insights={other_prefs.get(INSIGHTS_KEY)}",
        )

        # ---- 7. fresh service instances see the same memory ------------------
        _PrimarySpy.prompts.clear()
        reopened = ChatService(db).chat(user, QUESTION)
        _record(
            "a freshly constructed ChatService still recalls the fact",
            bool(fact_text)
            and fact_text in (_PrimarySpy.prompts[-1] if _PrimarySpy.prompts else ""),
            f"answer={reopened['response'][:120]!r}",
        )

    # ---- 8. after a restart: brand-new session, engines and caches ------------
    with SessionLocal() as db:
        fresh_user = UserRepository(db).get(user_id)
        _PrimarySpy.prompts.clear()
        after_restart = ChatService(db).chat(fresh_user, QUESTION)
        _record(
            "memory survives a restart (new session, new caches)",
            bool(fact_text)
            and fact_text in (_PrimarySpy.prompts[-1] if _PrimarySpy.prompts else "")
            and FACT_SUBJECT in after_restart["response"].lower(),
            f"answer={after_restart['response'][:160]!r}",
        )

    _print_timings()
    print("\n=== provider health ===")
    print(
        f"extraction calls without a usable result : {len(_Providers.extraction_errors) + _Providers.extraction_empty}"
    )
    for err in dict.fromkeys(_Providers.extraction_errors):
        print(f"       extraction error: {err}")
    for err in dict.fromkeys(_Providers.primary_errors):
        print(f"       primary model error: {err}")

    print("\n=== summary ===")
    failed = [name for name, ok, _ in _RESULTS if not ok]
    print(f"{len(_RESULTS) - len(failed)}/{len(_RESULTS)} checks passed")
    for name in failed:
        print(f"  failed: {name}")
    return 1 if failed else 0


def _print_timings() -> None:
    def stats(values: list[float]) -> str:
        if not values:
            return "n/a"
        values = sorted(values)
        return f"n={len(values)} min={values[0]:.0f}ms median={values[len(values) // 2]:.0f}ms max={values[-1]:.0f}ms"

    print("\n=== latency (live) ===")
    print(f"extraction (dedicated LLM + persistence) : {stats(_Timings.extraction_ms)}")
    print(f"continuity index sync per turn           : {stats(_Timings.index_ms)}")
    print(f"total chat turn                          : {stats(_Timings.turn_ms)}")


if __name__ == "__main__":
    raise SystemExit(main())
