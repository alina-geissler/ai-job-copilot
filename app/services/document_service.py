"""Service functions for document upload and lifecycle management.

Coordinate storage operations, CRUD persistence, and background text
extraction. Own all transaction boundaries for document write operations.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app.core.enums import DocumentProcessingStatus, DocumentType, ExtractionMethod
from app.db.session import SessionLocal
from app.crud.document import (
    create_document,
    delete_document,
    get_document_by_id_for_user,
    get_document_by_type_for_user,
    list_documents_for_user,
    update_document_extraction_result,
    update_document_name,
    update_document_processing_status,
)
from app.utils.document_ui import DOCUMENT_TYPE_LABELS
from app.models.document import Document
from app.crud.profile_information import upsert_profile
from app.services.document_extraction import extract_markdown_from_pdf
from app.services.document_storage import delete_document as storage_delete
from app.services.document_storage import download_document, upload_document
from app.services.profile_extraction import extract_profile_from_cv_text

logger = logging.getLogger(__name__)

_EVAL_LOG_PATH = "evals/profile_extractions.jsonl"


def _log_extraction(
    *,
    cv_text: str,
    profile: "CandidateProfile",
    prompt_version: str,
) -> None:
    """Append one eval record to the local JSONL log.

    Never raises — a logging failure must not interrupt the extraction flow.
    The CV text is not stored; only a short hash prefix for traceability.

    :param cv_text: Raw CV text (used only for hashing).
    :param profile: Successfully parsed CandidateProfile.
    :param prompt_version: Active prompt version string (e.g. ``"v1"``).
    """
    try:
        from app.core.config import settings as _settings
        os.makedirs("evals", exist_ok=True)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "prompt_version": prompt_version,
            "model": _settings.llm_model,
            "cv_sha256": hashlib.sha256(cv_text.encode()).hexdigest()[:16],
            "output": profile.model_dump(),
        }
        with open(_EVAL_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        logger.warning("Failed to write eval log entry.", exc_info=True)


def build_storage_key(*, user_id: int, original_filename: str) -> str:
    """Generate a unique storage key for a user's document.

    :param user_id: Identifier of the owning user.
    :param original_filename: Sanitized original filename from the browser.
    :return: Storage key in the form ``documents/{user_id}/{uuid}_{stem}.pdf``.
    """
    stem = Path(original_filename).stem[:64]
    return f"documents/{user_id}/{uuid4().hex}_{stem}.pdf"


def upload_user_document(
    db: Session,
    *,
    background_tasks: BackgroundTasks,
    user_id: int,
    document_type: DocumentType,
    original_filename: str,
    file_bytes: bytes,
    mime_type: str,
) -> Document:
    """Upload a document to storage and create its database record.

    Upload the file bytes to object storage first. If storage fails, raise
    without creating a database record. On success, create the record with
    PENDING status and enqueue the extraction background task.

    :param db: Active database session.
    :param background_tasks: FastAPI background task queue.
    :param user_id: Identifier of the owning user.
    :param document_type: Type discriminator for the document.
    :param original_filename: Sanitized original filename from the browser.
    :param file_bytes: Raw file content to store and extract from.
    :param mime_type: Verified MIME type of the file.
    :return: Newly created document record.
    :raises RuntimeError: If the storage upload fails.
    """
    existing = get_document_by_type_for_user(db, user_id=user_id, document_type=document_type)

    storage_key = build_storage_key(user_id=user_id, original_filename=original_filename)
    upload_document(storage_key=storage_key, file_bytes=file_bytes, mime_type=mime_type)

    if existing is not None:
        storage_delete(storage_key=existing.storage_key)
        delete_document(db, document=existing)

    document = create_document(
        db,
        user_id=user_id,
        document_type=document_type,
        document_name=DOCUMENT_TYPE_LABELS[document_type],
        original_filename=original_filename,
        storage_key=storage_key,
        mime_type=mime_type,
        file_size_bytes=len(file_bytes),
    )
    db.commit()

    background_tasks.add_task(_run_extraction_task, document_id=document.id)

    return document


def delete_user_document(
    db: Session,
    *,
    document_id: int,
    user_id: int,
) -> bool:
    """Delete a document from storage and remove its database record.

    Delete from object storage first (logging warnings on failure without
    raising), then always delete the database record to avoid orphaned rows.

    :param db: Active database session.
    :param document_id: Identifier of the document to delete.
    :param user_id: Identifier of the owning user.
    :return: ``True`` when the document was found and deleted, otherwise ``False``.
    """
    document = get_document_by_id_for_user(db, document_id=document_id, user_id=user_id)
    if document is None:
        return False

    storage_delete(storage_key=document.storage_key)

    try:
        delete_document(db, document=document)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return True


def update_user_document_name(
    db: Session,
    *,
    document_id: int,
    user_id: int,
    name: str,
) -> bool:
    """Update the display name of a user-owned document.

    :param db: Active database session.
    :param document_id: Identifier of the document to rename.
    :param user_id: Identifier of the owning user.
    :param name: New display name (already validated as non-blank by the caller).
    :return: ``True`` when the document was found and updated, otherwise ``False``.
    """
    document = get_document_by_id_for_user(db, document_id=document_id, user_id=user_id)
    if document is None:
        return False

    update_document_name(db, document=document, name=name)
    db.commit()
    return True


def list_user_documents(db: Session, *, user_id: int) -> list[Document]:
    """Return all documents for one user ordered by newest first.

    :param db: Active database session.
    :param user_id: Identifier of the owning user.
    :return: List of documents.
    """
    return list_documents_for_user(db, user_id=user_id)


def _run_extraction_task(*, document_id: int) -> None:
    """Background task: download and extract Markdown from an uploaded document.

    Open a new database session (separate from the request session),
    update the processing status to PROCESSING, download the file from
    object storage, run pymupdf4llm extraction, and persist the result.
    Mark the document as FAILED on any exception.

    :param document_id: Identifier of the document to process.
    """
    db = SessionLocal()
    try:
        document = db.get(Document, document_id)
        if document is None:
            logger.error("Extraction task: document %d not found.", document_id)
            return

        update_document_processing_status(
            db, document=document, status=DocumentProcessingStatus.PROCESSING
        )
        db.commit()

        try:
            file_bytes = download_document(storage_key=document.storage_key)
            extracted_text = extract_markdown_from_pdf(file_bytes)
            update_document_extraction_result(
                db,
                document=document,
                status=DocumentProcessingStatus.COMPLETED,
                extracted_text=extracted_text,
                extraction_method=ExtractionMethod.MARKDOWN,
                extraction_error=None,
            )
            db.commit()

        except Exception as exc:
            logger.exception("Markdown extraction failed for document %d.", document_id)
            update_document_extraction_result(
                db,
                document=document,
                status=DocumentProcessingStatus.FAILED,
                extracted_text=None,
                extraction_method=None,
                extraction_error=str(exc),
            )
            db.commit()
            return

        try:
            profile, prompt_version = extract_profile_from_cv_text(extracted_text)
            _log_extraction(cv_text=extracted_text, profile=profile, prompt_version=prompt_version)
            upsert_profile(db, user_id=document.user_id, data={
                **profile.model_dump(),
                "extraction_error": None,
            })
        except Exception as profile_exc:
            logger.exception("Profile extraction failed for document %d.", document_id)
            upsert_profile(db, user_id=document.user_id, data={
                "extraction_error": str(profile_exc),
            })

        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Extraction task encountered an unhandled error for document %d.", document_id)
    finally:
        db.close()


def _run_profile_only_task(*, user_id: int) -> None:
    """Background task: re-run profile extraction for a user who already has a COMPLETED CV.

    Open a new database session, fetch the stored CV text, call the LLM, and
    persist the result. Saves an extraction_error on any failure so the UI can
    surface it.

    :param user_id: Identifier of the owning user.
    """
    from app.crud.document import get_document_by_type_for_user
    from app.core.enums import DocumentType

    db = SessionLocal()
    try:
        cv_doc = get_document_by_type_for_user(db, user_id=user_id, document_type=DocumentType.CV)
        if cv_doc is None or cv_doc.extracted_text is None:
            logger.error("Profile retry: no completed CV text found for user %d.", user_id)
            return

        try:
            profile, prompt_version = extract_profile_from_cv_text(cv_doc.extracted_text)
            _log_extraction(cv_text=cv_doc.extracted_text, profile=profile, prompt_version=prompt_version)
            upsert_profile(db, user_id=user_id, data={
                **profile.model_dump(),
                "extraction_error": None,
            })
        except Exception as profile_exc:
            logger.exception("Profile retry extraction failed for user %d.", user_id)
            upsert_profile(db, user_id=user_id, data={
                "extraction_error": str(profile_exc),
            })

        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Profile retry task encountered an unhandled error for user %d.", user_id)
    finally:
        db.close()


def retry_profile_extraction(
    db: Session,
    *,
    background_tasks: BackgroundTasks,
    user_id: int,
) -> bool:
    """Delete any existing profile and re-enqueue profile extraction from the CV text.

    Checks that a COMPLETED CV with extracted text exists before proceeding.
    Deletes the existing profile row so the profile page shows the in-progress
    spinner while the background task runs.

    :param db: Active database session.
    :param background_tasks: FastAPI background task queue.
    :param user_id: Identifier of the owning user.
    :return: True if a completed CV exists and the task was enqueued, False otherwise.
    """
    from app.crud.document import get_document_by_type_for_user
    from app.crud.profile_information import get_profile_for_user, delete_profile
    from app.core.enums import DocumentType, DocumentProcessingStatus

    cv_doc = get_document_by_type_for_user(db, user_id=user_id, document_type=DocumentType.CV)
    if cv_doc is None or cv_doc.processing_status != DocumentProcessingStatus.COMPLETED:
        return False

    existing_profile = get_profile_for_user(db, user_id=user_id)
    if existing_profile is not None:
        delete_profile(db, profile=existing_profile)
        db.commit()

    background_tasks.add_task(_run_profile_only_task, user_id=user_id)
    return True
