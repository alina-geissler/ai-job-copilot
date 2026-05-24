"""CRUD operations for the Document model.

Handle database interactions for creating, reading, updating, and deleting
document records that belong to one authenticated user.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import DocumentProcessingStatus, DocumentType, ExtractionMethod
from app.models.document import Document


def create_document(
    db: Session,
    *,
    user_id: int,
    document_type: DocumentType,
    document_name: str,
    original_filename: str,
    storage_key: str,
    mime_type: str,
    file_size_bytes: int,
) -> Document:
    """Create and flush a new document record with PENDING processing status.

    :param db: Active database session.
    :param user_id: Identifier of the owning user.
    :param document_type: Type discriminator for the document.
    :param document_name: Human-readable display name for the document.
    :param original_filename: Sanitized original filename from the browser.
    :param storage_key: Object storage key for the uploaded file.
    :param mime_type: Verified MIME type of the file.
    :param file_size_bytes: File size in bytes.
    :return: Newly created document record.
    """
    document = Document(
        user_id=user_id,
        document_type=document_type,
        document_name=document_name,
        original_filename=original_filename,
        storage_key=storage_key,
        mime_type=mime_type,
        file_size_bytes=file_size_bytes,
        processing_status=DocumentProcessingStatus.PENDING,
    )
    db.add(document)
    db.flush()
    return document


def get_document_by_type_for_user(
    db: Session,
    *,
    user_id: int,
    document_type: DocumentType,
) -> Document | None:
    """Return the most recent document of a given type for the user.

    :param db: Active database session.
    :param user_id: Identifier of the owning user.
    :param document_type: Document type to look up.
    :return: Most recent matching document or ``None``.
    """
    stmt = (
        select(Document)
        .where(Document.user_id == user_id, Document.document_type == document_type)
        .order_by(Document.created_at.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def get_document_by_id_for_user(
    db: Session,
    *,
    document_id: int,
    user_id: int,
) -> Document | None:
    """Return one document by identifier for the given user.

    :param db: Active database session.
    :param document_id: Identifier of the document.
    :param user_id: Identifier of the owning user.
    :return: Matching document or ``None``.
    """
    stmt = (
        select(Document)
        .where(Document.id == document_id, Document.user_id == user_id)
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def list_documents_for_user(
    db: Session,
    *,
    user_id: int,
) -> list[Document]:
    """Return all documents for one user ordered by newest first.

    :param db: Active database session.
    :param user_id: Identifier of the owning user.
    :return: List of documents.
    """
    stmt = (
        select(Document)
        .where(Document.user_id == user_id)
        .order_by(Document.created_at.desc(), Document.id.desc())
    )
    return list(db.execute(stmt).scalars().all())


def update_document_processing_status(
    db: Session,
    *,
    document: Document,
    status: DocumentProcessingStatus,
) -> Document:
    """Update the processing status of a document.

    :param db: Active database session.
    :param document: Existing document to update.
    :param status: New processing status.
    :return: Updated document.
    """
    document.processing_status = status
    db.add(document)
    return document


def update_document_extraction_result(
    db: Session,
    *,
    document: Document,
    status: DocumentProcessingStatus,
    extracted_text: str | None,
    extraction_method: ExtractionMethod | None,
    extraction_error: str | None,
) -> Document:
    """Persist text extraction results on a document.

    :param db: Active database session.
    :param document: Existing document to update.
    :param status: Final processing status.
    :param extracted_text: Extracted or OCR text, if available.
    :param extraction_method: Method used for extraction.
    :param extraction_error: Error message if extraction failed.
    :return: Updated document.
    """
    document.processing_status = status
    document.extracted_text = extracted_text
    document.extraction_method = extraction_method
    document.extraction_error = extraction_error
    db.add(document)
    return document


def update_document_name(db: Session, *, document: Document, name: str) -> Document:
    """Update the display name of a document.

    :param db: Active database session.
    :param document: Existing document to update.
    :param name: New display name.
    :return: Updated document.
    """
    document.document_name = name
    db.add(document)
    return document


def delete_document(db: Session, *, document: Document) -> None:
    """Delete a document record from the database.

    :param db: Active database session.
    :param document: Existing document to delete.
    """
    db.delete(document)
