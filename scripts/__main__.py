"""Allow `python -m scripts` to delegate to the knowledge ingestion CLI."""
from __future__ import annotations

import multiprocessing
import sys

# On Windows, set the multiprocessing start method to 'spawn' before any
# multiprocessing code runs (ChromaDB's ONNX embedding may spawn processes).
if sys.platform == "win32":
    multiprocessing.set_start_method("spawn", force=True)

from .ingest_knowledge import main

if __name__ == "__main__":
    raise SystemExit(main())
