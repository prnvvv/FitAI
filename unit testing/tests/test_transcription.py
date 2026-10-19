"""Model loading, inference and error handling with an injected fake model."""

from __future__ import annotations

import numpy as np
import pytest

from audio_utils import TARGET_SAMPLE_RATE
from conftest import FakeModel, FakeProcessor, make_service
from speech_service import ModelLoadError, SpeechService, TranscriptionError


def test_transcribes_with_the_loaded_model(service, speech_sample):
    result = service.transcribe(speech_sample)

    assert result.text == "hello from granite"
    assert result.device == "cpu"
    assert result.duration_s == pytest.approx(1.0, abs=0.01)
    assert result.warnings == []


def test_loads_the_model_once_and_reuses_it(speech_sample):
    loads: list[int] = []

    def loader():
        loads.append(1)
        return FakeProcessor(), FakeModel()

    service = SpeechService(model_id="test/model", device="cpu", loader=loader, transcriber=lambda *_: "cached")
    service.load()
    service.load()
    service.transcribe(speech_sample)
    service.transcribe(speech_sample)

    assert len(loads) == 1
    assert service.status_dict()["requests"] == 2


def test_lazy_load_happens_on_first_request(speech_sample):
    def loader():
        return FakeProcessor(), FakeModel()

    service = SpeechService(model_id="test/model", device="cpu", loader=loader, transcriber=lambda *_: "lazy")
    assert service.status.state == "idle"

    service.transcribe(speech_sample)

    assert service.status.state == "ready"
    assert service.status.device == "cpu"


def test_warmup_swallows_the_error_and_records_it():
    service = SpeechService(
        model_id="test/model",
        device="cpu",
        loader=lambda: (_ for _ in ()).throw(RuntimeError("checkpoint missing")),
        transcriber=lambda *_: "",
    )

    service.warmup()  # must not raise in the background thread

    assert service.status.state == "error"
    assert "checkpoint missing" in service.status.error


def test_transcribe_raises_when_the_model_failed_to_load():
    service = SpeechService(
        model_id="test/model",
        device="cpu",
        loader=lambda: (_ for _ in ()).throw(RuntimeError("no weights")),
        transcriber=lambda *_: "",
    )
    with pytest.raises(ModelLoadError):
        service.load()

    with pytest.raises(ModelLoadError, match="no weights"):
        service.transcribe(np.zeros(1600, dtype=np.float32))


def test_inference_errors_are_wrapped(speech_sample):
    def transcriber(processor, model, samples, sample_rate):
        raise RuntimeError("CUDA out of memory")

    service = SpeechService(
        model_id="test/model", device="cpu", loader=lambda: (FakeProcessor(), FakeModel()), transcriber=transcriber
    )
    service.load()

    with pytest.raises(TranscriptionError, match="CUDA out of memory"):
        service.transcribe(speech_sample)


def test_an_empty_transcript_is_flagged(speech_sample):
    service = make_service(transcript="   ")

    result = service.transcribe(speech_sample)

    assert result.text == ""
    assert result.warnings == ["The model returned an empty transcript."]


def test_transcriber_receives_the_resampled_waveform(speech_sample):
    seen: dict[str, object] = {}

    def transcriber(processor, model, samples, sample_rate):
        seen["samples"] = samples
        seen["sample_rate"] = sample_rate
        return "ok"

    service = SpeechService(
        model_id="test/model", device="cpu", loader=lambda: (FakeProcessor(), FakeModel()), transcriber=transcriber
    )
    service.load()
    service.transcribe(speech_sample)

    assert seen["sample_rate"] == TARGET_SAMPLE_RATE
    assert isinstance(seen["samples"], np.ndarray)
    assert seen["samples"].size == TARGET_SAMPLE_RATE


def test_status_reports_the_configured_model(service):
    status = service.status_dict()

    assert status["state"] == "ready"
    assert status["model_id"] == "test/model"
    assert status["sample_rate"] == TARGET_SAMPLE_RATE
    assert status["error"] == ""