"""Extract text from images through a configurable provider chain.

Providers are tried in the order configured by ``VISION_PROVIDER_ORDER``:

* ``groq`` - a vision-capable Groq model. The model id comes from
  ``VISION_MODEL`` when set, otherwise from the model list of the configured
  Groq account (never from memory). The API key comes from application settings
  so a ``.env`` file is honoured.
* ``rapidocr`` - local OCR (``rapidocr-onnxruntime``, ONNX runtime). It needs no
  API key and no system binary, so image reading keeps working when the Groq
  account has no vision model or the network call fails.

Every provider is fed a prepared image: magic bytes verified, EXIF orientation
applied, converted to RGB, metadata stripped and downscaled to
``OCR_MAX_SIDE_PX``. Failures raise a readable error; the full cause is logged
server-side with ``exc_info`` and never leaks into the user-facing reason.
"""

from __future__ import annotations

import asyncio
import base64
import functools
import io
import threading
from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

log: Any = get_logger(__name__)

#: Fragments that identify a vision-capable model in the provider's model list.
VISION_MODEL_MARKERS = ("vision", "llama-4", "scout", "pixtral", "gemma-3")
#: Hard ceiling for an image handed to a provider, whatever the upload limit is.
MAX_IMAGE_BYTES = 20 * 1024 * 1024
#: Stored when an image contains no readable text. This is a valid, non-failure
#: outcome: the document is Ready and nothing is written to the index.
NO_TEXT_NOTE = "No readable text found"

VISION_UNAVAILABLE = "Image reading isn't available right now."
UNREADABLE_IMAGE = "Couldn't read this image."


class ImageOcrError(Exception):
    """Image text extraction failed for a reason worth showing the user."""


class VisionUnavailableError(ImageOcrError):
    """No configured image-text provider can run."""


class ImageTooLargeError(ImageOcrError):
    """The image exceeds the maximum size a provider accepts."""


@dataclass(frozen=True)
class PreparedImage:
    """A verified, normalised image ready for OCR or a vision API."""

    filename: str
    image: Any  # PIL.Image.Image
    #: Media type of ``data_url_bytes``. Prepared images are always re-encoded
    #: as PNG, so a vision payload never lies about its content.
    mime_type: str
    #: Downscaled RGB copy encoded for a vision API.
    data_url_bytes: bytes

    @property
    def width(self) -> int:
        return int(self.image.width)

    @property
    def height(self) -> int:
        return int(self.image.height)

    def data_url(self) -> str:
        return f"data:{self.mime_type};base64,{base64.b64encode(self.data_url_bytes).decode()}"


@dataclass(frozen=True)
class ImageReadResult:
    """What the provider chain produced for one image."""

    #: Text for indexing (OCR text, or the description when that is all there is).
    text: str
    #: Short visual description, when a vision model produced one.
    description: str | None = None
    #: Which provider answered.
    provider: str | None = None
    #: Mean confidence of the OCR lines, when local OCR ran.
    mean_confidence: float | None = None
    #: Set when the image simply has no readable text (not a failure).
    note: str | None = None

    @property
    def has_text(self) -> bool:
        return bool(self.text.strip())


# --------------------------------------------------------------------------- #
# Image preparation
# --------------------------------------------------------------------------- #

#: Prepared images are re-encoded as PNG before being sent to a vision model,
#: so the payload media type is always PNG regardless of the upload's format.
PREPARED_MIME_TYPE = "image/png"


def _pil() -> tuple[Any, Any]:
    """Import Pillow lazily; it is required for every provider."""
    try:
        import PIL.Image
        import PIL.ImageOps
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise ImageOcrError(UNREADABLE_IMAGE) from exc
    return PIL.Image, PIL.ImageOps


def prepare_image(data: bytes, filename: str, *, max_side: int | None = None) -> PreparedImage:
    """Validate, orient, clean and downscale an image before any provider runs.

    Raises ``ImageTooLargeError`` for an oversized file and ``ImageOcrError``
    when the bytes are not a readable image.
    """
    if not data:
        raise ImageOcrError(UNREADABLE_IMAGE)
    if len(data) > MAX_IMAGE_BYTES:
        raise ImageTooLargeError(f"File too large (max {MAX_IMAGE_BYTES // (1024 * 1024)} MB)")

    pil_image, pil_ops = _pil()
    try:
        with pil_image.open(io.BytesIO(data)) as opened:
            # Honour EXIF orientation, then drop every metadata block.
            oriented = pil_ops.exif_transpose(opened) or opened
            cleaned = pil_image.new("RGB", oriented.size)
            cleaned.paste(oriented.convert("RGB"), (0, 0))
    except ImageOcrError:
        raise
    except Exception as exc:  # noqa: BLE001 - unreadable image is user-visible
        log.warning("image_prepare_failed", filename=filename, exc_info=True)
        raise ImageOcrError(UNREADABLE_IMAGE) from exc

    limit = max_side if max_side and max_side > 0 else settings.ocr_max_side_px
    longest = max(cleaned.width, cleaned.height)
    if longest > limit:
        ratio = limit / longest
        cleaned = cleaned.resize(
            (max(1, int(cleaned.width * ratio)), max(1, int(cleaned.height * ratio))),
            pil_image.Resampling.LANCZOS,
        )

    buffer = io.BytesIO()
    cleaned.save(buffer, format="PNG")
    return PreparedImage(
        filename=filename,
        image=cleaned,
        mime_type=PREPARED_MIME_TYPE,
        data_url_bytes=buffer.getvalue(),
    )


