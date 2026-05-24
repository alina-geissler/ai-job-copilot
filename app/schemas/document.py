"""Define Pydantic schemas for document upload form submissions.

Describe the validated data structures used when a user submits a document
upload form.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.core.enums import DocumentType


class DocumentUploadForm(BaseModel):
    """Represent validated form input for uploading a document.

    The file itself is received as a FastAPI ``UploadFile`` alongside this
    schema; this schema covers only the non-file form fields.
    """

    document_type: DocumentType = DocumentType.CV
