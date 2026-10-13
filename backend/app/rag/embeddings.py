"""Single embedding configuration shared by indexing and retrieval.

Uses ChromaDB's default local embedding function (ONNX all-MiniLM-L6-v2): no API key.
The model files are downloaded by Chroma on first use, then cached locally.
"""

from __future__ import annotations

import logging
import shutil
from functools import lru_cache
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Stored in collection metadata; a mismatch means the index must be rebuilt.
EMBEDDING_NAME = "chroma-default-onnx-minilm-l6-v2"

_ONNX_REQUIRED_FILES = (
    "config.json",
    "model.onnx",
    "special_tokens_map.json",
    "tokenizer_config.json",
    "tokenizer.json",
    "vocab.txt",
)


def _onnx_paths() -> tuple[Path, Path]:
    """Return (archive, extracted_folder) for the Chroma ONNX model cache."""
    from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2

    root = Path(ONNXMiniLM_L6_V2.DOWNLOAD_PATH)
    return root / ONNXMiniLM_L6_V2.ARCHIVE_FILENAME, root / ONNXMiniLM_L6_V2.EXTRACTED_FOLDER_NAME


def is_embedding_model_cached() -> bool:
    """True when the ONNX model is fully extracted and usable offline."""
    try:
        _, extracted = _onnx_paths()
    except OSError:
        return False
    return all((extracted / name).is_file() for name in _ONNX_REQUIRED_FILES)


def repair_embedding_cache() -> bool:
    """Remove an unusable ONNX model cache so Chroma can download the model again.

    Chroma verifies the downloaded archive with SHA256 and retries the whole
    download on a mismatch, but it leaves the zero-byte or truncated archive in
    place. Every later embedding attempt then re-checks and re-downloads the
    model, which stalls indexing. Deleting the unusable files breaks that cycle.

    Returns True when the model is cached and usable; False when a download on
    the next embedding call is still required.
    """
    try:
        if is_embedding_model_cached():
            return True

        archive, extracted = _onnx_paths()
        removed = False
        # An empty archive is never usable, and an empty extracted folder only
        # holds leftovers from an interrupted download.
        if archive.exists() and archive.stat().st_size == 0:
            archive.unlink()
            removed = True
        if extracted.exists() and not any(extracted.iterdir()):
            shutil.rmtree(extracted, ignore_errors=True)
            removed = True

        if removed:
            log.warning("removed corrupted embedding cache at %s", archive.parent)
        return False
    except OSError as exc:
        # Never block ingestion because cache maintenance failed.
        log.warning("embedding cache repair failed: %s", exc)
        return False


@lru_cache(maxsize=1)
def get_embedding_function() -> Any:
    """Return the process-wide embedding function (same object for add and query)."""
    from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

    repair_embedding_cache()
    return DefaultEmbeddingFunction()
