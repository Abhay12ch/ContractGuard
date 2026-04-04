"""Shared Gemini generative-AI client for ContractGuard.

Centralises API-key lookup, SDK import, and model selection so every
module (summariser, analyser, comparator, QA) uses consistent logic.
"""

from __future__ import annotations

import importlib
import logging
import os
from functools import lru_cache
from typing import Any

logger = logging.getLogger("contractguard.gemini")


@lru_cache(maxsize=1)
def _load_genai_module() -> Any | None:
    try:
        return importlib.import_module("google.genai")
    except ImportError:
        logger.debug("google-genai SDK not installed — Gemini features disabled.")
        return None


def gemini_api_key() -> str:
    return os.getenv("GEMINI_API_KEY", "").strip()


def gemini_available() -> bool:
    return bool(gemini_api_key()) and _load_genai_module() is not None


@lru_cache(maxsize=1)
def _get_client(api_key: str) -> Any:
    genai = _load_genai_module()
    if genai is None:
        raise RuntimeError("google-genai SDK is not installed.")
    return genai.Client(api_key=api_key)


def get_gemini_client() -> Any:
    """Return a cached google.genai.Client, ready to use."""
    key = gemini_api_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not configured.")
    return _get_client(key)


def default_model() -> str:
    return os.getenv("GEMINI_MODEL", "gemini-2.5-pro").strip() or "gemini-2.5-pro"


def generate_text(prompt: str, *, model: str | None = None) -> str:
    """Send a single-turn text generation request and return the response text.

    Returns an empty string on any failure so callers can fall back gracefully.
    """
    try:
        client = get_gemini_client()
        model_name = model or default_model()
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
        )
        return (getattr(response, "text", "") or "").strip()
    except Exception as exc:
        logger.warning("Gemini generate_text failed: %s", exc)
        return ""


def generate_json(prompt: str, *, model: str | None = None) -> str:
    """Send a text generation request expecting JSON output.

    Wraps the prompt with instructions to return valid JSON and uses
    response_mime_type where supported.
    """
    try:
        client = get_gemini_client()
        model_name = model or default_model()

        genai = _load_genai_module()
        types_mod = importlib.import_module("google.genai.types")

        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types_mod.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )
        return (getattr(response, "text", "") or "").strip()
    except Exception as exc:
        logger.warning("Gemini generate_json failed: %s", exc)
        return ""


__all__ = [
    "default_model",
    "gemini_available",
    "generate_json",
    "generate_text",
    "get_gemini_client",
]
