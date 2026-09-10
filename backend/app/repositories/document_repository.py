"""
Document Repository - database access layer.

Responsibilities:
  - Persist processed document results to PostgreSQL.
  - Upsert by document_name (latest-wins strategy).
  - Retrieve document list for dashboard.
  - Retrieve latest result by document name.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.document import ProcessedDocument
from app.schemas.document import DocumentProcessResponse, DocumentListItem

logger = get_logger(__name__)


def upsert_document(
    db: Session,
    response: DocumentProcessResponse,
) -> ProcessedDocument:
    """
    Persist or update a processed document result.
    If a record with the same document_name already exists, update it.
    This ensures GET /documents/{name} always returns the LATEST result.
    """
    existing = (
        db.query(ProcessedDocument)
        .filter(ProcessedDocument.document_name == response.document_name)
        .first()
    )

    metadata = response.processing_metadata
    file_val = response.file_validation

    if existing:
        logger.info("db_upsert_update", document=response.document_name)
        existing.document_type = response.document_type
        existing.processing_status = response.processing_status
        existing.file_type = file_val.file_type if file_val else None
        existing.page_count = file_val.page_count if file_val else None
        existing.is_readable = file_val.is_readable if file_val else None
        existing.ocr_used = metadata.ocr_used if metadata else False
        existing.extracted_data = response.extracted_data
        existing.validation = response.validation.model_dump() if response.validation else None
        existing.file_validation = file_val.model_dump() if file_val else None
        existing.processing_metadata = metadata.model_dump() if metadata else None
        existing.completeness = response.completeness.model_dump() if response.completeness else None
        existing.error_detail = response.error.get("message") if response.error else None
        existing.updated_at = datetime.now(timezone.utc)
        doc = existing
    else:
        logger.info("db_upsert_insert", document=response.document_name)
        doc = ProcessedDocument(
            document_name=response.document_name,
            document_type=response.document_type,
            processing_status=response.processing_status,
            file_type=file_val.file_type if file_val else None,
            page_count=file_val.page_count if file_val else None,
            is_readable=file_val.is_readable if file_val else None,
            ocr_used=metadata.ocr_used if metadata else False,
            extracted_data=response.extracted_data,
            validation=response.validation.model_dump() if response.validation else None,
            file_validation=file_val.model_dump() if file_val else None,
            processing_metadata=metadata.model_dump() if metadata else None,
            completeness=response.completeness.model_dump() if response.completeness else None,
            error_detail=response.error.get("message") if response.error else None,
        )
        db.add(doc)

    try:
        db.commit()
        db.refresh(doc)
        logger.info("db_persist_ok", document=response.document_name, doc_id=doc.id)
    except Exception as exc:
        db.rollback()
        logger.error("db_persist_error", document=response.document_name, error=str(exc)[:200])
        raise

    return doc


def get_document_by_name(db: Session, document_name: str) -> Optional[ProcessedDocument]:
    """Retrieve the latest processed result for a given document name."""
    return (
        db.query(ProcessedDocument)
        .filter(ProcessedDocument.document_name == document_name)
        .order_by(ProcessedDocument.updated_at.desc())
        .first()
    )


def list_documents(db: Session, skip: int = 0, limit: int = 100) -> List[ProcessedDocument]:
    """Return a list of processed documents for the dashboard, newest first."""
    return (
        db.query(ProcessedDocument)
        .order_by(ProcessedDocument.updated_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def count_documents(db: Session) -> int:
    return db.query(ProcessedDocument).count()
