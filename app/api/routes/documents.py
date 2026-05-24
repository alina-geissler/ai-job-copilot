"""Define browser routes for the documents feature.

Render the document list page and handle upload and delete actions for
user-owned documents.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.enums import DocumentType
from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.templates import build_feedback_query, get_base_template_context
from app.models.user import User
from app.crud.document import get_document_by_id_for_user, get_document_by_type_for_user
from app.services.document_service import (
    delete_user_document,
    list_user_documents,
    update_user_document_name,
    upload_user_document,
)
from app.services.document_storage import generate_presigned_url
from app.utils.document_ui import (
    DOCUMENT_STATUS_CLASSES,
    DOCUMENT_STATUS_LABELS,
    DOCUMENT_TYPE_LABELS,
    EXTRACTION_METHOD_LABELS,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])
templates = Jinja2Templates(directory="templates")

_ALLOWED_MIME_TYPES = {"application/pdf"}


def _serialize_document(doc: Any) -> dict[str, Any]:
    """Serialize one document ORM object into template-friendly data.

    :param doc: Document ORM object.
    :return: Dictionary with UI-ready document data.
    """
    return {
        "id": doc.id,
        "document_type": doc.document_type,
        "document_type_label": DOCUMENT_TYPE_LABELS.get(doc.document_type, doc.document_type.value),
        "document_name": doc.document_name,
        "original_filename": doc.original_filename,
        "file_size_bytes": doc.file_size_bytes,
        "processing_status": doc.processing_status,
        "processing_status_label": DOCUMENT_STATUS_LABELS.get(
            doc.processing_status, doc.processing_status.value
        ),
        "processing_status_css_class": DOCUMENT_STATUS_CLASSES.get(
            doc.processing_status, ""
        ),
        "extraction_method": doc.extraction_method,
        "extraction_method_label": (
            EXTRACTION_METHOD_LABELS.get(doc.extraction_method)
            if doc.extraction_method
            else None
        ),
        "extracted_text": doc.extracted_text,
        "extraction_error": doc.extraction_error,
        "created_at": doc.created_at,
    }


def _get_mime_type(file_bytes: bytes, fallback: str = "application/octet-stream") -> str:
    """Detect the MIME type of file bytes using python-magic.

    Fall back to ``fallback`` when python-magic is unavailable or cannot load
    its native library (common on Windows without libmagic DLLs).

    :param file_bytes: Raw file content to inspect.
    :param fallback: MIME type to return when detection is unavailable.
    :return: Detected MIME type string.
    """
    try:
        import magic
        return magic.from_buffer(file_bytes, mime=True)
    except (ImportError, OSError):
        logger.warning(
            "python-magic is unavailable; falling back to browser-reported MIME type %r. "
            "Install python-magic-bin for reliable file type detection on Windows.",
            fallback,
        )
        return fallback


@router.get("", response_class=HTMLResponse, name="render_documents_page")
def render_documents_page(
        request: Request,
        current_user: Annotated[User, Depends(get_current_user)],
        db: Annotated[Session, Depends(get_db)],
) -> HTMLResponse:
    """Render the documents overview page.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :return: Rendered documents page.
    """
    documents = list_user_documents(db, user_id=current_user.id)
    serialized = [_serialize_document(doc) for doc in documents]
    has_existing_cv = get_document_by_type_for_user(
        db, user_id=current_user.id, document_type=DocumentType.CV
    ) is not None

    return templates.TemplateResponse(
        request=request,
        name="documents.html",
        context={
            **get_base_template_context(request),
            "current_user": current_user,
            "documents": serialized,
            "document_types": [(t.value, DOCUMENT_TYPE_LABELS[t]) for t in DocumentType],
            "has_existing_cv": has_existing_cv,
        },
    )


@router.post("/upload", response_class=HTMLResponse, name="upload_document_action")
def upload_document_route(
        request: Request,
        current_user: Annotated[User, Depends(get_current_user)],
        db: Annotated[Session, Depends(get_db)],
        background_tasks: BackgroundTasks,
        file: Annotated[UploadFile, ...],
        document_type: Annotated[DocumentType, Form()] = DocumentType.CV,
) -> RedirectResponse:
    """Upload a document file and enqueue text extraction.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :param background_tasks: FastAPI background task queue.
    :param file: Uploaded file from the multipart form.
    :param document_type: Document type submitted via the form.
    :return: Redirect response to the documents page.
    """
    documents_url = str(request.url_for("render_documents_page"))

    file_bytes = file.file.read()

    if len(file_bytes) > settings.max_upload_size_bytes:
        max_mb = settings.max_upload_size_bytes // (1024 * 1024)
        query_string = build_feedback_query(
            message=f"Die Datei ist zu groß. Maximal erlaubt sind {max_mb} MB.",
            message_type="error",
        )
        return RedirectResponse(url=f"{documents_url}?{query_string}", status_code=303)

    if len(file_bytes) == 0:
        query_string = build_feedback_query(
            message="Die hochgeladene Datei ist leer.",
            message_type="error",
        )
        return RedirectResponse(url=f"{documents_url}?{query_string}", status_code=303)

    mime_type = _get_mime_type(file_bytes, fallback=file.content_type or "application/octet-stream")
    if mime_type not in _ALLOWED_MIME_TYPES:
        query_string = build_feedback_query(
            message="Nur PDF-Dateien sind erlaubt.",
            message_type="error",
        )
        return RedirectResponse(url=f"{documents_url}?{query_string}", status_code=303)

    original_filename = Path(file.filename or "document.pdf").name

    try:
        upload_user_document(
            db,
            background_tasks=background_tasks,
            user_id=current_user.id,
            document_type=document_type,
            original_filename=original_filename,
            file_bytes=file_bytes,
            mime_type=mime_type,
        )
    except RuntimeError:
        logger.exception("Document upload failed for user %d.", current_user.id)
        query_string = build_feedback_query(
            message="Beim Hochladen des Dokuments ist ein Fehler aufgetreten. Bitte versuche es erneut.",
            message_type="error",
        )
        return RedirectResponse(url=f"{documents_url}?{query_string}", status_code=303)

    query_string = build_feedback_query(
        message="Dokument hochgeladen. Textextraktion läuft im Hintergrund…",
        message_type="success",
    )
    return RedirectResponse(url=f"{documents_url}?{query_string}", status_code=303)


@router.get("/{doc_id}/view", name="render_document_view_action")
def render_document_view_action(
        request: Request,
        current_user: Annotated[User, Depends(get_current_user)],
        db: Annotated[Session, Depends(get_db)],
        doc_id: int,
) -> RedirectResponse:
    """Redirect to a temporary presigned URL for viewing an uploaded document.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :param doc_id: Identifier of the document to view.
    :return: Temporary redirect to the presigned storage URL.
    """
    documents_url = str(request.url_for("render_documents_page"))
    document = get_document_by_id_for_user(db, document_id=doc_id, user_id=current_user.id)

    if document is None:
        query_string = build_feedback_query(
            message="Dokument nicht gefunden.",
            message_type="error",
        )
        return RedirectResponse(url=f"{documents_url}?{query_string}", status_code=303)

    try:
        presigned_url = generate_presigned_url(storage_key=document.storage_key, expires_in=900)
    except RuntimeError:
        logger.exception("Presigned URL generation failed for document %d.", doc_id)
        query_string = build_feedback_query(
            message="Das Dokument konnte nicht geöffnet werden. Bitte versuche es erneut.",
            message_type="error",
        )
        return RedirectResponse(url=f"{documents_url}?{query_string}", status_code=303)

    return RedirectResponse(url=presigned_url, status_code=302)


@router.post("/{doc_id}/name", name="update_document_name_action")
def update_document_name_route(
        request: Request,
        current_user: Annotated[User, Depends(get_current_user)],
        db: Annotated[Session, Depends(get_db)],
        doc_id: int,
        name: Annotated[str, Form()],
) -> RedirectResponse:
    """Update the display name of a document.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :param doc_id: Identifier of the document to rename.
    :param name: New display name submitted via the form.
    :return: Redirect response to the documents page.
    """
    documents_url = str(request.url_for("render_documents_page"))

    stripped = name.strip()
    if not stripped:
        query_string = build_feedback_query(
            message="Der Dokumentname darf nicht leer sein.",
            message_type="error",
        )
        return RedirectResponse(url=f"{documents_url}?{query_string}", status_code=303)

    was_updated = update_user_document_name(
        db, document_id=doc_id, user_id=current_user.id, name=stripped
    )

    if was_updated:
        message = "Dokumentname gespeichert."
        message_type = "success"
    else:
        message = "Dokument nicht gefunden."
        message_type = "error"

    query_string = build_feedback_query(message=message, message_type=message_type)
    return RedirectResponse(url=f"{documents_url}?{query_string}", status_code=303)


@router.post("/{document_id}/delete", response_class=HTMLResponse, name="delete_document_action")
def delete_document_route(
        request: Request,
        current_user: Annotated[User, Depends(get_current_user)],
        db: Annotated[Session, Depends(get_db)],
        document_id: int,
) -> RedirectResponse:
    """Delete one document from storage and the database.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :param document_id: Identifier of the document to delete.
    :return: Redirect response to the documents page.
    """
    documents_url = str(request.url_for("render_documents_page"))

    was_deleted = delete_user_document(db, document_id=document_id, user_id=current_user.id)

    if was_deleted:
        message = "Dokument erfolgreich gelöscht."
        message_type = "success"
    else:
        message = "Dokument nicht gefunden."
        message_type = "error"

    query_string = build_feedback_query(message=message, message_type=message_type)
    return RedirectResponse(url=f"{documents_url}?{query_string}", status_code=303)
