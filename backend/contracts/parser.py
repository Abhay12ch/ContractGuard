"""Document parsing utilities for contract uploads.

Uses PyPDF (pypdf) for PDFs, python-docx for Word files, and optional
Ollama OCR for image-based documents when enabled.
"""

import logging
from pathlib import Path
from typing import List

import pypdf
from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from pypdf.errors import EmptyFileError, PdfReadError

from .ocr import ocr_image_bytes
from ..core.config import settings
from ..core.exceptions import (
    ContractExtractionError,
    ContractFileNotFoundError,
    UnsupportedContractFormatError,
)


logger = logging.getLogger("contractguard.parser")

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def _supported_formats() -> tuple[str, ...]:
    if settings.ocr_enabled:
        return ("PDF", "DOCX", "PNG", "JPG/JPEG", "WEBP")
    return ("PDF", "DOCX")


def _largest_embedded_image(page: object) -> bytes:
    """Return the largest embedded image found on a PDF page."""
    images = getattr(page, "images", None)
    if not images:
        return b""

    largest = b""
    for image in images:
        data = getattr(image, "data", b"")
        if isinstance(data, bytearray):
            data = bytes(data)
        if isinstance(data, bytes) and len(data) > len(largest):
            largest = data
    return largest


def _extract_pdf(path: Path) -> str:
    reader = pypdf.PdfReader(str(path))
    text_chunks: List[str] = []
    ocr_candidates: List[tuple[int, bytes]] = []

    for page_number, page in enumerate(reader.pages, start=1):
        page_text = (page.extract_text() or "").strip()
        if page_text:
            text_chunks.append(page_text)

        if (
            settings.ocr_enabled
            and page_number <= settings.ocr_pdf_max_pages
        ):
            image_bytes = _largest_embedded_image(page)
            if image_bytes:
                ocr_candidates.append((page_number, image_bytes))

    extracted_text = "\n".join(text_chunks).strip()
    if extracted_text and len(extracted_text) >= settings.ocr_pdf_min_chars:
        return extracted_text
    if not settings.ocr_enabled or not ocr_candidates:
        return extracted_text

    logger.info("Falling back to OCR for likely scanned PDF: %s", path.name)
    ocr_chunks: List[str] = []
    for page_number, image_bytes in ocr_candidates:
        ocr_text = ocr_image_bytes(image_bytes)
        if ocr_text.strip():
            ocr_chunks.append(f"[Page {page_number}]\n{ocr_text.strip()}")

    if not ocr_chunks:
        return extracted_text

    ocr_text = "\n\n".join(ocr_chunks).strip()
    if extracted_text:
        return f"{extracted_text}\n\n{ocr_text}"
    return ocr_text


def _extract_docx(path: Path) -> str:
    doc = Document(str(path))
    paras = [p.text for p in doc.paragraphs if p.text]
    return "\n".join(paras)


def _extract_image(path: Path) -> str:
    image_bytes = path.read_bytes()
    return ocr_image_bytes(image_bytes).strip()


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
        except (OSError, ValueError, PdfReadError, EmptyFileError) as exc:
            raise ContractExtractionError(path.name, "PDF") from exc
    if suffix == ".docx":
        try:
            return _extract_docx(path)
        except (OSError, ValueError, PackageNotFoundError) as exc:
            raise ContractExtractionError(path.name, "DOCX") from exc
    if suffix in _IMAGE_SUFFIXES:
        if not settings.ocr_enabled:
            raise UnsupportedContractFormatError(
                suffix,
                supported_formats=_supported_formats(),
            )
        try:
            return _extract_image(path)
        except OSError as exc:
            raise ContractExtractionError(path.name, "IMAGE") from exc

    raise UnsupportedContractFormatError(
        suffix,
        supported_formats=_supported_formats(),
    )


__all__ = ["extract_text_from_file"]
