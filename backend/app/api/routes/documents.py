"""
Document API Routes.

Endpoints:
  GET  /api/v1/health                     - Health check
  POST /api/v1/documents/process          - Upload and process document
  GET  /api/v1/documents                  - List processed documents (dashboard)
  GET  /api/v1/documents/{document_name}  - Get latest result by filename
"""
from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.repositories.document_repository import (
    count_documents,
    get_document_by_name,
    list_documents,
    upsert_document,
)
from app.schemas.document import (
    DocumentListItem,
    DocumentListResponse,
    DocumentProcessResponse,
    ErrorResponse,
    HealthResponse,
)
from app.services.document_service import process_uploaded_document, VALID_DOCUMENT_TYPES

logger = get_logger(__name__)
router = APIRouter()

MAX_FILE_SIZE_BYTES = settings.MAX_FILE_SIZE_MB * 1024 * 1024


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    tags=["Health"],
)
def health_check(db: Session = Depends(get_db)):
    """Returns service health status and database connectivity."""
    try:
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
        db_status = "connected"
    except Exception:
        db_status = "disconnected"

    return HealthResponse(
        status="ok",
        version=settings.APP_VERSION,
        database=db_status,
    )


# ---------------------------------------------------------------------------
# Process Document
# ---------------------------------------------------------------------------

@router.post(
    "/documents/process",
    response_model=DocumentProcessResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload and process a financial document",
    tags=["Documents"],
    responses={
        400: {"model": ErrorResponse, "description": "Validation error"},
        413: {"model": ErrorResponse, "description": "File too large"},
        422: {"model": ErrorResponse, "description": "Unprocessable entity"},
        500: {"model": ErrorResponse, "description": "Processing failure"},
    },
)
async def process_document(
    file: UploadFile = File(..., description="PDF, JPG, or PNG document (max 3 pages)"),
    document_type: str = Form(
        ...,
        description="One of: invoice | balance_sheet | profit_and_loss | cash_flow_statement",
    ),
    db: Session = Depends(get_db),
):
    """
    Upload a financial document and run the full processing pipeline:
    file validation → OCR → AI extraction → completeness check →
    financial validation → database persistence.
    """
    logger.info(
        "api_process_request",
        filename=file.filename,
        content_type=file.content_type,
        doc_type=document_type,
    )

    # Validate document_type parameter
    if document_type not in VALID_DOCUMENT_TYPES:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": {
                    "code": "INVALID_DOCUMENT_TYPE",
                    "message": f"document_type must be one of: {', '.join(sorted(VALID_DOCUMENT_TYPES))}",
                }
            },
        )

    # Read file content
    try:
        file_content = await file.read()
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": {"code": "FILE_READ_ERROR", "message": "Could not read uploaded file."}},
        )

    # Check file size
    if len(file_content) == 0:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": {"code": "EMPTY_FILE", "message": "The uploaded file is empty."}},
        )

    if len(file_content) > MAX_FILE_SIZE_BYTES:
        return JSONResponse(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            content={
                "error": {
                    "code": "FILE_TOO_LARGE",
                    "message": f"File exceeds maximum size of {settings.MAX_FILE_SIZE_MB}MB.",
                }
            },
        )

    # Run processing pipeline
    result = process_uploaded_document(
        file_content=file_content,
        original_filename=file.filename or "document",
        document_type=document_type,
    )

    # Persist to database (even failures, for audit trail)
    try:
        upsert_document(db, result)
    except Exception as exc:
        logger.error("api_db_persist_error", error=str(exc)[:200])
        # Do not fail the API call due to DB error — return result anyway

    # Return appropriate HTTP status
    if result.processing_status == "FAILED":
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=result.model_dump(mode="json"),
        )

    return result


# ---------------------------------------------------------------------------
# List Documents
# ---------------------------------------------------------------------------

@router.get(
    "/documents",
    response_model=DocumentListResponse,
    summary="List all processed documents",
    tags=["Documents"],
)
def list_processed_documents(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """Returns paginated list of processed documents for the dashboard."""
    docs = list_documents(db, skip=skip, limit=limit)
    total = count_documents(db)

    items = [DocumentListItem.model_validate(doc) for doc in docs]
    return DocumentListResponse(documents=items, total=total)


# ---------------------------------------------------------------------------
# Get by Document Name
# ---------------------------------------------------------------------------

@router.get(
    "/documents/{document_name}",
    summary="Get latest result for a document by filename",
    tags=["Documents"],
    responses={
        404: {"model": ErrorResponse, "description": "Document not found"},
    },
)
def get_document(document_name: str, db: Session = Depends(get_db)):
    """
    Retrieve the latest processing result for a given document filename.
    If the same file has been processed multiple times, returns the most recent result.
    """
    doc = get_document_by_name(db, document_name)

    if not doc:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": {
                    "code": "DOCUMENT_NOT_FOUND",
                    "message": f"No result found for document '{document_name}'.",
                }
            },
        )

    # Build full response from stored data
    return {
        "id": doc.id,
        "document_name": doc.document_name,
        "document_type": doc.document_type,
        "processing_status": doc.processing_status,
        "file_validation": doc.file_validation,
        "extracted_data": doc.extracted_data,
        "validation": doc.validation,
        "completeness": doc.completeness,
        "processing_metadata": doc.processing_metadata,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
    }
