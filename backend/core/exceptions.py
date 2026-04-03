"""Domain-specific exceptions for ContractGuard backend."""

from __future__ import annotations

from pathlib import Path


class ContractGuardError(Exception):
    """Base exception for domain-level ContractGuard failures."""


class ContractNotFoundError(ContractGuardError):
    """Raised when a contract_id does not exist in storage."""

    def __init__(self, contract_id: str) -> None:
        self.contract_id = contract_id
        super().__init__(f"Unknown contract_id '{contract_id}'. Upload the contract first.")


class ContractParsingError(ContractGuardError):
    """Base exception for contract parsing/extraction failures."""


class UploadValidationError(ContractParsingError):
    """Base exception for upload metadata/content validation failures."""


class UploadTooLargeError(UploadValidationError):
    """Raised when an uploaded file exceeds configured size limits."""

    def __init__(self, *, max_bytes: int, actual_bytes: int) -> None:
        self.max_bytes = max_bytes
        self.actual_bytes = actual_bytes
        super().__init__(
            f"Uploaded file is too large ({actual_bytes} bytes). "
            f"Maximum allowed size is {max_bytes} bytes."
        )


class UnsupportedContentTypeError(UploadValidationError):
    """Raised when uploaded content-type does not match the file extension policy."""

    def __init__(self, *, content_type: str, extension: str) -> None:
        self.content_type = content_type
        self.extension = extension
        super().__init__(
            f"Unsupported content-type '{content_type}' for '{extension}' uploads."
        )


class InvalidFileSignatureError(UploadValidationError):
    """Raised when payload magic bytes do not match the declared file type."""

    def __init__(self, *, filename: str, expected_type: str) -> None:
        self.filename = filename
        self.expected_type = expected_type
        super().__init__(
            f"Uploaded file signature is invalid for {expected_type.upper()} file: {filename}"
        )


class ContractFileNotFoundError(ContractParsingError):
    """Raised when a source contract file path does not exist."""

    def __init__(self, file_path: str | Path) -> None:
        resolved = str(file_path)
        self.file_path = resolved
        super().__init__(f"Input file does not exist: {resolved}")


class UnsupportedContractFormatError(ContractParsingError):
    """Raised when the contract file extension is not supported."""

    def __init__(self, extension: str) -> None:
        self.extension = extension
        super().__init__(f"Unsupported file type: {extension}. Only PDF and DOCX files are supported")


class ContractExtractionError(ContractParsingError):
    """Raised when parsing fails for a supported file type."""

    def __init__(self, filename: str, file_kind: str) -> None:
        self.filename = filename
        self.file_kind = file_kind
        super().__init__(f"Failed to parse {file_kind} file: {filename}")


class EmptyContractTextError(ContractParsingError):
    """Raised when parsing succeeds structurally but no usable text is extracted."""

    def __init__(self, filename: str | None = None) -> None:
        self.filename = filename
        if filename:
            super().__init__(f"Could not extract text from contract file: {filename}")
        else:
            super().__init__("Could not extract text from contract")


class ContractStorageError(ContractGuardError):
    """Raised when temporary upload storage operations fail."""

    def __init__(self, filename: str) -> None:
        self.filename = filename
        super().__init__(f"Could not stage uploaded file for parsing: {filename}")


class IndexingQueueError(ContractGuardError):
    """Base exception for async indexing queue workflow failures."""


class IndexingQueueFullError(IndexingQueueError):
    """Raised when indexing queue cannot accept additional jobs."""

    def __init__(self, max_size: int) -> None:
        self.max_size = max_size
        super().__init__(f"Indexing queue is full (max size: {max_size}). Try again shortly.")


class IndexingInProgressError(IndexingQueueError):
    """Raised when user action requires ready index but indexing is still in progress."""

    def __init__(self, contract_id: str) -> None:
        self.contract_id = contract_id
        super().__init__(f"Indexing is still processing for contract_id '{contract_id}'.")


class IndexingFailedError(IndexingQueueError):
    """Raised when indexing failed for a contract and cannot serve semantic queries."""

    def __init__(self, contract_id: str, reason: str | None = None) -> None:
        self.contract_id = contract_id
        self.reason = reason
        detail = (
            f"Indexing failed for contract_id '{contract_id}': {reason}"
            if reason
            else f"Indexing failed for contract_id '{contract_id}'."
        )
        super().__init__(detail)


__all__ = [
    "ContractExtractionError",
    "ContractFileNotFoundError",
    "ContractGuardError",
    "ContractNotFoundError",
    "ContractParsingError",
    "ContractStorageError",
    "EmptyContractTextError",
    "IndexingFailedError",
    "IndexingInProgressError",
    "IndexingQueueError",
    "IndexingQueueFullError",
    "InvalidFileSignatureError",
    "UnsupportedContentTypeError",
    "UnsupportedContractFormatError",
    "UploadTooLargeError",
    "UploadValidationError",
]
