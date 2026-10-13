# FitAI Unit Tests

Tests are organized to mirror the `app/` module layout (one test file per
production module). Run them from the `backend/` directory with:

```bash
python -m pytest tests/unit -v
```

External services (Groq, ChromaDB, databases) are mocked so unit tests do not
require live credentials.
