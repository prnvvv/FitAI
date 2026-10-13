"""Shared pytest fixtures for the FitAI backend test suite.

Real test bodies will be added in a follow-up step. Fixtures here are empty stubs
that mirror the production protocols so tests can inject fakes later.
"""
from __future__ import annotations

import pytest

from app.agent.nodes import MemoryReader, Retriever
from app.memory.confirmation import MemoryWriter
from app.memory.extractor import TextCompleter
from app.tools.progress_tools import ProgressService
from app.tools.workout_tools import WorkoutService


@pytest.fixture
def fake_llm() -> TextCompleter:
    """Stub LLM completer that returns an empty JSON object."""
    return None  # type: ignore[return-value]


@pytest.fixture
def fake_memory_reader() -> MemoryReader:
    """Stub that returns an empty current-memory mapping."""
    return None  # type: ignore[return-value]


@pytest.fixture
def fake_memory_writer() -> MemoryWriter:
    """Stub memory writer that reports every operation as unconfirmed."""
    return None  # type: ignore[return-value]


@pytest.fixture
def fake_workout_service() -> WorkoutService:
    """Stub workout service with no persisted data."""
    return None  # type: ignore[return-value]


@pytest.fixture
def fake_progress_service() -> ProgressService:
    """Stub progress service with no persisted history."""
    return None  # type: ignore[return-value]


@pytest.fixture
def fake_retriever() -> Retriever:
    """Stub RAG retriever that returns an empty document list."""
    return None  # type: ignore[return-value]
