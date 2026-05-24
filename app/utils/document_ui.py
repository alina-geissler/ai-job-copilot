"""Define UI helper metadata for document rendering.

Provide one central place for UI-specific document metadata such as
translated labels and CSS classes for document types and processing statuses.
"""

from __future__ import annotations

from app.core.enums import DocumentProcessingStatus, DocumentType, ExtractionMethod

DOCUMENT_TYPE_LABELS: dict[DocumentType, str] = {
    DocumentType.CV: "Lebenslauf",
    DocumentType.COVER_LETTER: "Anschreiben",
}

DOCUMENT_STATUS_LABELS: dict[DocumentProcessingStatus, str] = {
    DocumentProcessingStatus.PENDING: "Ausstehend",
    DocumentProcessingStatus.PROCESSING: "Wird verarbeitet…",
    DocumentProcessingStatus.COMPLETED: "Abgeschlossen",
    DocumentProcessingStatus.FAILED: "Fehlgeschlagen",
}

DOCUMENT_STATUS_CLASSES: dict[DocumentProcessingStatus, str] = {
    DocumentProcessingStatus.PENDING: "status--pending",
    DocumentProcessingStatus.PROCESSING: "status--processing",
    DocumentProcessingStatus.COMPLETED: "status--completed",
    DocumentProcessingStatus.FAILED: "status--failed",
}

EXTRACTION_METHOD_LABELS: dict[ExtractionMethod, str] = {
    ExtractionMethod.EMBEDDED_TEXT: "Eingebetteter Text",
    ExtractionMethod.OCR: "OCR",
    ExtractionMethod.MARKDOWN: "Markdown (pymupdf4llm)",
}
