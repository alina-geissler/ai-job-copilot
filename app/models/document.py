"""Define the ORM model for user documents.

Map the ``documents`` database table to a Python class. A single shared table
stores all document types (uploaded CVs, generated cover letters, etc.)
distinguished by the ``document_type`` discriminator column.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import DocumentProcessingStatus, DocumentType, ExtractionMethod
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class Document(Base):
    """Represent a document owned by a user.

    Store both uploaded files (e.g. CVs) and generated files (e.g. cover
    letters) in one table. The ``document_type`` field is the discriminator.
    Text extraction results and processing state are tracked here so the
    rest of the application can query extracted CV text without accessing
    object storage.
    """

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_type: Mapped[DocumentType] = mapped_column(
        Enum(DocumentType, name="documenttype"), nullable=False, index=True
    )
    document_name: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    processing_status: Mapped[DocumentProcessingStatus] = mapped_column(
        Enum(DocumentProcessingStatus, name="documentprocessingstatus"),
        nullable=False,
        default=DocumentProcessingStatus.PENDING,
        index=True,
    )
    extraction_method: Mapped[ExtractionMethod | None] = mapped_column(
        Enum(ExtractionMethod, name="extractionmethod"), nullable=True
    )
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    user: Mapped[User] = relationship("User", back_populates="documents")
