"""OCR helpers for scanned contracts and image uploads via Gemini Multimodal Vision and Ollama."""

from __future__ import annotations

import base64
import logging
from typing import Optional

import requests

from .gemini_client import gemini_available, get_gemini_client, default_model
from ..core.config import settings

logger = logging.getLogger("contractguard.ocr")

_DEFAULT_PROMPT = (
    "Extract all readable text, clauses, headings, and numbers from this document in natural reading order. "
    "Return the extracted plain text only. Do not add any conversational commentary or formatting notes."
)


def _ocr_with_gemini(data_bytes: bytes, mime_type: str, prompt: Optional[str] = None) -> str:
    """Extract text from PDF or image bytes using Gemini Multimodal API."""
    if not gemini_available():
        return ""

    try:
        from google.genai import types
        client = get_gemini_client()
        part = types.Part.from_bytes(data=data_bytes, mime_type=mime_type)
        extract_prompt = prompt or _DEFAULT_PROMPT
        response = client.models.generate_content(
            model=default_model(),
            contents=[part, extract_prompt],
        )
        if response and response.text:
            text = response.text.strip()
            if text and text != "[NO_TEXT]" and text != "[EMPTY_DOCUMENT]":
                logger.info("Gemini OCR extracted %d characters (%s)", len(text), mime_type)
                return text
    except Exception as exc:
        logger.warning("Gemini multimodal OCR failed (%s): %s", mime_type, exc)
    return ""


def _ocr_with_ollama(image_bytes: bytes, prompt: Optional[str] = None) -> str:
    """Fallback OCR using local Ollama vision endpoint."""
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
        message = data.get("message", {})
        if isinstance(message, dict):
            return str(message.get("content", "")).strip()
    except Exception as exc:
        logger.debug("Ollama OCR fallback skipped/failed: %s", exc)
    return ""


def ocr_image_bytes(image_bytes: bytes, mime_type: str = "image/png", *, prompt: str | None = None) -> str:
    """Run OCR on image bytes using Gemini Multimodal Vision, falling back to Ollama.

    Returns an empty string when OCR yields no text.
    """
    if not image_bytes:
        return ""

    # 1. Try Gemini Vision (primary, cloud-accelerated)
    text = _ocr_with_gemini(image_bytes, mime_type, prompt)
    if text:
        return text

    # 2. Try Ollama (local fallback)
    text = _ocr_with_ollama(image_bytes, prompt)
    return text


def ocr_pdf_bytes(pdf_bytes: bytes, *, prompt: str | None = None) -> str:
    """Run full-document OCR on PDF bytes using Gemini Multimodal PDF processing.

    Returns extracted text or empty string on failure.
    """
    if not pdf_bytes:
        return ""

    # Try Gemini direct PDF processing
    text = _ocr_with_gemini(pdf_bytes, "application/pdf", prompt)
    return text


__all__ = ["ocr_image_bytes", "ocr_pdf_bytes"]
