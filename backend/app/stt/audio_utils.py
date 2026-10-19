"""Audio decoding, resampling and silence checks for the backend STT endpoint.

The browser records with `MediaRecorder`, which yields compressed containers
(`audio/webm;codecs=opus` in Chromium, `audio/mp4` in Safari). Granite Speech
5.0 TurboCTC expects a mono 16 kHz float32 waveform, so everything is decoded
and resampled here, once, before it reaches the model.
"""

from __future__ import annotations

import io
import shutil
import subprocess
from dataclasses import dataclass
from math import gcd

import numpy as np

# Granite Speech 5.0 TurboCTC ships a 16 kHz log-mel front-end (see the model's
# `preprocessor_config.json`), so every clip is normalised to this rate.
TARGET_SAMPLE_RATE = 16_000

# Anything shorter than this cannot hold a word and only wastes an inference.
MIN_DURATION_SECONDS = 0.3

# Root-mean-square amplitude below which a clip counts as silence.
SILENCE_RMS_THRESHOLD = 1e-4

WAV_SUFFIXES = (".wav", ".wave")
FFMPEG_FORMATS = ("webm", "ogg", "oga", "opus", "mp4", "m4a", "mp3", "aac", "flac", "3gp")


class AudioValidationError(ValueError):
    """The uploaded bytes are not usable audio (empty, truncated or too short)."""


class UnsupportedAudioError(AudioValidationError):
    """The container cannot be decoded with the tools available on this machine."""


@dataclass(frozen=True)
class DecodedAudio:
    """A mono, float32 waveform ready for the model."""

    samples: np.ndarray
    sample_rate: int
    source_format: str
    original_sample_rate: int

    @property
    def duration_s(self) -> float:
        return float(len(self.samples) / self.sample_rate) if self.sample_rate else 0.0

    def summary(self) -> dict[str, float | int | str]:
        return {
            "duration_s": round(self.duration_s, 3),
            "sample_rate": self.sample_rate,
            "source_format": self.source_format,
            "original_sample_rate": self.original_sample_rate,
            "rms": round(rms(self.samples), 8),
        }


def rms(samples: np.ndarray) -> float:
    """Root-mean-square level of a waveform, 0.0 for an empty clip."""
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))


def is_silent(samples: np.ndarray, threshold: float = SILENCE_RMS_THRESHOLD) -> bool:
    """True when a clip carries no usable energy (silence or near-silence)."""
    return samples.size == 0 or rms(samples) < threshold


def to_mono(samples: np.ndarray) -> np.ndarray:
    """Average interleaved channels down to a single float32 channel."""
    array = np.asarray(samples, dtype=np.float32)
    if array.ndim == 1:
        return array
    if array.ndim == 2:
        return array.mean(axis=1, dtype=np.float32)
    raise AudioValidationError(f"Unsupported audio shape: {array.shape}")


def resample(samples: np.ndarray, orig_sr: int, target_sr: int = TARGET_SAMPLE_RATE) -> np.ndarray:
    """Band-limited resampling to `target_sr` (polyphase, falling back to linear)."""
    array = np.asarray(samples, dtype=np.float32)
    if orig_sr <= 0:
        raise AudioValidationError(f"Invalid source sample rate: {orig_sr}")
    if orig_sr == target_sr or array.size == 0:
        return array

    divisor = gcd(int(orig_sr), int(target_sr))
    up, down = int(target_sr) // divisor, int(orig_sr) // divisor
    try:
        from scipy.signal import resample_poly

        return resample_poly(array, up, down).astype(np.float32, copy=False)
    except ImportError:  # pragma: no cover - scipy is a declared dependency
        duration = array.size / orig_sr
        target_length = max(1, int(round(duration * target_sr)))
        source_positions = np.linspace(0.0, array.size - 1, target_length, dtype=np.float64)
        return np.interp(source_positions, np.arange(array.size), array).astype(np.float32)


def _decode_wav(data: bytes) -> tuple[np.ndarray, int]:
    import soundfile as sf

    try:
        samples, sample_rate = sf.read(io.BytesIO(data), dtype="float32", always_2d=False)
    except Exception as exc:  # soundfile raises several unrelated exception types
        raise AudioValidationError(f"Could not read the WAV file: {exc}") from exc
    return np.asarray(samples), int(sample_rate)


def _decode_with_pyav(data: bytes) -> tuple[np.ndarray, int]:
    """Decode any container PyAV supports (webm/opus, mp4, m4a, mp3) to 16 kHz mono.

    PyAV ships its own FFmpeg libraries, so this needs no system install.
    """
    try:
        import av
    except ImportError as exc:
        raise UnsupportedAudioError(
            "This audio format needs a decoder. Install one of: "
            "`pip install av` (bundles FFmpeg, recommended) or install ffmpeg on PATH."
        ) from exc

    try:
        decoded: list[np.ndarray] = []
        with av.open(io.BytesIO(data)) as container:
            resampler = av.AudioResampler(format="fltp", layout="mono", rate=TARGET_SAMPLE_RATE)
            for frame in container.decode(audio=0):
                for resampled in resampler.resample(frame):
                    decoded.append(_frame_to_mono(resampled))
            # Flush the resampler's tail.
            for resampled in resampler.resample(None):
                decoded.append(_frame_to_mono(resampled))
    except UnsupportedAudioError:
        raise
    except Exception as exc:
        raise UnsupportedAudioError(f"Could not decode the audio: {exc}") from exc

    if not decoded:
        raise AudioValidationError("The uploaded file contained no audio frames.")
    samples = np.concatenate(decoded).astype(np.float32, copy=False)
    return samples, TARGET_SAMPLE_RATE


