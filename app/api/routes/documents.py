"""Define browser routes for the documents feature.

Render the document list page and handle upload and delete actions for
user-owned documents.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.enums import DocumentProcessingStatus, DocumentType
from app.crud.application_tracker_entry import list_tracker_entries_for_user
from app.crud.cover_letter import get_completed_drafts_for_user, get_saved_cover_letters_for_user
from app.crud.document import get_document_by_id_for_user, get_document_by_type_for_user
from app.crud.job import get_jobs_by_ids
from app.crud.profile_information import get_profile_for_user
from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.templates import build_feedback_query, get_base_template_context
from app.models.user import User
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

_TEMPLATE_LABELS: dict[str, str] = {
    "classic": "Klassisch",
    "modern": "Modern",
    "compact": "Kompakt",
}


def _serialize_cover_letter(cl: Any) -> dict[str, Any]:
    """Serialize one CoverLetter ORM object into template-friendly data.

    :param cl: CoverLetter ORM object.
    :return: Dictionary with UI-ready cover letter data.
    """
    template_val = cl.template.value if cl.template is not None else ""
    return {
        "id": cl.id,
        "document_name": cl.document_name,
        "template": template_val,
        "template_label": _TEMPLATE_LABELS.get(template_val, template_val),
        "is_saved": cl.is_saved,
        "generation_status": cl.generation_status,
        "job_id": cl.job_id,
        "manual_job_posting_id": cl.manual_job_posting_id,
        "created_at": cl.created_at,
    }


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
        job_id: Annotated[int | None, Query()] = None,
) -> HTMLResponse:
    """Render the documents overview page.

    Shows uploaded documents, saved cover letters, and cover letter drafts.
    When ``job_id`` is provided, the cover letter sections are filtered to that
    job and a contextual banner is displayed.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :param job_id: Optional job identifier to filter cover letter sections.
    :return: Rendered documents page.
    """
    documents = list_user_documents(db, user_id=current_user.id)
    serialized = [_serialize_document(doc) for doc in documents]
    cv_doc = get_document_by_type_for_user(db, user_id=current_user.id, document_type=DocumentType.CV)
    has_existing_cv = (
        cv_doc is not None
        and cv_doc.processing_status == DocumentProcessingStatus.COMPLETED
    )
    profile = get_profile_for_user(db, user_id=current_user.id)
    profile_has_error = profile is not None and bool(profile.extraction_error)
    signature_image = profile.signature_image if profile is not None else None
    redirect_to_profile = request.session.get("redirect_to_profile", False)

    saved_cover_letters = [
        _serialize_cover_letter(cl)
        for cl in get_saved_cover_letters_for_user(db, user_id=current_user.id, job_id=job_id)
    ]
    draft_cover_letters = [
        _serialize_cover_letter(cl)
        for cl in get_completed_drafts_for_user(db, user_id=current_user.id, job_id=job_id)
    ]

    tracker_entries = list_tracker_entries_for_user(db, user_id=current_user.id)
    tracked_job_map: dict[int, int] = {e.job_id: e.id for e in tracker_entries if e.job_id}

    all_cl_job_ids = list({
        cl["job_id"] for cl in saved_cover_letters + draft_cover_letters
        if cl.get("job_id")
    })
    job_map = get_jobs_by_ids(db, job_ids=all_cl_job_ids)
    job_url_map: dict[int, str] = {
        jid: job.job_url for jid, job in job_map.items() if job.job_url
    }

    return templates.TemplateResponse(
        request=request,
        name="documents.html",
        context={
            **get_base_template_context(request),
            "current_user": current_user,
            "documents": serialized,
            "document_types": [(t.value, DOCUMENT_TYPE_LABELS[t]) for t in DocumentType],
            "has_existing_cv": has_existing_cv,
            "profile_has_error": profile_has_error,
            "signature_image": signature_image,
            "redirect_to_profile": redirect_to_profile,
            "saved_cover_letters": saved_cover_letters,
            "draft_cover_letters": draft_cover_letters,
            "job_id_filter": job_id,
            "tracked_job_map": tracked_job_map,
            "job_url_map": job_url_map,
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

    request.session["redirect_to_profile"] = True
    request.session["profile_extraction_in_progress"] = True

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
