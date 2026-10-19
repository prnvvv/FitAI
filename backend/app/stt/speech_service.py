"""Local Granite Speech 5.0 TurboCTC inference for the FitAI backend.

The model card documents native support in `transformers>=5.16.0` and shows the
exact procedure this module follows:

    processor = AutoProcessor.from_pretrained(model_id)
    model = AutoModelForCTC.from_pretrained(model_id, device_map="auto")
    inputs = processor(samples, sampling_rate=..., device=model.device)
    inputs.to(model.device, dtype=model.dtype)
    outputs = model.generate(**inputs)
    processor.batch_decode(outputs, skip_special_tokens=True)

The model is public (`gated: false`), so no token is required to download it;
`HUGGINGFACE_API_KEY` is only read when present, for authenticated or faster
downloads, and is never sent anywhere else.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from app.stt.audio_utils import TARGET_SAMPLE_RATE

DEFAULT_MODEL_ID = "ibm-granite/granite-speech-5.0-470m-turboctc"
MIN_TRANSCRIPT_CHARS = 1


class ModelLoadError(RuntimeError):
    """The model or its processor could not be loaded."""


class TranscriptionError(RuntimeError):
    """Inference failed (bad input shape, out of memory, decode failure...)."""


@dataclass
class ServiceStatus:
    state: str = "idle"  # idle | loading | ready | error
    model_id: str = DEFAULT_MODEL_ID
    device: str = "not loaded"
    sample_rate: int = TARGET_SAMPLE_RATE
    detail: str = ""
    error: str = ""
    load_seconds: float = 0.0
    requests: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "state": self.state,
            "model_id": self.model_id,
            "device": self.device,
            "sample_rate": self.sample_rate,
            "detail": self.detail,
            "error": self.error,
            "load_seconds": round(self.load_seconds, 2),
            "requests": self.requests,
        }


@dataclass
class TranscriptionResult:
    text: str
    duration_s: float
    model_id: str
    device: str
    load_seconds: float = 0.0
    warnings: list[str] = field(default_factory=list)


def read_local_env(path: str | Path = ".env") -> dict[str, str]:
    """Read a tiny `KEY=value` file without pulling in a dotenv dependency."""
    values: dict[str, str] = {}
    file_path = Path(path)
    if not file_path.is_file():
        return values
    for raw_line in file_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def resolve_config() -> dict[str, str]:
    """Environment variables first, then an optional local `.env` file."""
    file_values = read_local_env(Path(__file__).with_name(".env"))
    config = {
        "model_id": os.environ.get(
            "STT_MODEL_ID", file_values.get("STT_MODEL_ID", DEFAULT_MODEL_ID)
        ),
        "device": os.environ.get("STT_DEVICE", file_values.get("STT_DEVICE", "auto")),
        "hf_token": os.environ.get(
            "HUGGINGFACE_API_KEY", file_values.get("HUGGINGFACE_API_KEY", "")
        ),
        # Defaults to 1 so local development / production warm the model on
        # startup and the first dictation feels instant. Set STT_EAGER_LOAD=0
        # (e.g. in CI) to skip the download and load lazily on first request.
        "eager_load": os.environ.get("STT_EAGER_LOAD", file_values.get("STT_EAGER_LOAD", "1")),
    }
    return config


class SpeechService:
    """Loads Granite once and reuses it for every transcription request.

    `loader` and `transcriber` are injectable so the automated tests can run
    without torch, transformers or the 900 MB checkpoint.
    """

    def __init__(
        self,
        model_id: str | None = None,
        device: str | None = None,
        loader: Callable[[], tuple[object, object]] | None = None,
        transcriber: Callable[[object, object, np.ndarray, int], str] | None = None,
    ) -> None:
        config = resolve_config()
        self.model_id = model_id or config["model_id"]
        self.device_request = device or config["device"]
        self.eager_load = str(config["eager_load"]).strip().lower() not in {"0", "false", "no"}
        self._hf_token = config["hf_token"]
        self._loader = loader
        self._transcriber = transcriber
        self._processor: object | None = None
        self._model: object | None = None
        self._device = "not loaded"
        self.device_note = ""
        self._lock = threading.Lock()
        self._load_seconds = 0.0
        self._last_seconds = 0.0
        self._requests = 0
        self.status = ServiceStatus(model_id=self.model_id)

    # ------------------------------------------------------------------ load

    @staticmethod
    def _dependency_hint(error: Exception) -> str:
        """Turn the most common load failures into an actionable message."""
        message = str(error).lower()
        if "torchaudio" in message:
            return (
                "\nFix: GraniteSpeech5FeatureExtractor requires torchaudio. Install a torch/torchaudio"
                " pair of the same version, e.g. `pip install torch==2.9.1 torchaudio==2.9.1`"
                " (add --index-url https://download.pytorch.org/whl/cu128 for an NVIDIA GPU)."
                " torchaudio publishes no wheel for torch 2.10+, so a newer torch cannot be paired."
            )
        if "transformers" in message or "accelerate" in message:
            return (
                "\nFix: `pip install -r requirements.txt` inside this folder's virtual environment."
            )
        if "out of memory" in message or "not enough memory" in message:
            return "\nFix: set STT_DEVICE=cpu, or close memory-hungry applications and retry."
        return ""

    def _resolve_device(self) -> tuple[str, str]:
        """Return (device_map value, note). A requested GPU that is not there
        falls back to CPU instead of failing the whole load."""
        request = (self.device_request or "auto").strip().lower()
        try:
            import torch
        except ImportError:
            return "cpu", "torch is not installed; using CPU"

        has_cuda = bool(getattr(torch, "cuda", None)) and torch.cuda.is_available()
        if request.startswith("cuda") and not has_cuda:
            return "cpu", "STT_DEVICE asks for CUDA but no GPU is available; using CPU"
        if request == "auto" and not has_cuda:
            return "cpu", "no GPU detected; using CPU"
        return request, ""

    def _default_loader(self) -> tuple[object, object]:
        """Follow the model card: AutoProcessor + AutoModelForCTC, device_map auto."""
        try:
            from transformers import AutoModelForCTC, AutoProcessor
        except ImportError as exc:  # pragma: no cover - exercised only without deps
            raise ModelLoadError(
                "transformers>=5.16.0 is required for local inference. "
                "Install the requirements in this folder's virtual environment."
            ) from exc

        token = self._hf_token or None
        common = {"token": token} if token else {}

        try:
            # `transformers` ships this architecture natively from 5.16.0.
            processor = AutoProcessor.from_pretrained(self.model_id, **common)
        except Exception as native_error:
            # The repository also ships remote-code copies of the processor.
            hint = self._dependency_hint(native_error)
            try:
                processor = AutoProcessor.from_pretrained(
                    self.model_id, trust_remote_code=True, **common
                )
            except Exception as exc:
                raise ModelLoadError(
                    f"Could not load the processor: {exc} (native: {native_error}){hint}"
                ) from exc

        device_map, note = self._resolve_device()
        self.device_note = note
        try:
            model = AutoModelForCTC.from_pretrained(self.model_id, device_map=device_map, **common)
        except Exception as exc:
            raise ModelLoadError(
                f"Could not load the model: {exc}{self._dependency_hint(exc)}"
            ) from exc

        model.eval()
        return processor, model

    def load(self) -> None:
        """Load the model once; concurrent callers wait for the same load."""
        with self._lock:
            if self.status.state == "ready":
                return
            self.status.state = "loading"
            self.status.error = ""
            self.status.detail = "Downloading and loading the checkpoint on first run"
            started = time.perf_counter()
            try:
                if self._loader is not None:
                    processor, model = self._loader()
                else:
                    processor, model = self._default_loader()
            except Exception as exc:
                self.status.state = "error"
                self.status.error = str(exc)
                self.status.detail = ""
                raise ModelLoadError(str(exc)) from exc

            self._processor = processor
            self._model = model
            self._device = getattr(model, "device", "cpu")
            self._load_seconds = time.perf_counter() - started
            self.status.state = "ready"
            self.status.device = str(self._device)
            self.status.detail = self.device_note or "Ready"
            self.status.load_seconds = self._load_seconds

    def warmup(self) -> None:
        """Background load used by the API so the UI never waits on first use."""
        try:
            self.load()
        except ModelLoadError:
            return  # Already recorded in `status.error`; surfaced through /api/status.

    def ensure_ready(self) -> None:
        if self.status.state == "ready":
            return
        if self.status.state == "error":
            raise ModelLoadError(self.status.error or "The model failed to load.")
        self.load()

    # ----------------------------------------------------------- transcribe

    def _default_transcriber(
        self, processor: object, model: object, samples: np.ndarray, sample_rate: int
    ) -> str:
        try:
            inputs = processor(
                [samples],
                sampling_rate=sample_rate,
                device=getattr(model, "device", "cpu"),
            )
            inputs = inputs.to(model.device, dtype=model.dtype)
            outputs = model.generate(**inputs)
            texts = processor.batch_decode(outputs, skip_special_tokens=True)
        except Exception as exc:
            raise TranscriptionError(f"Inference failed: {exc}") from exc
        return texts[0] if texts else ""

    def transcribe(
        self, samples: np.ndarray, sample_rate: int = TARGET_SAMPLE_RATE
    ) -> TranscriptionResult:
        """Run inference on a mono float32 waveform. Thread-safe, model reused."""
        self.ensure_ready()
        assert self._processor is not None and self._model is not None
        transcriber = self._transcriber or self._default_transcriber
        with self._lock:
            started = time.perf_counter()
            try:
                raw = transcriber(self._processor, self._model, samples, sample_rate)
            except (ModelLoadError, TranscriptionError):
                raise
            except Exception as exc:
                # Injected and real transcribers fail the same way for callers.
                raise TranscriptionError(f"Inference failed: {exc}") from exc
            finally:
                self._last_seconds = time.perf_counter() - started
            self._requests += 1
        text = (raw or "").strip()
        return TranscriptionResult(
            text=text,
            duration_s=round(len(samples) / sample_rate, 3) if sample_rate else 0.0,
            model_id=self.model_id,
            device=str(self._device),
            load_seconds=round(self._load_seconds, 2),
            warnings=[] if text else ["The model returned an empty transcript."],
        )

    def status_dict(self) -> dict[str, object]:
        payload = self.status.as_dict()
        payload["requests"] = self._requests
        payload["device_request"] = self.device_request
        payload["device_note"] = self.device_note
        payload["last_request_seconds"] = round(self._last_seconds, 2)
        return payload


_service: SpeechService | None = None
_service_lock = threading.Lock()


def get_service() -> SpeechService:
    """Process-wide singleton so the checkpoint is loaded exactly once."""
    global _service
    with _service_lock:
        if _service is None:
            _service = SpeechService()
        return _service


def set_service(service: SpeechService | None) -> None:
    """Swap the singleton (used by the tests)."""
    global _service
    with _service_lock:
        _service = service
