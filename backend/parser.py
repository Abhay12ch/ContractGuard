"""Document parsing utilities for PDF/DOCX contracts.

Uses PyPDF (pypdf) for PDFs and python-docx for Word files.
"""

from pathlib import Path
from typing import List

import pypdf
from docx import Document


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

    Raises FileNotFoundError if the file is missing, and ValueError for
    unsupported extensions.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(file_path)

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix == ".docx":
        return _extract_docx(path)

    raise ValueError(f"Unsupported file type: {suffix}")