def _frame_to_mono(frame) -> np.ndarray:
    array = frame.to_ndarray()
    return array.mean(axis=0, dtype=np.float32) if array.ndim > 1 else array.astype(np.float32)


def _decode_with_ffmpeg(data: bytes, source_format: str) -> tuple[np.ndarray, int]:
    binary = shutil.which("ffmpeg")
    if not binary:
        raise UnsupportedAudioError(
            f"Cannot decode '{source_format}' audio: neither PyAV nor ffmpeg is available. "
            "Install one of: `pip install av` (recommended) or ffmpeg on PATH."
        )
    command = [
        binary,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        "pipe:0",
        "-f",
        "f32le",
        "-acodec",
        "pcm_f32le",
        "-ac",
        "1",
        "-ar",
        str(TARGET_SAMPLE_RATE),
        "pipe:1",
    ]
    try:
        completed = subprocess.run(
            command, input=data, capture_output=True, check=False, timeout=120
        )
    except subprocess.TimeoutExpired as exc:
        raise AudioValidationError("Decoding the audio timed out.") from exc
    if completed.returncode != 0 or not completed.stdout:
        detail = completed.stderr.decode("utf-8", "replace").strip().splitlines()
        raise UnsupportedAudioError(
            f"ffmpeg could not decode the uploaded audio: {detail[-1] if detail else 'unknown error'}"
        )
    samples = np.frombuffer(completed.stdout, dtype=np.float32).copy()
    return samples, TARGET_SAMPLE_RATE


def _format_from(data: bytes, filename: str | None) -> str:
    if filename and "." in filename:
        return filename.rsplit(".", 1)[-1].lower()
    if data[:4] == b"RIFF":
        return "wav"
    if data[:4] == b"OggS":
        return "ogg"
    if data[4:8] == b"ftyp":
        return "mp4"
    return "unknown"


def decode_audio(
    data: bytes,
    filename: str | None = None,
    target_sample_rate: int = TARGET_SAMPLE_RATE,
    min_duration_s: float = MIN_DURATION_SECONDS,
) -> DecodedAudio:
    """Decode uploaded bytes into a mono float32 waveform at `target_sample_rate`.

    Raises `AudioValidationError` for empty, corrupt or too-short audio and
    `UnsupportedAudioError` when the container needs a decoder we do not have.
    """
    if not data:
        raise AudioValidationError("The recording was empty. Please record again.")

    source_format = _format_from(data, filename)
    if source_format == "wav":
        raw, sample_rate = _decode_wav(data)
    elif source_format in FFMPEG_FORMATS:
        # PyAV first (self-contained), then a system ffmpeg if one is installed.
        try:
            raw, sample_rate = _decode_with_pyav(data)
        except UnsupportedAudioError as pyav_error:
            try:
                raw, sample_rate = _decode_with_ffmpeg(data, source_format)
            except UnsupportedAudioError:
                raise pyav_error from None
    else:
        raise UnsupportedAudioError(
            f"Unsupported audio format '{source_format}'. Record with the browser "
            "(webm/opus or mp4) or upload a WAV file."
        )

    mono = to_mono(raw)
    if mono.size == 0:
        raise AudioValidationError("The recording contained no audio samples.")

    resampled = resample(mono, sample_rate, target_sample_rate)
    decoded = DecodedAudio(
        samples=resampled,
        sample_rate=target_sample_rate,
        source_format=source_format,
        original_sample_rate=sample_rate,
    )
    if decoded.duration_s < min_duration_s:
        raise AudioValidationError(
            f"The recording is only {decoded.duration_s:.2f}s long. Record at least {min_duration_s:.1f}s."
        )
    return decoded


def write_wav(path: str, samples: np.ndarray, sample_rate: int = TARGET_SAMPLE_RATE) -> None:
    """Write a float32 mono clip as 16-bit PCM WAV (used by tests and tooling)."""
    import soundfile as sf

    clipped = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
    sf.write(path, clipped, sample_rate, subtype="PCM_16")


def wav_bytes(samples: np.ndarray, sample_rate: int = TARGET_SAMPLE_RATE) -> bytes:
    """Encode a float32 mono clip as WAV bytes, for tests and local tooling."""
    buffer = io.BytesIO()
    import soundfile as sf

    clipped = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
    sf.write(buffer, clipped, sample_rate, format="WAV", subtype="PCM_16")
    return buffer.getvalue()
