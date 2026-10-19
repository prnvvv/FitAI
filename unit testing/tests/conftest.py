"""Test fixtures: no torch, no transformers, no model download, no API key."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audio_utils import TARGET_SAMPLE_RATE, wav_bytes  # noqa: E402
from speech_service import SpeechService, set_service  # noqa: E402


class FakeProcessor:
    """Stands in for `AutoProcessor`."""

    feature_extractor = type("FeatureExtractor", (), {"sampling_rate": TARGET_SAMPLE_RATE})()

    def __call__(self, samples, sampling_rate, device):
        assert isinstance(samples, list) and samples
        assert sampling_rate == TARGET_SAMPLE_RATE
        assert device == "cpu"
        return {"input_values": np.asarray(samples, dtype=np.float32)}


class FakeModel:
    device = "cpu"
    dtype = "float32"

    def __init__(self, outputs=("hello from granite",)) -> None:
        self.outputs = list(outputs)


def make_service(transcript: str = "hello from granite", load_error: Exception | None = None) -> SpeechService:
    """A SpeechService with injected loader/transcriber, ready to use offline."""
    calls: list[int] = []

    def loader():
        if load_error is not None:
            raise load_error
        return FakeProcessor(), FakeModel([transcript])

    def transcriber(processor, model, samples, sample_rate):
        calls.append(len(samples))
        return transcript

    service = SpeechService(model_id="test/model", device="cpu", loader=loader, transcriber=transcriber)
    service.load()
    return service


@pytest.fixture
def speech_sample() -> np.ndarray:
    """A 1 s 440 Hz tone: non-silent, mono, 16 kHz."""
    t = np.linspace(0.0, 1.0, TARGET_SAMPLE_RATE, endpoint=False, dtype=np.float32)
    return (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)


@pytest.fixture
def silent_sample() -> np.ndarray:
    return np.zeros(TARGET_SAMPLE_RATE, dtype=np.float32)


@pytest.fixture
def wav_upload(speech_sample: np.ndarray) -> bytes:
    return wav_bytes(speech_sample)


@pytest.fixture
def service() -> SpeechService:
    built = make_service()
    yield built
    set_service(None)


@pytest.fixture
def client(service: SpeechService):
    from fastapi.testclient import TestClient

    import app as app_module

    set_service(service)
    with TestClient(app_module.app) as test_client:
        yield test_client
    set_service(None)