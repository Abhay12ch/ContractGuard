"""Document parsing utilities for contract uploads.

Uses PyPDF (pypdf) for digital PDFs, Gemini Multimodal Vision / Ollama OCR for
scanned/image-based PDFs, python-docx for Word files, and direct vision OCR for images.
"""

import logging
from pathlib import Path
from typing import List

import pypdf
from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from pypdf.errors import EmptyFileError, PdfReadError

from .ocr import ocr_image_bytes, ocr_pdf_bytes
from ..core.config import settings
from ..core.exceptions import (
    ContractExtractionError,
    ContractFileNotFoundError,
    UnsupportedContractFormatError,
)

logger = logging.getLogger("contractguard.parser")

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
_MIME_MAP = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def _supported_formats() -> tuple[str, ...]:
    return ("PDF", "DOCX", "PNG", "JPG/JPEG", "WEBP")


def _largest_embedded_image(page: object) -> bytes:
    """Return the largest embedded image found on a PDF page."""
    images = getattr(page, "images", None)
    if not images:
        return b""

    largest = b""
    try:
        for image in images:
            data = getattr(image, "data", b"")
            if isinstance(data, bytearray):
                data = bytes(data)
            if isinstance(data, bytes) and len(data) > len(largest):
                largest = data
    except Exception as exc:
        logger.debug("Failed extracting embedded image from page: %s", exc)
    return largest


def _extract_pdf(path: Path) -> str:
    """Extract text from a PDF file using PyPDF with automatic Gemini/Ollama OCR fallback for scanned docs."""
    text_chunks: List[str] = []
    ocr_candidates: List[tuple[int, bytes]] = []

    try:
        reader = pypdf.PdfReader(str(path))
        for page_number, page in enumerate(reader.pages, start=1):
            try:
                page_text = (page.extract_text() or "").strip()
                if page_text:
                    text_chunks.append(page_text)
            except Exception as exc:
                logger.debug("PyPDF page text extraction failed for page %d: %s", page_number, exc)

            if page_number <= settings.ocr_pdf_max_pages:
                try:
                    image_bytes = _largest_embedded_image(page)
                    if image_bytes:
                        ocr_candidates.append((page_number, image_bytes))
                except Exception:
                    pass
    except Exception as exc:
        logger.warning("PyPDF structure read failed for %s: %s (falling back to direct PDF OCR)", path.name, exc)

    extracted_text = "\n\n".join(text_chunks).strip()
    
    # If standard text extraction yielded sufficient text, return it
    if extracted_text and len(extracted_text) >= settings.ocr_pdf_min_chars:
        return extracted_text

    # Scanned or image-based PDF detected — run Multimodal OCR
    logger.info("Scanned/image PDF detected (%s), running Gemini Document OCR...", path.name)
    
    # 1. First try full-document PDF OCR via Gemini
    try:
        pdf_bytes = path.read_bytes()
        ocr_result = ocr_pdf_bytes(pdf_bytes)
        if ocr_result and len(ocr_result.strip()) >= 10:
            logger.info("Direct PDF OCR succeeded for %s (%d chars)", path.name, len(ocr_result))
            if extracted_text:
                return f"{extracted_text}\n\n{ocr_result.strip()}"
            return ocr_result.strip()
    except Exception as exc:
        logger.warning("Direct PDF OCR attempt failed: %s", exc)

    # 2. Fall back to per-page embedded image OCR
    if ocr_candidates:
        ocr_chunks: List[str] = []
        for page_number, image_bytes in ocr_candidates:
            try:
                ocr_text = ocr_image_bytes(image_bytes)
                if ocr_text.strip():
                    ocr_chunks.append(f"[Page {page_number}]\n{ocr_text.strip()}")
            except Exception as exc:
                logger.debug("Page %d image OCR failed: %s", page_number, exc)

        if ocr_chunks:
            combined = "\n\n".join(ocr_chunks).strip()
            if extracted_text:
                return f"{extracted_text}\n\n{combined}"
            return combined

    return extracted_text


def _extract_docx(path: Path) -> str:
    try:
        doc = Document(str(path))
        paras = [p.text for p in doc.paragraphs if p.text]
        return "\n".join(paras)
    except Exception as exc:
        raise ContractExtractionError(path.name, "DOCX") from exc


def _extract_image(path: Path) -> str:
    image_bytes = path.read_bytes()
    suffix = path.suffix.lower()
    mime_type = _MIME_MAP.get(suffix, "image/png")
    return ocr_image_bytes(image_bytes, mime_type=mime_type).strip()


def extract_text_from_file(file_path: str) -> str:
    """Extract raw text from a supported contract upload.

    Raises dedicated ContractGuard domain exceptions for missing files,
    unsupported formats, and parser failures.
    """
    path = Path(file_path)
    if not path.exists():
        raise ContractFileNotFoundError(path)

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            return _extract_pdf(path)
        except Exception as exc:
            raise ContractExtractionError(path.name, "PDF") from exc
    if suffix == ".docx":
        try:
            return _extract_docx(path)
        except Exception as exc:
            raise ContractExtractionError(path.name, "DOCX") from exc
    if suffix in _IMAGE_SUFFIXES:
        try:
            return _extract_image(path)
        except Exception as exc:
            raise ContractExtractionError(path.name, "IMAGE") from exc

    raise UnsupportedContractFormatError(
        suffix,
        supported_formats=_supported_formats(),
    )


__all__ = ["extract_text_from_file"]
