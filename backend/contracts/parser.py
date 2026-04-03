"""Document parsing utilities for PDF/DOCX contracts.

Uses PyPDF (pypdf) for PDFs and python-docx for Word files.
"""

from pathlib import Path
from typing import List

import pypdf
from pypdf.errors import EmptyFileError, PdfReadError
from docx import Document
from docx.opc.exceptions import PackageNotFoundError

from ..core.exceptions import (
    ContractExtractionError,
    ContractFileNotFoundError,
    UnsupportedContractFormatError,
)


def _extract_pdf(path: Path) -> str:
    reader = pypdf.PdfReader(str(path))
    texts: List[str] = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        texts.append(page_text)
    return "\n".join(texts)


def _extract_docx(path: Path) -> str:
    doc = Document(str(path))
    paras = [p.text for p in doc.paragraphs if p.text]
    return "\n".join(paras)


def extract_text_from_file(file_path: str) -> str:
    """Extract raw text from a PDF or DOCX file.

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

    raise UnsupportedContractFormatError(suffix)


__all__ = ["extract_text_from_file"]
