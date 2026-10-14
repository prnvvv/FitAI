"""Tests for the shared embedding configuration and its cache self-healing."""

from __future__ import annotations

from pathlib import Path

from app.rag import embeddings

_REQUIRED = embeddings._ONNX_REQUIRED_FILES


def _fake_cache(tmp_path: Path, monkeypatch, *, archive_size: int, extract: bool) -> Path:
    root = tmp_path / "onnx_models" / "all-MiniLM-L6-v2"
    root.mkdir(parents=True)
    archive = root / "onnx.tar.gz"
    archive.write_bytes(b"x" * archive_size)
    if extract:
        folder = root / "onnx"
        folder.mkdir()
        for name in _REQUIRED:
            (folder / name).write_text("stub")
    monkeypatch.setattr(
        embeddings,
        "_onnx_paths",
        lambda: (archive, root / "onnx"),
    )
    return archive


def test_repair_removes_zero_byte_archive(monkeypatch, tmp_path: Path) -> None:
    archive = _fake_cache(tmp_path, monkeypatch, archive_size=0, extract=False)

    repaired = embeddings.repair_embedding_cache()

    assert repaired is False
    assert not archive.exists()
    assert embeddings.is_embedding_model_cached() is False


def test_repair_keeps_complete_cache(monkeypatch, tmp_path: Path) -> None:
    archive = _fake_cache(tmp_path, monkeypatch, archive_size=1024, extract=True)

    repaired = embeddings.repair_embedding_cache()

    assert repaired is True
    assert archive.exists()
    assert embeddings.is_embedding_model_cached() is True


def test_repair_removes_empty_extracted_folder(monkeypatch, tmp_path: Path) -> None:
    _fake_cache(tmp_path, monkeypatch, archive_size=1024, extract=True)
    extracted = tmp_path / "onnx_models" / "all-MiniLM-L6-v2" / "onnx"
    for item in extracted.iterdir():
        item.unlink()

    # A partially extracted folder is left for Chroma to re-extract; the point
    # is that repair reports the model is not ready for offline use.
    assert embeddings.repair_embedding_cache() is False
    assert not extracted.exists()
    assert embeddings.is_embedding_model_cached() is False


def test_repair_survives_unreadable_cache(monkeypatch, tmp_path: Path) -> None:
    def _boom():
        raise OSError("permission denied")

    monkeypatch.setattr(embeddings, "_onnx_paths", _boom)

    assert embeddings.repair_embedding_cache() is False
