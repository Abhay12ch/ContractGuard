"""OCR helpers for scanned contracts and image uploads via Ollama."""

from __future__ import annotations

import base64
import logging

import requests

from ..core.config import settings


logger = logging.getLogger("contractguard.ocr")

_DEFAULT_PROMPT = (
    "Extract all readable text from this document image in natural reading order. "
    "Return plain text only. Do not add commentary."
)


def ocr_image_bytes(image_bytes: bytes, *, prompt: str | None = None) -> str:
    """Run OCR on image bytes using Ollama chat vision API.

    Returns an empty string when OCR is disabled, unavailable, or yields no text.
    """
    if not settings.ocr_enabled:
        return ""
    if not image_bytes:
        return ""

    endpoint = f"{settings.ollama_base_url}/api/chat"
    encoded = base64.b64encode(image_bytes).decode("ascii")
    payload = {
        "model": settings.ollama_ocr_model,
        "messages": [
            {
                "role": "user",
                "content": (prompt or _DEFAULT_PROMPT),
                "images": [encoded],
            }
        ],
        "stream": False,
    }

    try:
        response = requests.post(
            endpoint,
            json=payload,
            timeout=settings.ocr_timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        logger.warning("Ollama OCR request failed: %s", exc)
        return ""
    except (TypeError, ValueError) as exc:
        logger.warning("Ollama OCR returned invalid payload: %s", exc)
        return ""

    message = data.get("message", {})
    if not isinstance(message, dict):
        return ""
    content = str(message.get("content", "")).strip()
    return content


__all__ = ["ocr_image_bytes"]
