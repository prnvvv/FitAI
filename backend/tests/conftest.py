"""Shared pytest fixtures.

Tests run against an isolated in-memory SQLite database. Authentication is
overridden through a small token registry so that no live Supabase credentials
are required, while ``anon_client`` exercises the real verification dependency.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (register all models)
from app.api.deps import get_current_auth_user
from app.core.errors import AuthenticationError
from app.core.security import AuthUser
from app.db.base import Base
from app.db.session import get_db
from app.main import app


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
