"""HTTP-level error translation for ContractGuard domain exceptions."""

from __future__ import annotations

from fastapi import HTTPException, status

from ..core.exceptions import (
    ContractGuardError,
    ContractNotFoundError,
    ContractParsingError,
    ContractStorageError,
    IndexingFailedError,
    IndexingInProgressError,
    IndexingQueueFullError,
    InvalidFileSignatureError,
    UnsupportedContentTypeError,
    UploadTooLargeError,
)


def to_http_exception(exc: ContractGuardError) -> HTTPException:
    """Map domain exceptions to stable FastAPI HTTP exceptions."""
    if isinstance(exc, ContractNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    if isinstance(exc, UploadTooLargeError):
        return HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc))

    if isinstance(exc, UnsupportedContentTypeError):
        return HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc))

    if isinstance(exc, InvalidFileSignatureError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if isinstance(exc, IndexingInProgressError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    if isinstance(exc, IndexingFailedError):
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))

    if isinstance(exc, IndexingQueueFullError):
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))

    if isinstance(exc, ContractParsingError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if isinstance(exc, ContractStorageError):
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not process uploaded file",
        )

    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unexpected backend error",
    )


__all__ = ["to_http_exception"]
