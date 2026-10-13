"""Allow `python -m scripts` to delegate to the knowledge ingestion CLI."""
from __future__ import annotations

from .ingest_knowledge import main

if __name__ == "__main__":
    raise SystemExit(main())
