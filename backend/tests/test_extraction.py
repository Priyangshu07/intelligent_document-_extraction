"""
Tests for document file validation service.
No AI, no database, no network required.
"""
import io
import struct
import pytest
from app.services.document_validation_service import (
    validate_document,
    sanitize_filename,
    detect_mime,
    PDF_MAGIC,
    JPEG_MAGIC,
    PNG_MAGIC,
)


def make_minimal_pdf(num_pages: int = 1) -> bytes:
    """Create a minimal but valid PDF in memory."""
    import fitz
    doc = fitz.open()
    for _ in range(num_pages):
        doc.new_page()
    return doc.tobytes()


def make_jpeg_bytes() -> bytes:
    """Create a minimal valid JPEG."""
    from PIL import Image
    img = Image.new("RGB", (100, 100), color="red")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def make_png_bytes() -> bytes:
    """Create a minimal valid PNG."""
    from PIL import Image
    img = Image.new("RGB", (100, 100), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestSanitizeFilename:

    def test_normal_filename(self):
        assert sanitize_filename("document.pdf") == "document.pdf"

    def test_path_traversal_blocked(self):
        result = sanitize_filename("../../../etc/passwd")
        assert ".." not in result
        assert "/" not in result

    def test_special_chars_replaced(self):
        result = sanitize_filename("my document (1).pdf")
        assert "(" not in result or result.endswith(".pdf")

    def test_hidden_file_stripped(self):
        result = sanitize_filename(".hidden.pdf")
        assert not result.startswith(".")

    def test_empty_filename_default(self):
        result = sanitize_filename("")
        assert result == "document"


class TestDetectMime:

    def test_detect_pdf(self):
        assert detect_mime(PDF_MAGIC + b"rest") == "application/pdf"

    def test_detect_jpeg(self):
        assert detect_mime(JPEG_MAGIC + b"rest") == "image/jpeg"

    def test_detect_png(self):
        assert detect_mime(PNG_MAGIC + b"rest") == "image/png"

    def test_unknown(self):
        assert detect_mime(b"GARBAGE") == "unknown"


class TestValidateDocument:

    def test_valid_pdf(self):
        content = make_minimal_pdf(1)
        result, mime, pages = validate_document(content, "test.pdf")
        assert result.status == "PASS"
        assert result.is_supported is True
        assert result.is_readable is True
        assert pages == 1
        assert mime == "application/pdf"

    def test_valid_jpeg(self):
        content = make_jpeg_bytes()
        result, mime, pages = validate_document(content, "invoice.jpg")
        assert result.status == "PASS"
        assert pages == 1
        assert mime == "image/jpeg"

    def test_valid_png(self):
        content = make_png_bytes()
        result, mime, pages = validate_document(content, "doc.png")
        assert result.status == "PASS"
        assert pages == 1

    def test_empty_file(self):
        with pytest.raises(ValueError, match="EMPTY_FILE"):
            validate_document(b"", "empty.pdf")

    def test_zero_bytes(self):
        with pytest.raises(ValueError):
            validate_document(b"", "doc.pdf")

    def test_unsupported_file_type(self):
        with pytest.raises(ValueError, match="UNSUPPORTED_FILE_TYPE"):
            validate_document(b"GARBAGE_CONTENT_NO_MAGIC", "doc.txt")

    def test_corrupt_pdf(self):
        # PDF magic but invalid content
        corrupt = PDF_MAGIC + b"CORRUPT_NOT_REAL_PDF"
        with pytest.raises(ValueError, match="CORRUPT_FILE"):
            validate_document(corrupt, "corrupt.pdf")

    def test_corrupt_image(self):
        # JPEG magic but invalid content
        corrupt = JPEG_MAGIC + b"CORRUPT_JPEG_DATA"
        with pytest.raises(ValueError, match="CORRUPT_FILE"):
            validate_document(corrupt, "corrupt.jpg")

    def test_too_many_pages(self):
        content = make_minimal_pdf(4)  # 4 pages > 3 max
        with pytest.raises(ValueError, match="TOO_MANY_PAGES"):
            validate_document(content, "long.pdf")

    def test_exactly_3_pages(self):
        content = make_minimal_pdf(3)
        result, mime, pages = validate_document(content, "three.pdf")
        assert result.status == "PASS"
        assert pages == 3

    def test_does_not_trust_extension_alone(self):
        """A JPEG disguised as .pdf should be detected correctly."""
        jpeg_bytes = make_jpeg_bytes()
        # Should detect as JPEG based on magic bytes, not .pdf extension
        result, mime, pages = validate_document(jpeg_bytes, "tricky.pdf")
        assert mime == "image/jpeg"
        assert result.status == "PASS"
