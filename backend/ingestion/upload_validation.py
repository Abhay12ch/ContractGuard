"""Upload metadata and payload validation utilities."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from ..core.exceptions import (
    InvalidFileSignatureError,
    UnsupportedContentTypeError,
    UnsupportedContractFormatError,
    UploadTooLargeError,
)


_ALLOWED_CONTENT_TYPES_BY_EXTENSION = {
    ".pdf": {"application/pdf"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    },
}


def _normalize_content_type(content_type: str | None) -> str:
    if not content_type:
        return ""
    return content_type.split(";", maxsplit=1)[0].strip().lower()


def _looks_like_pdf(contents: bytes) -> bool:
    return contents.startswith(b"%PDF-")


def _looks_like_docx(contents: bytes) -> bool:
    if not contents.startswith(b"PK\x03\x04"):
        return False

    try:
        with ZipFile(BytesIO(contents)) as archive:
            names = set(archive.namelist())
    except (BadZipFile, OSError, ValueError):
        return False

    return "[Content_Types].xml" in names and any(name.startswith("word/") for name in names)


def validate_upload_payload(
    *,
    filename: str,
    content_type: str | None,
    contents: bytes,
    max_bytes: int,
) -> None:
    """Enforce strict upload limits and file-type validation policy."""
    actual_size = len(contents)
    if actual_size > max_bytes:
        raise UploadTooLargeError(max_bytes=max_bytes, actual_bytes=actual_size)

    suffix = Path(filename).suffix.lower()
    if suffix not in _ALLOWED_CONTENT_TYPES_BY_EXTENSION:
        raise UnsupportedContractFormatError(suffix)

    normalized_content_type = _normalize_content_type(content_type)
    allowed_content_types = _ALLOWED_CONTENT_TYPES_BY_EXTENSION[suffix]
    if normalized_content_type not in allowed_content_types:
        raise UnsupportedContentTypeError(
            content_type=normalized_content_type or "missing",
            extension=suffix,
        )

    signature_valid = _looks_like_pdf(contents) if suffix == ".pdf" else _looks_like_docx(contents)
    if not signature_valid:
        expected = "pdf" if suffix == ".pdf" else "docx"
        raise InvalidFileSignatureError(filename=filename, expected_type=expected)


__all__ = ["validate_upload_payload"]
