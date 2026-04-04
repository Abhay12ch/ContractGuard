"""Centralized application settings for ContractGuard."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _to_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _normalize_log_level(value: str | None, default: str = "INFO") -> str:
    allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
    if value is None:
        return default
    normalized = value.strip().upper()
    if normalized in allowed:
        return normalized
    return default


def _normalize_url(value: str | None, default: str) -> str:
    if value is None:
        return default
    normalized = value.strip().rstrip("/")
    if not normalized:
        return default
    return normalized


@dataclass(frozen=True)
class Settings:
    app_name: str = "ContractGuard API"
    log_level: str = _normalize_log_level(
        os.getenv("LOG_LEVEL"),
        default="INFO",
    )
    precompute_embeddings_on_upload: bool = _to_bool(
        os.getenv("PRECOMPUTE_EMBEDDINGS_ON_UPLOAD"),
        default=False,
    )
    prewarm_embedder_on_startup: bool = _to_bool(
        os.getenv("PREWARM_EMBEDDER_ON_STARTUP"),
        default=False,
    )
    async_indexing_enabled: bool = _to_bool(
        os.getenv("ASYNC_INDEXING_ENABLED"),
        default=True,
    )
    indexing_queue_max_size: int = max(
        1,
        _to_int(os.getenv("INDEXING_QUEUE_MAX_SIZE"), default=256),
    )
    upload_max_bytes: int = max(
        1,
        _to_int(os.getenv("UPLOAD_MAX_BYTES"), default=5_242_880),
    )
    ocr_enabled: bool = _to_bool(os.getenv("OCR_ENABLED"), default=False)
    ollama_base_url: str = _normalize_url(
        os.getenv("OLLAMA_BASE_URL"),
        default="http://127.0.0.1:11434",
    )
    ollama_ocr_model: str = (
        os.getenv("OLLAMA_OCR_MODEL", "glm-ocr:latest").strip() or "glm-ocr:latest"
    )
    ocr_timeout_seconds: int = max(
        5,
        _to_int(os.getenv("OCR_TIMEOUT_SECONDS"), default=120),
    )
    ocr_pdf_min_chars: int = max(
        1,
        _to_int(os.getenv("OCR_PDF_MIN_CHARS"), default=80),
    )
    ocr_pdf_max_pages: int = max(
        1,
        _to_int(os.getenv("OCR_PDF_MAX_PAGES"), default=25),
    )
    summary_min_chars: int = 100
    summary_max_chars: int = _to_int(os.getenv("SUMMARY_MAX_CHARS"), default=2000)


settings = Settings()


__all__ = ["Settings", "settings"]
