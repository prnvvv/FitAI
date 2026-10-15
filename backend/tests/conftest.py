"""Shared pytest fixtures.

Person 1 (core backend): an isolated in-memory SQLite database, an
authentication token registry so no live Supabase credentials are required, and
client fixtures for API tests. ``anon_client`` exercises the real verification
dependency.

Person 2 (AI engine): fakes for the LLM completer, memory reader/writer,
workout/progress services, and RAG retriever used by unit tests.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator, Mapping, Sequence
from datetime import date, datetime, timezone
from typing import Any

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (register all models)
from app.agent.nodes import MemoryReader, Retriever
from app.api.deps import get_current_auth_user
from app.core.errors import AuthenticationError
from app.core.security import AuthUser
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.memory.change_detector import DetectedChange, MemoryEntry
from app.memory.confirmation import Decision, MemoryWriter
from app.memory.extractor import TextCompleter
from app.tools.progress_tools import DatedValue, GoalEntry, ProgressService
from app.tools.workout_tools import WorkoutLog, WorkoutService

# ---------------------------------------------------------------------------
# Person 2 fakes: LLM, memory, workout, progress, retriever
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _off_network_guard_classifier(monkeypatch) -> None:
    """Keep tests off the network: the LLM guard classifier is off by default.

    The default classifier builds a real Groq client, which would make a live
    call in any test that reaches the chat path. Disabling it here guarantees
    the whole suite stays deterministic and offline; individual tests opt in by
    flipping the flag back on and injecting a fake classifier.

    Cross-chat continuity is disabled here too so the chat path never opens
    Chroma or calls the summary model. Tests that exercise continuity enable it
    explicitly and inject fakes.
    """
    from app.core.config import settings
    from app.guardrails.guard import clear_decision_cache

    clear_decision_cache()
    monkeypatch.setattr(settings, "guard_classifier_enabled", False)
    monkeypatch.setattr(settings, "continuity_enabled", False)
    yield
    clear_decision_cache()


class _FakeLLM:
    """Stub LLM completer that returns a fixed JSON object."""

    def __init__(self, response: str = '{"facts":[]}') -> None:
        self.response = response
        self.calls: list[tuple[str, str, bool]] = []

    def __call__(self, system: str, user: str, *, json_mode: bool = False) -> str:
        self.calls.append((system, user, json_mode))
        return self.response


class _FakeMemoryReader:
    """Stub that returns a configurable current-memory mapping."""

    def __init__(self, memory: Mapping[str, MemoryEntry] | None = None) -> None:
        self.memory = dict(memory or {})

    def get_current_memory(self, user_id: str) -> Mapping[str, MemoryEntry]:
        return self.memory


class _FakeMemoryWriter:
    """Stub memory writer that records calls and reports success."""

    def __init__(self, succeed: bool = True) -> None:
        self.succeed = succeed
        self.updates: list[tuple[str, DetectedChange]] = []
        self.pending: list[tuple[str, Decision]] = []
        self.history: list[tuple[str, Any]] = []

    def apply_update(self, user_id: str, change: DetectedChange) -> bool:
        self.updates.append((user_id, change))
        return self.succeed

    def create_pending(self, user_id: str, decision: Decision) -> str | None:
        self.pending.append((user_id, decision))
        return "pending-1" if self.succeed else None

    def record_history(self, user_id: str, record: Any) -> bool:
        self.history.append((user_id, record))
        return self.succeed


class _FakeWorkoutService:
    """Stub workout service with no persisted data."""

    def __init__(self, workouts: Sequence[WorkoutLog] | None = None) -> None:
        self.workouts = list(workouts or [])
        self.logged: list[tuple[str, WorkoutLog]] = []

    def log_workout(self, user_id: str, workout: WorkoutLog) -> str | None:
        self.logged.append((user_id, workout))
        return "workout-1"

    def get_workouts(self, user_id: str, start: date, end: date) -> Sequence[WorkoutLog]:
        return [w for w in self.workouts if start <= w.performed_on <= end]


class _FakeProgressService:
    """Stub progress service with configurable histories."""

    def __init__(
        self,
        weights: Sequence[DatedValue] | None = None,
        measurements: Mapping[str, Sequence[DatedValue]] | None = None,
        goals: Sequence[GoalEntry] | None = None,
    ) -> None:
        self.weights = list(weights or [])
        self.measurements = dict(measurements or {})
        self.goals = list(goals or [])

    def get_weight_history(self, user_id: str, start: date, end: date) -> Sequence[DatedValue]:
        return [p for p in self.weights if start <= p.on <= end]

    def get_measurement_history(
        self, user_id: str, site: str, start: date, end: date
    ) -> Sequence[DatedValue]:
        return [p for p in self.measurements.get(site, []) if start <= p.on <= end]

    def get_goal_history(self, user_id: str) -> Sequence[GoalEntry]:
        return self.goals


class _FakeRetriever:
    """Stub RAG retriever that returns a fixed document list."""

    def __init__(self, docs: Sequence[str] | None = None) -> None:
        self.docs = list(docs or [])
        self.searches: list[tuple[str, str, int]] = []

    def search(self, query: str, user_id: str, k: int = 4) -> list[str]:
        self.searches.append((query, user_id, k))
        return list(self.docs[:k])


@pytest.fixture
def fake_llm() -> TextCompleter:
    """Stub LLM completer for unit tests."""
    return _FakeLLM()


@pytest.fixture
def fake_memory_reader() -> MemoryReader:
    """Stub that returns an empty current-memory mapping."""
    return _FakeMemoryReader()


@pytest.fixture
def fake_memory_writer() -> MemoryWriter:
    """Stub memory writer that reports every operation as successful."""
    return _FakeMemoryWriter()


@pytest.fixture
def fake_workout_service() -> WorkoutService:
    """Stub workout service with no persisted data."""
    return _FakeWorkoutService()


@pytest.fixture
def fake_progress_service() -> ProgressService:
    """Stub progress service with no persisted history."""
    return _FakeProgressService()


@pytest.fixture
def fake_retriever() -> Retriever:
    """Stub RAG retriever that returns an empty document list."""
    return _FakeRetriever()


@pytest.fixture
def now() -> datetime:
    """Fixed UTC datetime for deterministic tests."""
    return datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Person 1 fixtures: database, authentication, API clients
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session() -> Iterator[Session]:
    """Provide a session bound to a fresh in-memory SQLite database."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = test_session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def make_client(db_session: Session) -> Iterator[object]:
    """Return a factory producing authenticated TestClients with distinct users."""
    registry: dict[str, AuthUser] = {}

    def _override_db() -> Iterator[Session]:
        yield db_session

    def _override_auth(request: Request) -> AuthUser:
        token = request.headers.get("Authorization", "")
        user = registry.get(token)
        if user is None:
            raise AuthenticationError("A bearer access token is required.")
        return user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_auth_user] = _override_auth

    def _factory(auth_user: AuthUser | None = None) -> TestClient:
        user = auth_user or AuthUser(id=uuid.uuid4(), email="user@example.com")
        token = f"Bearer test-{user.id}"
        registry[token] = user
        return TestClient(app, headers={"Authorization": token})

    try:
        yield _factory
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def client(make_client) -> TestClient:
    """A default authenticated client."""
    return make_client()


@pytest.fixture
def anon_client(db_session: Session) -> Iterator[TestClient]:
    """A client with only the database dependency overridden (no auth)."""

    def _override_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
