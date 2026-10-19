"""Audio validation and preprocessing."""

from __future__ import annotations

import io

import numpy as np
import pytest
import soundfile as sf

from audio_utils import (
    TARGET_SAMPLE_RATE,
    AudioValidationError,
    UnsupportedAudioError,
    decode_audio,
    is_silent,
    resample,
    rms,
    to_mono,
    wav_bytes,
)


def test_decodes_wav_and_normalises_to_16k_mono(speech_sample):
    decoded = decode_audio(wav_bytes(speech_sample))

    assert decoded.sample_rate == TARGET_SAMPLE_RATE
    assert decoded.source_format == "wav"
    assert decoded.samples.dtype == np.float32
    assert decoded.samples.ndim == 1
    assert decoded.duration_s == pytest.approx(1.0, abs=0.01)


def test_downmixes_stereo_to_mono():
    left = np.full(8000, 0.5, dtype=np.float32)
    right = np.full(8000, -0.5, dtype=np.float32)
    buffer = io.BytesIO()
    sf.write(buffer, np.stack([left, right], axis=1), 16000, format="WAV")

    decoded = decode_audio(buffer.getvalue(), "clip.wav")

    assert decoded.samples.ndim == 1
    assert np.allclose(decoded.samples, 0.0, atol=1e-4)


def test_resamples_48k_down_to_16k():
    tone = np.sin(2 * np.pi * 220 * np.arange(48000) / 48000).astype(np.float32)

    resampled = resample(tone, 48000, TARGET_SAMPLE_RATE)

    assert resampled.size == pytest.approx(16000, rel=0.01)
    assert resampled.dtype == np.float32


def test_resample_is_a_no_op_at_the_target_rate(speech_sample):
    assert resample(speech_sample, TARGET_SAMPLE_RATE) is speech_sample


def test_rejects_an_empty_upload():
    with pytest.raises(AudioValidationError, match="empty"):
        decode_audio(b"", "clip.wav")


def test_rejects_truncated_wav_data():
    good = wav_bytes(np.zeros(16000, dtype=np.float32))

    with pytest.raises(AudioValidationError):
        decode_audio(good[:40], "clip.wav")


def test_rejects_a_recording_shorter_than_the_minimum():
    tiny = wav_bytes(np.zeros(1600, dtype=np.float32))  # 0.1 s

    with pytest.raises(AudioValidationError, match="at least"):
        decode_audio(tiny, "clip.wav")


def test_rejects_an_unsupported_container(wav_upload):
    with pytest.raises(UnsupportedAudioError, match="Unsupported audio format"):
        decode_audio(b"\x00\x01\x02\x03not-audio", "clip.aiff")


def test_reports_a_missing_ffmpeg_decoder_for_opus(monkeypatch):
    monkeypatch.setattr("audio_utils.shutil.which", lambda _: None)

    with pytest.raises(UnsupportedAudioError, match="ffmpeg was not found"):
        decode_audio(b"OggS" + b"\x00" * 64, "clip.webm")


def test_silence_is_detected_and_a_tone_is_not(silent_sample, speech_sample):
    assert is_silent(silent_sample) is True
    assert is_silent(speech_sample) is False
    assert rms(np.array([], dtype=np.float32)) == 0.0


def test_to_mono_rejects_an_unexpected_shape():
    with pytest.raises(AudioValidationError, match="Unsupported audio shape"):
        to_mono(np.zeros((2, 2, 2), dtype=np.float32))


def test_summary_reports_duration_rate_and_level(wav_upload):
    summary = decode_audio(wav_upload, "clip.wav").summary()

    assert summary["duration_s"] == pytest.approx(1.0, abs=0.01)
    assert summary["sample_rate"] == TARGET_SAMPLE_RATE
    assert summary["source_format"] == "wav"
    assert summary["rms"] > 0