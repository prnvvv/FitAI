"""STT start-up work (local Granite provider only)."""

from __future__ import annotations

import threading

from app.core.logging import get_logger

logger = get_logger(__name__)


def warm_stt_model() -> None:
    """Start loading the Granite STT model in the background if eager load is on.

    Loading ~900 MB of weights can take several seconds; doing it lazily on the
    first request would make the first dictation feel broken. A background
    thread keeps startup fast and never blocks health checks.
    """
    from app.stt.speech_service import get_service

    service = get_service()
    if not service.eager_load:
        logger.info("stt_warmup_skipped", reason="STT_EAGER_LOAD is disabled")
        return
    if service.status.state != "idle":
        logger.info("stt_warmup_skipped", reason=f"status is {service.status.state}")
        return

    def _warm() -> None:
        try:
            service.warmup()
            logger.info(
                "stt_warmup_complete",
                state=service.status.state,
                device=service.status.device,
                load_seconds=service.status.load_seconds,
            )
        except Exception as exc:  # noqa: BLE001 - warmup must not crash startup
            logger.error("stt_warmup_failed", error=str(exc))

    logger.info(
        "stt_warmup_started", model_id=service.model_id, device_request=service.device_request
    )
    threading.Thread(target=_warm, name="stt-warmup", daemon=True).start()
