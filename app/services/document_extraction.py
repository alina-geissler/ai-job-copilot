"""Extract text from PDF documents as Markdown using pymupdf4llm.

Try pymupdf4llm first for layout-aware Markdown. When it returns empty
(e.g. certain font encodings or CVs with complex sidebar layouts that
MuPDF's higher-level text pipeline skips), fall back to PyMuPDF's own
plain-text extraction, which reads the same underlying MuPDF engine at
a lower level and reliably extracts embedded text.
"""

from __future__ import annotations

import logging

import fitz
import pymupdf4llm

logger = logging.getLogger(__name__)


def extract_markdown_from_pdf(file_bytes: bytes) -> str:
    """Extract text from a PDF as a Markdown string.

    Open the document in memory, attempt pymupdf4llm layout-aware
    Markdown extraction, and fall back to PyMuPDF plain-text extraction
    if the result is empty.

    :param file_bytes: Raw PDF file content.
    :return: Extracted text (Markdown or plain) as a single string.
    :raises RuntimeError: If both extraction methods fail entirely.
    """
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    try:
        md = pymupdf4llm.to_markdown(doc)
        if md.strip():
            return md
        logger.warning(
            "pymupdf4llm returned empty text; falling back to PyMuPDF plain-text extraction."
        )
    except Exception:
        logger.exception(
            "pymupdf4llm extraction failed; falling back to PyMuPDF plain-text extraction."
        )
    finally:
        doc.close()

    doc = fitz.open(stream=file_bytes, filetype="pdf")
    try:
        parts = [page.get_text().strip() for page in doc if page.get_text().strip()]
        if not parts:
            raise RuntimeError("No extractable text found in PDF.")
        return "\n\n".join(parts)
    finally:
        doc.close()
