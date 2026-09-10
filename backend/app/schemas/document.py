"""
Pydantic schemas for API request/response objects.
"""
from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# File Validation
# ---------------------------------------------------------------------------

class FileValidationResult(BaseModel):
    file_type: Optional[str] = None
    is_supported: bool = False
    is_readable: bool = False
    page_count: Optional[int] = None
    status: str = "FAILED"  # PASS | FAILED


# ---------------------------------------------------------------------------
# Financial Validation Check
# ---------------------------------------------------------------------------

class ValidationCheck(BaseModel):
    name: str
    formula: str
    operands: Dict[str, Any] = {}
    calculated_value: Optional[float] = None
    reported_value: Optional[float] = None
    variance: Optional[float] = None
    tolerance: Optional[float] = None
    status: str  # PASS | FAIL | NOT_APPLICABLE


class ValidationResult(BaseModel):
    checks: List[ValidationCheck] = []
    overall_status: str = "NOT_APPLICABLE"  # PASS | FAIL | NOT_APPLICABLE
    issues: List[str] = []


# ---------------------------------------------------------------------------
# Completeness Guard
# ---------------------------------------------------------------------------

class CompletenessResult(BaseModel):
    completeness_status: str = "OK"  # OK | WARNING
    potential_missing_fields: List[str] = []
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Processing Metadata
# ---------------------------------------------------------------------------

class ProcessingMetadata(BaseModel):
    ocr_used: bool = False
    ai_provider: Optional[str] = None
    ai_model: Optional[str] = None
    processed_at: str
    processing_time_ms: int = 0


# ---------------------------------------------------------------------------
# Full Response
# ---------------------------------------------------------------------------

class DocumentProcessResponse(BaseModel):
    document_name: str
    document_type: str
    processing_status: str  # PASS | FAILED

    file_validation: FileValidationResult
    extracted_data: Optional[Any] = None
    validation: Optional[ValidationResult] = None
    completeness: Optional[CompletenessResult] = None
    processing_metadata: ProcessingMetadata

    error: Optional[Dict[str, str]] = None


# ---------------------------------------------------------------------------
# List / Dashboard
# ---------------------------------------------------------------------------

class DocumentListItem(BaseModel):
    id: int
    document_name: str
    document_type: str
    processing_status: str
    file_type: Optional[str] = None
    page_count: Optional[int] = None
    ocr_used: Optional[bool] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    documents: List[DocumentListItem]
    total: int


# ---------------------------------------------------------------------------
# Error
# ---------------------------------------------------------------------------

class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str
    version: str
    database: str
