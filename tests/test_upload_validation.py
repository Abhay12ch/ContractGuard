"""Upload validation tests for optional image OCR upload support."""

import pytest

from backend.core.exceptions import InvalidFileSignatureError, UnsupportedContractFormatError
from backend.ingestion.upload_validation import validate_upload_payload


def test_upload_allows_png_when_image_uploads_enabled() -> None:
    validate_upload_payload(
        filename="scan.png",
        content_type="image/png",
        contents=b"\x89PNG\r\n\x1a\nfake-bytes",
        max_bytes=1024 * 1024,
        allow_images=True,
    )


def test_upload_rejects_png_when_image_uploads_disabled() -> None:
    with pytest.raises(UnsupportedContractFormatError):
        validate_upload_payload(
            filename="scan.png",
            content_type="image/png",
            contents=b"\x89PNG\r\n\x1a\nfake-bytes",
            max_bytes=1024 * 1024,
            allow_images=False,
        )


def test_upload_rejects_invalid_jpeg_signature() -> None:
    with pytest.raises(InvalidFileSignatureError):
        validate_upload_payload(
            filename="scan.jpg",
            content_type="image/jpeg",
            contents=b"not-a-jpeg",
            max_bytes=1024 * 1024,
            allow_images=True,
        )
