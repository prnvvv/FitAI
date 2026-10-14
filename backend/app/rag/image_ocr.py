"""Extract text from images using a vision-capable Groq model."""

from __future__ import annotations

import base64
import logging
import mimetypes
import os
from pathlib import Path

from groq import Groq

log = logging.getLogger(__name__)

# Prefer a vision-capable Groq model; fall back to the configured model if needed.
VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "llama-3.2-11b-vision-preview")
FALLBACK_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
MAX_IMAGE_BYTES = 20 * 1024 * 1024


class ImageOcrError(Exception):
    """Image text extraction failed."""


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
        raise ImageOcrError("GROQ_API_KEY is not configured; image text extraction is unavailable.")

    if not data:
        raise ImageOcrError("image is empty")

    resized = _resize_for_vision(data)
    mime = _mime_type(filename)
    b64 = base64.b64encode(resized).decode("utf-8")
    data_url = f"data:{mime};base64,{b64}"

    client = Groq(api_key=key, timeout=60.0)
    models_to_try = [VISION_MODEL]
    if VISION_MODEL != FALLBACK_MODEL:
        models_to_try.append(FALLBACK_MODEL)

    last_error: Exception | None = None
    for model in models_to_try:
        try:
            response = client.chat.completions.create(
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
            content = response.choices[0].message.content
            return (content or "").strip()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            log.warning("image_ocr_model_failed", model=model, error=str(exc))
            continue

    raise ImageOcrError(f"Could not extract text from image: {last_error}")


def load_image_document(data: bytes, filename: str, api_key: str | None = None) -> str:
    """Return extracted text from an image, suitable for chunking.

    Raises ImageOcrError when extraction fails or returns nothing usable.
    """
    text = extract_text_from_image(data, filename, api_key=api_key)
    if not text:
        raise ImageOcrError("no readable text found in image")
    return text