# --------------------------------------------------------------------------- #
# Provider: Groq vision
# --------------------------------------------------------------------------- #


def _groq_client(api_key: str) -> Any:
    from groq import Groq

    return Groq(api_key=api_key, timeout=60.0)


def groq_api_key() -> str | None:
    """Return the configured Groq API key.

    Settings are read first so a ``.env`` file counts; the process environment is
    the fallback. Reading only ``os.environ`` is what previously made every
    image fail with "Image reading isn't available right now".
    """
    key = (settings.groq_api_key or "").strip()
    return key or None


def resolve_vision_model(api_key: str | None = None) -> str | None:
    """Return an available vision-capable model id, or None when there is none.

    ``VISION_MODEL`` wins when set. Otherwise the account's model list is
    inspected once per process; nothing is guessed from memory.
    """
    configured = (settings.vision_model or "").strip()
    if configured:
        return configured
    return _detect_vision_model(api_key)


@functools.lru_cache(maxsize=4)
def _detect_vision_model(api_key: str | None) -> str | None:
    key = api_key or groq_api_key()
    if not key:
        log.info("vision_model_unavailable", reason="missing_api_key")
        return None
    try:
        models = [model.id for model in _groq_client(key).models.list().data]
    except Exception as exc:  # noqa: BLE001 - availability probe must never raise
        log.warning("vision_model_probe_failed", exc_info=True, error_type=type(exc).__name__)
        return None
    lowered = {model_id.lower(): model_id for model_id in models}
    for marker in VISION_MODEL_MARKERS:
        for model_id, original in lowered.items():
            if marker in model_id:
                log.info("vision_model_detected", model=original)
                return original
    log.info("vision_model_unavailable", available_models=len(models))
    return None


def _groq_vision(prepared: PreparedImage, api_key: str | None = None) -> ImageReadResult:
    """Describe the image and transcribe its text with a vision model."""
    key = api_key or groq_api_key()
    if not key:
        raise VisionUnavailableError(VISION_UNAVAILABLE)

    model = resolve_vision_model(key)
    if not model:
        raise VisionUnavailableError(VISION_UNAVAILABLE)

    try:
        response = _groq_client(key).chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Transcribe every piece of readable text in this image, in "
                                "reading order. If the image contains no text, reply with the "
                                "single line DESCRIPTION: <a short description of the image>. "
                                "Output nothing else."
                            ),
                        },
                        {"type": "image_url", "image_url": {"url": prepared.data_url()}},
                    ],
                }
            ],
            temperature=0.0,
            max_tokens=2048,
        )
        content = (response.choices[0].message.content or "").strip()
    except Exception as exc:  # noqa: BLE001 - reported as a readable reason
        log.warning("image_vision_request_failed", model=model, exc_info=True)
        raise ImageOcrError(UNREADABLE_IMAGE) from exc

    if not content:
        return ImageReadResult(text="", provider="groq", note=NO_TEXT_NOTE)
    if content.upper().startswith("DESCRIPTION:"):
        description = content.split(":", 1)[1].strip()
        return ImageReadResult(text=description, description=description, provider="groq")
    return ImageReadResult(text=content, provider="groq")


# --------------------------------------------------------------------------- #
# Provider: local RapidOCR
# --------------------------------------------------------------------------- #

_engine_lock = threading.Lock()
_engine: Any | None = None


def _rapidocr_engine() -> Any:
    """Return the process-wide RapidOCR engine, creating it on first use.

    The engine is never built at import time and never per request.
    """
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                from rapidocr_onnxruntime import RapidOCR

                _engine = RapidOCR()
    return _engine


def reset_rapidocr_engine() -> None:
    """Drop the cached engine (tests and explicit reconfiguration)."""
    global _engine
    with _engine_lock:
        _engine = None


