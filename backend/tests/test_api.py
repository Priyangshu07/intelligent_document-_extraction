"""
API integration tests using TestClient (no actual database or AI needed).
Tests use mocking to isolate the API layer.
"""
import io
import json
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app


def make_minimal_pdf(num_pages: int = 1) -> bytes:
    import fitz
    doc = fitz.open()
    for _ in range(num_pages):
        doc.new_page()
    return doc.tobytes()


def make_png_bytes() -> bytes:
    from PIL import Image
    img = Image.new("RGB", (100, 100), color="green")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def client():
    """FastAPI test client with database dependency overridden."""
    def override_get_db():
        db = MagicMock()
        db.execute = MagicMock()
        yield db

    from app.core.database import get_db
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def mock_pipeline():
    """Mock the document processing pipeline."""
    with patch('app.api.routes.documents.process_uploaded_document') as mock_proc, \
         patch('app.api.routes.documents.upsert_document') as mock_db:
        yield mock_proc, mock_db


# ============================================================
# Health Check
# ============================================================

class TestHealthCheck:

    def test_health_ok(self, client):
        resp = client.get('/api/v1/health')
        assert resp.status_code == 200
        data = resp.json()
        assert data['status'] == 'ok'
        assert 'version' in data
        assert 'database' in data


# ============================================================
# Document Upload
# ============================================================

class TestDocumentProcess:

    def test_upload_valid_pdf_invoice(self, client, mock_pipeline):
        mock_proc, mock_db = mock_pipeline

        from app.schemas.document import (
            DocumentProcessResponse, FileValidationResult,
            ProcessingMetadata, ValidationResult
        )
        import datetime

        mock_proc.return_value = DocumentProcessResponse(
            document_name="test_invoice.pdf",
            document_type="invoice",
            processing_status="PASS",
            file_validation=FileValidationResult(
                file_type="application/pdf",
                is_supported=True,
                is_readable=True,
                page_count=1,
                status="PASS",
            ),
            extracted_data={"invoice_number": {"value": "INV-001", "page_number": 1, "evidence": "INV-001"}},
            validation=ValidationResult(checks=[], overall_status="PASS", issues=[]),
            processing_metadata=ProcessingMetadata(
                ocr_used=False,
                processed_at=datetime.datetime.utcnow().isoformat(),
                processing_time_ms=1000,
            ),
        )
        mock_db.return_value = MagicMock()

        pdf_bytes = make_minimal_pdf(1)
        resp = client.post(
            '/api/v1/documents/process',
            files={'file': ('test_invoice.pdf', pdf_bytes, 'application/pdf')},
            data={'document_type': 'invoice'},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data['processing_status'] == 'PASS'
        assert data['document_name'] == 'test_invoice.pdf'

    def test_upload_invalid_document_type(self, client):
        pdf_bytes = make_minimal_pdf(1)
        resp = client.post(
            '/api/v1/documents/process',
            files={'file': ('test.pdf', pdf_bytes, 'application/pdf')},
            data={'document_type': 'invalid_type'},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert 'error' in data
        assert data['error']['code'] == 'INVALID_DOCUMENT_TYPE'

    def test_upload_empty_file(self, client):
        resp = client.post(
            '/api/v1/documents/process',
            files={'file': ('empty.pdf', b'', 'application/pdf')},
            data={'document_type': 'invoice'},
        )
        assert resp.status_code == 400

    def test_upload_png(self, client, mock_pipeline):
        mock_proc, mock_db = mock_pipeline
        from app.schemas.document import (
            DocumentProcessResponse, FileValidationResult,
            ProcessingMetadata, ValidationResult
        )
        import datetime

        mock_proc.return_value = DocumentProcessResponse(
            document_name="invoice.png",
            document_type="invoice",
            processing_status="PASS",
            file_validation=FileValidationResult(
                file_type="image/png", is_supported=True,
                is_readable=True, page_count=1, status="PASS",
            ),
            validation=ValidationResult(checks=[], overall_status="NOT_APPLICABLE", issues=[]),
            processing_metadata=ProcessingMetadata(
                ocr_used=True,
                processed_at=datetime.datetime.utcnow().isoformat(),
                processing_time_ms=500,
            ),
        )
        mock_db.return_value = MagicMock()

        png_bytes = make_png_bytes()
        resp = client.post(
            '/api/v1/documents/process',
            files={'file': ('invoice.png', png_bytes, 'image/png')},
            data={'document_type': 'invoice'},
        )
        assert resp.status_code == 200


# ============================================================
# Document List
# ============================================================

class TestDocumentList:

    def test_list_documents_empty(self, client):
        with patch('app.api.routes.documents.list_documents', return_value=[]), \
             patch('app.api.routes.documents.count_documents', return_value=0):
            resp = client.get('/api/v1/documents')
            assert resp.status_code == 200
            data = resp.json()
            assert 'documents' in data
            assert data['total'] == 0

    def test_list_documents_with_results(self, client):
        from app.models.document import ProcessedDocument
        from datetime import datetime, timezone

        mock_doc = MagicMock(spec=ProcessedDocument)
        mock_doc.id = 1
        mock_doc.document_name = "balance.pdf"
        mock_doc.document_type = "balance_sheet"
        mock_doc.processing_status = "PASS"
        mock_doc.file_type = "application/pdf"
        mock_doc.page_count = 1
        mock_doc.ocr_used = False
        mock_doc.created_at = datetime.now(timezone.utc)

        with patch('app.api.routes.documents.list_documents', return_value=[mock_doc]), \
             patch('app.api.routes.documents.count_documents', return_value=1):
            resp = client.get('/api/v1/documents')
            assert resp.status_code == 200
            data = resp.json()
            assert data['total'] == 1


# ============================================================
# Get by Document Name
# ============================================================

class TestGetDocument:

    def test_get_existing_document(self, client):
        from datetime import datetime, timezone

        mock_doc = MagicMock()
        mock_doc.id = 1
        mock_doc.document_name = "invoice.pdf"
        mock_doc.document_type = "invoice"
        mock_doc.processing_status = "PASS"
        mock_doc.file_validation = {"status": "PASS"}
        mock_doc.extracted_data = {"invoice_number": {"value": "INV-001"}}
        mock_doc.validation = {"overall_status": "PASS", "checks": []}
        mock_doc.completeness = None
        mock_doc.processing_metadata = {"processed_at": "2024-01-01T00:00:00"}
        mock_doc.created_at = datetime.now(timezone.utc)
        mock_doc.updated_at = datetime.now(timezone.utc)

        with patch('app.api.routes.documents.get_document_by_name', return_value=mock_doc):
            resp = client.get('/api/v1/documents/invoice.pdf')
            assert resp.status_code == 200
            data = resp.json()
            assert data['document_name'] == 'invoice.pdf'

    def test_get_nonexistent_document(self, client):
        with patch('app.api.routes.documents.get_document_by_name', return_value=None):
            resp = client.get('/api/v1/documents/nonexistent.pdf')
            assert resp.status_code == 404
            data = resp.json()
            assert data['error']['code'] == 'DOCUMENT_NOT_FOUND'
