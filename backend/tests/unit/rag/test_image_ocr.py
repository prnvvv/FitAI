"""Image text extraction: preparation, provider order and local OCR.

These tests render images with Pillow, so they never need a real photo, a Groq
key or a network call.
"""

from __future__ import annotations

import io

import pytest

from app.core.config import settings
from app.rag import image_ocr
from app.rag.image_ocr import (
    NO_TEXT_NOTE,
    ImageOcrError,
    ImageReadResult,
    ImageTooLargeError,
    VisionUnavailableError,
    prepare_image,
    read_image,
)

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def render_text_image(text: str = "BENCH PRESS 3 SETS", size: tuple[int, int] = (900, 240)):
    """Return JPEG bytes of a white image with ``text`` drawn on it."""
    from PIL import Image, ImageDraw

    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    draw.text((30, 60), text, fill="black")
    draw.text((30, 140), "target weight 80 kg", fill="black")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=95)
    return buffer.getvalue()


def encode(image_format: str, size: tuple[int, int] = (120, 60)) -> bytes:
    """Return encoded bytes for a blank image in ``image_format``."""
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", size, "white").save(buffer, format=image_format)
    return buffer.getvalue()


# --------------------------------------------------------------------------- #
# Local OCR
# --------------------------------------------------------------------------- #


def test_local_ocr_reads_rendered_text(tmp_path) -> None:
    data = render_text_image("SQUAT 5X3")
    path = tmp_path / "workout (copy).jpeg"
    path.write_bytes(data)

    result = read_image(data, path.name, provider_order=["rapidocr"])

    assert result.has_text
    assert "SQUAT" in result.text.upper()
    assert result.provider == "rapidocr"
    assert result.mean_confidence is not None
    assert result.mean_confidence > 0


@pytest.mark.parametrize("filename", ["a.jpg", "a.jpeg", "b.png", "c.webp", "D.JPEG", "E.JPG"])
def test_every_supported_image_extension_reaches_ocr(filename: str) -> None:
    from PIL import Image

    buffer = io.BytesIO()
    source = Image.open(io.BytesIO(render_text_image("DEADLIFT")))
    fmt = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "webp": "WEBP"}[
        filename.rsplit(".", 1)[1].lower()
    ]
    source.save(buffer, format=fmt)
    data = buffer.getvalue()

    result = read_image(data, filename, provider_order=["rapidocr"])

    assert "DEADLIFT" in result.text.upper()


def test_filename_with_spaces_and_parentheses_is_supported() -> None:
    data = render_text_image("LUNGE")
    result = read_image(data, "my plan (week 2).jpeg", provider_order=["rapidocr"])
    assert "LUNGE" in result.text.upper()


def test_blank_image_is_an_empty_result_not_a_failure() -> None:
    result = read_image(encode("PNG"), "blank.png", provider_order=["rapidocr"])
    assert result.has_text is False
    assert result.note == NO_TEXT_NOTE
    assert result.text == ""


def test_empty_result_keeps_searching_other_providers(monkeypatch) -> None:
    monkeypatch.setattr(
        image_ocr,
        "_groq_vision",
        lambda *a, **k: ImageReadResult(text="from groq", provider="groq"),
    )
    result = read_image(encode("PNG"), "x.png", provider_order=["rapidocr", "groq"])
    assert result.provider == "groq"
    assert result.text == "from groq"


# --------------------------------------------------------------------------- #
# Provider chain
# --------------------------------------------------------------------------- #


def test_groq_is_skipped_when_no_api_key_is_configured(monkeypatch) -> None:
    monkeypatch.setattr(settings, "groq_api_key", None)
    monkeypatch.setattr(settings, "vision_model", None)
    image_ocr._detect_vision_model.cache_clear()
    calls: list[str] = []

    def _fake_groq(*_args, **_kwargs):
        calls.append("groq")
        raise VisionUnavailableError(image_ocr.VISION_UNAVAILABLE)

    monkeypatch.setattr(image_ocr, "_groq_vision", _fake_groq)

    result = read_image(render_text_image("ROW"), "row.jpg")

    assert result.provider == "rapidocr"
    assert calls == ["groq"]


def test_groq_failure_falls_back_to_local_ocr(monkeypatch) -> None:
    monkeypatch.setattr(settings, "groq_api_key", None)
    monkeypatch.setattr(settings, "vision_model", None)
    image_ocr._detect_vision_model.cache_clear()

    def _boom(*_args, **_kwargs):
        raise ImageOcrError(image_ocr.UNREADABLE_IMAGE)

    monkeypatch.setattr(image_ocr, "_groq_vision", _boom)

    result = read_image(render_text_image("PULL UP"), "pullup.png")

    assert result.provider == "rapidocr"
    assert "PULL UP" in result.text.upper()