def _ocr_lines(result: Any) -> list[tuple[str, float]]:
    """Normalise RapidOCR output into ``(text, confidence)`` lines."""
    if result is None:
        return []
    # RapidOCR >= 1.4 may return an object exposing .txts/.scores.
    texts = getattr(result, "txts", None)
    scores = getattr(result, "scores", None)
    if texts is not None and scores is not None:
        return [
            (str(text), float(score))
            for text, score in zip(texts, scores, strict=False)
            if str(text).strip()
        ]
    lines: list[tuple[str, float]] = []
    for entry in result or []:
        try:
            text, score = entry[1], float(entry[2])
        except (IndexError, TypeError, ValueError):
            continue
        if str(text).strip():
            lines.append((str(text), score))
    return lines


def _rapidocr_read(prepared: PreparedImage) -> ImageReadResult:
    """Run local OCR and return the text in reading order with its confidence."""
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - numpy ships with chromadb
        raise VisionUnavailableError(VISION_UNAVAILABLE) from exc

    engine = _rapidocr_engine()
    try:
        outcome = engine(np.array(prepared.image))
    except Exception as exc:  # noqa: BLE001 - reported as a readable reason
        log.warning("image_local_ocr_failed", exc_info=True, error_type=type(exc).__name__)
        raise ImageOcrError(UNREADABLE_IMAGE) from exc

    raw = outcome[0] if isinstance(outcome, tuple) else outcome
    lines = _ocr_lines(raw)
    if not lines:
        return ImageReadResult(text="", provider="rapidocr", note=NO_TEXT_NOTE)
    text = "\n".join(line for line, _ in lines)
    confidence = sum(score for _, score in lines) / len(lines)
    return ImageReadResult(
        text=text,
        provider="rapidocr",
        mean_confidence=round(confidence, 4),
    )


# --------------------------------------------------------------------------- #
# Provider chain
# --------------------------------------------------------------------------- #

# Providers are looked up through thin wrappers so the module-level provider
# functions stay replaceable (tests, alternative implementations).
_PROVIDERS: dict[str, Any] = {
    "groq": lambda prepared: _groq_vision(prepared),
    "rapidocr": lambda prepared: _rapidocr_read(prepared),
}


def _run_in_thread(func: Any, *args: Any) -> Any:
    """Run blocking OCR work off the event loop.

    Outside an event loop the work is dispatched with ``asyncio.to_thread``.
    Inside one (an async caller) the function is called directly, because a
    nested event loop cannot be started; async callers should use
    :func:`aread_image`.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(asyncio.to_thread(func, *args))
    return func(*args)


def read_image(
    data: bytes,
    filename: str,
    *,
    provider_order: list[str] | None = None,
    max_side: int | None = None,
) -> ImageReadResult:
    """Extract text from an image, trying each configured provider in order.

    Returns an empty-text result (a note, not an error) when the image holds no
    readable text. Raises ``ImageOcrError`` only when every provider failed.
    """
    if not data:
        raise ImageOcrError(UNREADABLE_IMAGE)

    prepared = prepare_image(data, filename, max_side=max_side)
    order = provider_order if provider_order is not None else settings.vision_providers
    if not order:
        raise VisionUnavailableError(VISION_UNAVAILABLE)

    failures: list[str] = []
    empty: ImageReadResult | None = None
    for name in order:
        provider = _PROVIDERS.get(name)
        if provider is None:
            log.warning("vision_provider_unknown", provider=name)
            continue
        try:
            result = _run_in_thread(provider, prepared)
        except VisionUnavailableError as exc:
            failures.append(f"{name}:unavailable")
            log.info("vision_provider_unavailable", provider=name, reason=str(exc))
            continue
        except ImageOcrError as exc:
            failures.append(f"{name}:{type(exc).__name__}")
            log.warning("vision_provider_failed", provider=name, exc_info=True)
            continue
        if result.has_text:
            return result
        # Keep searching: a later provider may still find text.
        empty = empty or result
        failures.append(f"{name}:empty")

    if empty is not None:
        return empty
    if all(reason.endswith("unavailable") for reason in failures):
        raise VisionUnavailableError(VISION_UNAVAILABLE)
    raise ImageOcrError(UNREADABLE_IMAGE)


async def aread_image(
    data: bytes,
    filename: str,
    *,
    provider_order: list[str] | None = None,
    max_side: int | None = None,
) -> ImageReadResult:
    """Async wrapper around :func:`read_image` that runs blocking OCR in a thread."""
    return await asyncio.to_thread(
        read_image, data, filename, provider_order=provider_order, max_side=max_side
    )


def load_image_document(data: bytes, filename: str, api_key: str | None = None) -> str:
    """Return the text of an image, suitable for chunking.

    Kept as the single string entry point used by the loader. Raises
    ``ImageOcrError``; an image without text returns an empty string, which the
    loader turns into a Ready result with an empty-text note.
    """
    return read_image(data, filename).text
