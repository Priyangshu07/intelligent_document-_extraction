"""
SQLAlchemy ORM model for persisting processed financial documents.
JSONB columns store extraction results and validation outputs.
"""
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database import Base


class ProcessedDocument(Base):
    __tablename__ = "processed_documents"

    id = Column(Integer, primary_key=True, index=True)
    document_name = Column(String(512), nullable=False, index=True)
    document_type = Column(String(64), nullable=False)
    processing_status = Column(String(32), nullable=False)  # PASS | FAILED
    file_type = Column(String(64), nullable=True)
    page_count = Column(Integer, nullable=True)
    is_readable = Column(Boolean, nullable=True)
    ocr_used = Column(Boolean, default=False)

    extracted_data = Column(JSONB, nullable=True)
    validation = Column(JSONB, nullable=True)
    file_validation = Column(JSONB, nullable=True)
    processing_metadata = Column(JSONB, nullable=True)
    completeness = Column(JSONB, nullable=True)

    error_detail = Column(Text, nullable=True)  # safe error message, never stack trace

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return f"<ProcessedDocument id={self.id} name={self.document_name} status={self.processing_status}>"
