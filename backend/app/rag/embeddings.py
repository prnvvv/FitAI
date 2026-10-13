"""Single embedding configuration shared by indexing and retrieval.

Uses ChromaDB's default local embedding function (ONNX all-MiniLM-L6-v2): no API key.
The model files are downloaded by Chroma on first use, then cached locally.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

# Stored in collection metadata; a mismatch means the index must be rebuilt.
EMBEDDING_NAME = "chroma-default-onnx-minilm-l6-v2"


@lru_cache(maxsize=1)
def get_embedding_function() -> Any:
    """Return the process-wide embedding function (same object for add and query)."""
    from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

    return DefaultEmbeddingFunction()
