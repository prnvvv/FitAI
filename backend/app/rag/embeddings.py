"""Single embedding configuration shared by indexing and retrieval.

Two providers, selected by ``EMBEDDING_PROVIDER``:

* ``local`` (development default): ChromaDB's bundled ONNX all-MiniLM-L6-v2. No API
  key, but the model files are downloaded on first use and it needs well over
  100 MB of RAM, so it is not used on the 512 MB production services.
* ``remote``: an HTTP feature-extraction endpoint serving the *same* model family
  (384-dimension vectors). No model is loaded in-process. The endpoint is never
  defaulted: it must be configured, and a missing configuration fails loudly.

Both providers must produce ``EMBEDDING_DIMENSION`` floats per text; anything else
is rejected so a mismatched model can never be written to the index.
"""

from __future__ import annotations

import logging
import shutil
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings

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


class EmbeddingError(RuntimeError):
    """The embedding provider is misconfigured, unreachable or returned bad data."""


class RemoteEmbedder:
    """Embeds text through an HTTP endpoint using a shared, bounded client.

    ``api_format`` selects the request/response shape:

    * ``hf``: ``{"inputs": [...]}`` -> ``[[...], ...]`` (HuggingFace feature-extraction).
    * ``openai``: ``{"input": [...], "model": ...}`` -> ``{"data": [{"embedding": [...]}]}``.

    Texts are sent in bounded batches. The instance is callable with the ChromaDB
    ``EmbeddingFunction`` signature so the existing Chroma store can use it too.
    """

    def __init__(
        self,
        url: str | None,
        api_key: str | None,
        *,
        dimension: int,
        model: str | None = None,
        api_format: str = "hf",
        batch_size: int = 32,
        timeout_s: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        if not url or not api_key:
            raise EmbeddingError(
                "Remote embeddings are not configured: set EMBEDDING_API_URL and EMBEDDING_API_KEY."
            )
        if api_format not in {"hf", "openai"}:
            raise EmbeddingError("EMBEDDING_API_FORMAT must be 'hf' or 'openai'.")
        self._url, self._key, self._model = url, api_key, model
        self._format, self.dimension = api_format, dimension
        self._batch = max(1, batch_size)
        self._client = client or httpx.Client(timeout=httpx.Timeout(timeout_s, connect=10.0))

    def name(self) -> str:  # ChromaDB EmbeddingFunction protocol
        return "fitai-remote-embedder"

    def __call__(self, input: Sequence[str]) -> list[list[float]]:  # noqa: A002 - Chroma API
        return self.embed(input)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one ``dimension``-length vector per text, in order."""
        vectors: list[list[float]] = []
        for i in range(0, len(texts), self._batch):
            vectors.extend(self._embed_batch(list(texts[i : i + self._batch])))
        return vectors

    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        body: dict[str, Any] = (
            {"inputs": batch, "options": {"wait_for_model": True}}
            if self._format == "hf"
            else {"input": batch, "model": self._model}
        )
        try:
            response = self._client.post(
                self._url, json=body, headers={"Authorization": f"Bearer {self._key}"}
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            # Never include the response body or headers: they may echo the key.
            raise EmbeddingError(f"embedding request failed ({type(exc).__name__})") from exc

        rows = (
            [item.get("embedding") for item in payload.get("data", [])]
            if isinstance(payload, dict)
            else payload
        )
        if not isinstance(rows, list) or len(rows) != len(batch):
            raise EmbeddingError("embedding provider returned an unexpected number of vectors")
        out: list[list[float]] = []
        for row in rows:
            if (
                not isinstance(row, list)
                or len(row) != self.dimension
                or not all(isinstance(x, int | float) for x in row)
            ):
                raise EmbeddingError(
                    f"embedding provider returned a vector that is not {self.dimension}-dimensional"
                )
            out.append([float(x) for x in row])
        return out


@lru_cache(maxsize=1)
def get_embedding_function() -> Any:
    """Return the process-wide embedding function (same object for add and query)."""
    if settings.embedding_provider.strip().lower() == "remote":
        return get_remote_embedder()
    from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

    repair_embedding_cache()
    return DefaultEmbeddingFunction()


@lru_cache(maxsize=1)
def get_remote_embedder() -> RemoteEmbedder:
    """Return the shared remote embedder built from settings."""
    return RemoteEmbedder(
        settings.embedding_api_url,
        settings.embedding_api_key,
        dimension=settings.embedding_dimension,
        model=settings.embedding_remote_model,
        api_format=settings.embedding_api_format,
        batch_size=settings.embedding_batch_size,
        timeout_s=settings.embedding_timeout_s,
    )


def embed_texts(texts: Sequence[str]) -> list[list[float]]:
    """Embed ``texts`` with the configured provider (used by the pgvector store)."""
    return [list(map(float, v)) for v in get_embedding_function()(list(texts))]
