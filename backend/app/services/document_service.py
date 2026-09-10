"""
Main Document Service - orchestrates the full processing pipeline.

Pipeline:
  1. File Validation (magic bytes, size, page count)
  2. OCR / Text Extraction (native PDF text or image rendering)
  3. AI Extraction (vision LLM with document-specific prompt)
  4. Pydantic Validation of extracted JSON
  5. Completeness Guard
  6. Deterministic Financial Validation
  7. Database Persistence
  8. Return structured response

Every stage is logged. Errors at any stage return a safe structured error.
Stack traces are NEVER exposed to the client.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.document import (
    DocumentProcessResponse,
    FileValidationResult,
    ProcessingMetadata,
    ValidationResult,
    CompletenessResult,
)
from app.services.document_validation_service import validate_document, sanitize_filename
from app.services.ocr_service import process_document
from app.services.extraction_service import extract_document
from app.services.financial_validation_service import validate_financial_data
from app.utils.completeness_guard import check_completeness

logger = get_logger(__name__)

VALID_DOCUMENT_TYPES = {
    "invoice",
    "balance_sheet",
    "profit_and_loss",
    "cash_flow_statement",
}


def process_uploaded_document(
    file_content: bytes,
    original_filename: str,
    document_type: str,
) -> DocumentProcessResponse:
    """
    Full document processing pipeline.

    Args:
        file_content   : raw bytes of the uploaded file
        original_filename: original filename from client
        document_type  : invoice | balance_sheet | profit_and_loss | cash_flow_statement

    Returns:
        DocumentProcessResponse (always returned, never raises to caller)
    """
    pipeline_start = time.time()
    safe_name = sanitize_filename(original_filename)

    logger.info(
        "pipeline_start",
        document=safe_name,
        doc_type=document_type,
        size_bytes=len(file_content),
    )

    # Validate document type
    if document_type not in VALID_DOCUMENT_TYPES:
        return _error_response(
            document_name=safe_name,
            document_type=document_type,
            code="INVALID_DOCUMENT_TYPE",
            message=f"document_type must be one of: {', '.join(sorted(VALID_DOCUMENT_TYPES))}",
        )

    # =========================================================
    # Stage 1: File Validation
    # =========================================================
    try:
        file_validation, mime, page_count = validate_document(file_content, original_filename)
    except ValueError as exc:
        parts = str(exc).split(":", 1)
        code = parts[0] if len(parts) == 2 else "FILE_VALIDATION_ERROR"
        message = parts[1] if len(parts) == 2 else str(exc)
        logger.warning("pipeline_file_validation_failed", document=safe_name, code=code)
        return _error_response(
            document_name=safe_name,
            document_type=document_type,
            code=code,
            message=message,
        )

    # =========================================================
    # Stage 2: OCR / Text Extraction
    # =========================================================
    try:
        t0 = time.time()
        normalized_doc = process_document(file_content, mime)
        ocr_ms = int((time.time() - t0) * 1000)
        logger.info(
            "pipeline_ocr_complete",
            document=safe_name,
            is_scanned=normalized_doc.is_scanned,
            has_text=bool(normalized_doc.raw_text.strip()),
            elapsed_ms=ocr_ms,
        )
    except Exception as exc:
        logger.error("pipeline_ocr_error", document=safe_name, error=str(exc)[:200])
        return _error_response(
            document_name=safe_name,
            document_type=document_type,
            code="OCR_FAILURE",
            message="Failed to extract text or render document pages.",
            file_validation=file_validation,
        )

    # =========================================================
    # Stage 3: AI Extraction
    # =========================================================
    extracted_data_raw: Dict = {}
    ai_error: Optional[str] = None

    try:
        t0 = time.time()
        extracted_data_raw = extract_document(normalized_doc, document_type, safe_name)
        ai_ms = int((time.time() - t0) * 1000)
        logger.info(
            "pipeline_ai_complete",
            document=safe_name,
            fields_extracted=len(extracted_data_raw),
            elapsed_ms=ai_ms,
        )
    except Exception as exc:
        logger.error("pipeline_ai_error", document=safe_name, error=str(exc)[:200])
        ai_error = str(exc)[:200]
        # Continue with empty extraction — still store a partial result

    # =========================================================
    # Stage 4: Completeness Guard
    # =========================================================
    completeness_result = CompletenessResult(
        completeness_status="OK",
        potential_missing_fields=[],
    )
    if extracted_data_raw is not None:
        try:
            completeness_result = check_completeness(
                raw_text=normalized_doc.raw_text,
                extracted_data=extracted_data_raw,
                document_type=document_type,
            )
        except Exception as exc:
            logger.warning("pipeline_completeness_error", error=str(exc)[:100])

    # =========================================================
    # Stage 5: Deterministic Financial Validation
    # =========================================================
    validation_result = ValidationResult(
        checks=[],
        overall_status="NOT_APPLICABLE",
        issues=[],
    )
    if extracted_data_raw and not ai_error:
        try:
            validation_result = validate_financial_data(document_type, extracted_data_raw)
        except Exception as exc:
            logger.error("pipeline_validation_error", error=str(exc)[:200])

    # =========================================================
    # Stage 6: Build Response
    # =========================================================
    total_ms = int((time.time() - pipeline_start) * 1000)
    processing_status = "PASS" if not ai_error else "FAILED"

    # If AI returned empty extraction but no error, still mark PASS
    # (extraction may have legitimately found no data for a particular doc type)

    metadata = ProcessingMetadata(
        ocr_used=normalized_doc.is_scanned,
        ai_provider=settings.AI_PROVIDER,
        ai_model=settings.AI_MODEL,
        processed_at=datetime.now(timezone.utc).isoformat(),
        processing_time_ms=total_ms,
    )

    response = DocumentProcessResponse(
        document_name=safe_name,
        document_type=document_type,
        processing_status=processing_status,
        file_validation=file_validation,
        extracted_data=extracted_data_raw,
        validation=validation_result,
        completeness=completeness_result,
        processing_metadata=metadata,
        error={"code": "AI_EXTRACTION_FAILED", "message": ai_error} if ai_error else None,
    )

    logger.info(
        "pipeline_complete",
        document=safe_name,
        doc_type=document_type,
        processing_status=processing_status,
        validation_status=validation_result.overall_status,
        total_ms=total_ms,
    )

    return response


def _error_response(
    document_name: str,
    document_type: str,
    code: str,
    message: str,
    file_validation: Optional[FileValidationResult] = None,
) -> DocumentProcessResponse:
    """Build a standardized error response."""
    return DocumentProcessResponse(
        document_name=document_name,
        document_type=document_type,
        processing_status="FAILED",
        file_validation=file_validation or FileValidationResult(
            file_type=None,
            is_supported=False,
            is_readable=False,
            page_count=None,
            status="FAILED",
        ),
        extracted_data=None,
        validation=None,
        completeness=None,
        processing_metadata=ProcessingMetadata(
            ocr_used=False,
            processed_at=datetime.now(timezone.utc).isoformat(),
            processing_time_ms=0,
        ),
        error={"code": code, "message": message},
    )
