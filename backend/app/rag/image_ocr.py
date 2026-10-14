"""Extract text from images using a vision-capable Groq model.

The model is never hardcoded: it comes from ``GROQ_VISION_MODEL`` and, when that
is unset, from the model list of the configured Groq account. An account without
a vision-capable model gets an honest, specific failure instead of a generic one.
"""

from __future__ import annotations

import base64
import functools
import logging
import mimetypes
import os
from pathlib import Path

from groq import Groq

log = logging.getLogger(__name__)

#: Model id of a vision-capable model. Leave unset to auto-detect from the account.
VISION_MODEL_ENV = "GROQ_VISION_MODEL"
#: Fragments that identify a vision-capable model in the provider's model list.
VISION_MODEL_MARKERS = ("vision", "llama-4", "scout", "pixtral", "gemma-3")
MAX_IMAGE_BYTES = 20 * 1024 * 1024


class ImageOcrError(Exception):
    """Image text extraction failed."""


class VisionUnavailableError(ImageOcrError):
    """The configured Groq account exposes no vision-capable model."""


def _groq_client(api_key: str) -> Groq:
    return Groq(api_key=api_key, timeout=60.0)


def resolve_vision_model(api_key: str | None = None) -> str | None:
    """Return an available vision-capable model id, or None when there is none.

    ``GROQ_VISION_MODEL`` wins when set. Otherwise the account's model list is
    inspected once per process; nothing is guessed from memory.
    """
    configured = os.getenv(VISION_MODEL_ENV, "").strip()
    if configured:
        return configured
    return _detect_vision_model(api_key)


@functools.lru_cache(maxsize=4)
def _detect_vision_model(api_key: str | None) -> str | None:
    key = api_key or os.getenv("GROQ_API_KEY")
    if not key:
        log.info("vision_model_unavailable reason=missing_api_key")
        return None
    try:
        models = [model.id for model in _groq_client(key).models.list().data]
    except Exception as exc:  # noqa: BLE001 - availability probe must never raise
        log.warning("vision_model_probe_failed", exc_info=True, error_type=type(exc).__name__)
        return None
    for marker in VISION_MODEL_MARKERS:
        for model_id in models:
            if marker in model_id.lower():
                log.info("vision_model_detected", model=model_id)
                return model_id
    log.info("vision_model_unavailable", available_models=len(models))
    return None


def _mime_type(filename: str) -> str:
    guessed = mimetypes.guess_type(filename)[0]
    if guessed and guessed.startswith("image/"):
        return guessed
    ext = Path(filename).suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(ext, "image/jpeg")


def _resize_for_vision(data: bytes) -> bytes:
    """Downscale very large images so vision APIs accept them.

    This is a lightweight best-effort resize. PIL is not a project dependency,
    so if it is unavailable we return the original bytes and let the API reject
    oversized inputs with a clear message.
    """
    try:
        from PIL import Image
    except ImportError:
        return data

    try:
        from io import BytesIO

        img = Image.open(BytesIO(data))
        # Vision models typically accept images up to ~1024-2048 on the long edge.
        max_edge = 1536
        w, h = img.size
        if max(w, h) <= max_edge and len(data) <= MAX_IMAGE_BYTES:
            return data
        ratio = min(max_edge / max(w, h), 1.0)
        new_size = (int(w * ratio), int(h * ratio))
        resized = img.resize(new_size, Image.Resampling.LANCZOS)
        out = BytesIO()
        # Save as JPEG for broad compatibility; convert RGBA/P to RGB.
        if resized.mode in ("RGBA", "P"):
            resized = resized.convert("RGB")
        resized.save(out, format="JPEG", quality=85)
        return out.getvalue()
    except Exception as exc:  # noqa: BLE001
        log.warning("image_resize_failed", error=str(exc))
        return data


def extract_text_from_image(data: bytes, filename: str, api_key: str | None = None) -> str:
    """Return plain text extracted from an image, or raise ImageOcrError."""
    key = api_key or os.getenv("GROQ_API_KEY")
    if not key:
        raise VisionUnavailableError("Image reading isn't available right now.")

    model = resolve_vision_model(key)
    if not model:
        raise VisionUnavailableError("Image reading isn't available right now.")

    if not data:
        raise ImageOcrError("Couldn't read this image.")

    resized = _resize_for_vision(data)
    mime = _mime_type(filename)
    b64 = base64.b64encode(resized).decode("utf-8")
    data_url = f"data:{mime};base64,{b64}"

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
                                "Extract all readable text from this image. "
                                "If there is no text, briefly describe what the image shows. "
                                "Output only the extracted text or description, nothing else."
                            ),
                        },
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            temperature=0.0,
            max_tokens=2048,
        )
    except Exception as exc:  # noqa: BLE001 - reported as a readable reason
        log.warning("image_ocr_request_failed", model=model, exc_info=True)
        raise ImageOcrError("Couldn't read this image.") from exc

    content = response.choices[0].message.content
    return (content or "").strip()


def load_image_document(data: bytes, filename: str, api_key: str | None = None) -> str:
    """Return extracted text from an image, suitable for chunking.

    Raises ``VisionUnavailableError`` when no vision-capable model is available
    and ``ImageOcrError`` when extraction fails or returns nothing usable.
    """
    text = extract_text_from_image(data, filename, api_key=api_key)
    if not text:
        raise ImageOcrError("Couldn't read this image.")
    return text