def test_all_providers_unavailable_raises_readable_error(monkeypatch) -> None:
    monkeypatch.setattr(settings, "groq_api_key", None)
    image_ocr._detect_vision_model.cache_clear()

    def _unavailable(*_args, **_kwargs):
        raise VisionUnavailableError(image_ocr.VISION_UNAVAILABLE)

    monkeypatch.setattr(image_ocr, "_groq_vision", _unavailable)

    with pytest.raises(VisionUnavailableError) as excinfo:
        read_image(encode("PNG"), "x.png", provider_order=["groq"])

    assert str(excinfo.value) == image_ocr.VISION_UNAVAILABLE


def test_error_message_never_contains_a_traceback_or_file_content(monkeypatch) -> None:
    def _boom(*_args, **_kwargs):
        raise ImageOcrError(f"boom {image_ocr.UNREADABLE_IMAGE}")

    monkeypatch.setattr(image_ocr, "_groq_vision", _boom)
    monkeypatch.setattr(image_ocr, "_rapidocr_read", _boom)

    with pytest.raises(ImageOcrError) as excinfo:
        read_image(render_text_image("SECRET"), "secret.jpg")

    message = str(excinfo.value)
    assert "Traceback" not in message
    assert "SECRET" not in message


def test_configured_vision_model_wins_over_auto_detection(monkeypatch) -> None:
    monkeypatch.setattr(settings, "vision_model", "configured-model")
    image_ocr._detect_vision_model.cache_clear()
    assert image_ocr.resolve_vision_model("key") == "configured-model"


def test_api_key_is_read_from_settings_not_only_the_process_env(monkeypatch) -> None:
    monkeypatch.setattr(settings, "groq_api_key", "key-from-env-file")
    assert image_ocr.groq_api_key() == "key-from-env-file"


# --------------------------------------------------------------------------- #
# Image preparation
# --------------------------------------------------------------------------- #


def test_prepare_downscales_long_edge_and_strips_metadata() -> None:
    prepared = prepare_image(render_text_image(size=(3000, 1000)), "big.jpg", max_side=800)
    assert max(prepared.width, prepared.height) == 800
    assert prepared.image.mode == "RGB"
    assert prepared.data_url_bytes[:8] == b"\x89PNG\r\n\x1a\n"


def test_prepare_applies_exif_orientation() -> None:
    from PIL import Image

    image = Image.new("RGB", (80, 40), "white")
    exif = image.getexif()
    exif[0x0112] = 6  # rotate 90 degrees clockwise
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif)

    prepared = prepare_image(buffer.getvalue(), "rotated.jpg")

    assert prepared.height >= prepared.width


def test_oversized_file_is_rejected_with_a_readable_reason() -> None:
    with pytest.raises(ImageTooLargeError) as excinfo:
        prepare_image(b"\xff\xd8\xff" + b"0" * (image_ocr.MAX_IMAGE_BYTES + 1), "huge.jpg")
    assert "too large" in str(excinfo.value).lower()


def test_non_image_bytes_are_rejected() -> None:
    with pytest.raises(ImageOcrError) as excinfo:
        prepare_image(b"not an image at all", "fake.jpg")
    assert str(excinfo.value) == image_ocr.UNREADABLE_IMAGE


def test_vision_payload_is_always_png_encoded() -> None:
    """The encoded payload and its declared media type must always agree."""
    for name, fmt in (("a.png", "PNG"), ("b.webp", "WEBP"), ("c.JPEG", "JPEG")):
        prepared = prepare_image(encode(fmt), name)
        assert prepared.mime_type == "image/png"
        assert prepared.data_url_bytes[:8] == PNG_MAGIC


# --------------------------------------------------------------------------- #
# Engine lifecycle and thread offloading
# --------------------------------------------------------------------------- #


def test_engine_is_created_once_and_reused(monkeypatch) -> None:
    created: list[int] = []

    class _FakeEngine:
        def __call__(self, _array):
            created.append(1)
            return ([[None, "LINE", 0.9]], 0.1)

    class _FakeRapidOCR:
        def __init__(self) -> None:
            created.append(0)

        __call__ = _FakeEngine.__call__

    import rapidocr_onnxruntime

    monkeypatch.setattr(rapidocr_onnxruntime, "RapidOCR", _FakeRapidOCR)
    image_ocr.reset_rapidocr_engine()

    first = image_ocr._rapidocr_engine()
    second = image_ocr._rapidocr_engine()

    assert first is second
    assert created == [0]

    result = image_ocr._rapidocr_read(prepare_image(encode("PNG"), "a.png"))
    assert result.text == "LINE"
    assert result.mean_confidence == 0.9
    assert created == [0, 1]

    image_ocr.reset_rapidocr_engine()


@pytest.mark.asyncio
async def test_async_api_reads_an_image(monkeypatch) -> None:
    monkeypatch.setattr(
        image_ocr,
        "_rapidocr_read",
        lambda prepared: ImageReadResult(text="THREADED", provider="rapidocr"),
    )
    result = await image_ocr.aread_image(encode("PNG"), "a.png", provider_order=["rapidocr"])
    assert result.text == "THREADED"
