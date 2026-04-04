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


_BASE_ALLOWED_CONTENT_TYPES_BY_EXTENSION = {
    ".pdf": {"application/pdf"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    },
}

_IMAGE_CONTENT_TYPES_BY_EXTENSION = {
    ".png": {"image/png"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".webp": {"image/webp"},
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


def _looks_like_png(contents: bytes) -> bool:
    return contents.startswith(b"\x89PNG\r\n\x1a\n")


def _looks_like_jpeg(contents: bytes) -> bool:
    return contents.startswith(b"\xff\xd8\xff")


def _looks_like_webp(contents: bytes) -> bool:
    return (
        len(contents) >= 12
        and contents.startswith(b"RIFF")
        and contents[8:12] == b"WEBP"
    )


def _supported_format_names(*, allow_images: bool) -> tuple[str, ...]:
    if allow_images:
        return ("PDF", "DOCX", "PNG", "JPG/JPEG", "WEBP")
    return ("PDF", "DOCX")


def validate_upload_payload(
    *,
    filename: str,
    content_type: str | None,
    contents: bytes,
    max_bytes: int,
    allow_images: bool = False,
) -> None:
    """Enforce strict upload limits and file-type validation policy."""
    actual_size = len(contents)
    if actual_size > max_bytes:
        raise UploadTooLargeError(max_bytes=max_bytes, actual_bytes=actual_size)

    allowed_content_types_by_extension = dict(_BASE_ALLOWED_CONTENT_TYPES_BY_EXTENSION)
    if allow_images:
        allowed_content_types_by_extension.update(_IMAGE_CONTENT_TYPES_BY_EXTENSION)

    suffix = Path(filename).suffix.lower()
    if suffix not in allowed_content_types_by_extension:
        raise UnsupportedContractFormatError(
            suffix,
            supported_formats=_supported_format_names(allow_images=allow_images),
        )

    normalized_content_type = _normalize_content_type(content_type)
    allowed_content_types = allowed_content_types_by_extension[suffix]
    if normalized_content_type not in allowed_content_types:
        raise UnsupportedContentTypeError(
            content_type=normalized_content_type or "missing",
            extension=suffix,
        )

    if suffix == ".pdf":
        signature_valid = _looks_like_pdf(contents)
        expected = "pdf"
    elif suffix == ".docx":
        signature_valid = _looks_like_docx(contents)
        expected = "docx"
    elif suffix == ".png":
        signature_valid = _looks_like_png(contents)
        expected = "png"
    elif suffix in {".jpg", ".jpeg"}:
        signature_valid = _looks_like_jpeg(contents)
        expected = "jpeg"
    elif suffix == ".webp":
        signature_valid = _looks_like_webp(contents)
        expected = "webp"
    else:  # pragma: no cover - defensive path (suffix already validated)
        signature_valid = False
        expected = "supported"

    if not signature_valid:
        raise InvalidFileSignatureError(filename=filename, expected_type=expected)


__all__ = ["validate_upload_payload"]
