# FitAI Unit Tests

Tests are organized to mirror the `app/` module layout (one test file per
production module):

- `test_config.py` — settings parsing and derived properties.
- `test_security.py` — Supabase token verification (symmetric mode).
- `test_memory_validation.py` — structured memory value validation.

These tests have been written but **not yet run**; execution is pending
authorization. They run against an in-memory SQLite database via
`tests/conftest.py` and require no live credentials.