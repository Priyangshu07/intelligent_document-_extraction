"""
Document validation service.

Responsibilities:
  - Reject unsupported, empty, zero-byte and corrupt files.
  - Validate by actual content (magic bytes / PDF header), not extension alone.
  - Enforce maximum 3-page limit.
  - Sanitize filenames and prevent path traversal.
  - Never expose stack traces.

Supported:
  - PDF (application/pdf)
  - JPG / JPEG (image/jpeg)
  - PNG (image/png)
"""
import io
import os
import re
import tempfile
from pathlib import Path
from typing import Tuple

import fitz  # PyMuPDF
from PIL import Image, UnidentifiedImageError

from app.core.logging import get_logger
from app.schemas.document import FileValidationResult

logger = get_logger(__name__)

# Magic bytes for supported types
PDF_MAGIC = b"%PDF"
JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

SUPPORTED_MIME = {
    "application/pdf": "pdf",
    "image/jpeg": "jpeg",
    "image/png": "png",
}

MAX_PAGES = 3


def sanitize_filename(filename: str) -> str:
    """
    Remove path traversal components and illegal characters.
    Returns a safe base filename only.
    """
    # Take only the final component
    name = Path(filename).name
    # Replace any non-alphanumeric/dot/dash/underscore characters
    name = re.sub(r"[^\w.\-]", "_", name)
    # Prevent hidden files
    name = name.lstrip(".")
    if not name:
        name = "document"
    return name[:255]


def detect_mime(content: bytes) -> str:
    """
    Detect MIME type from magic bytes.
    Returns MIME string or 'unknown'.
    """
    if content[:4] == PDF_MAGIC:
        return "application/pdf"
    if content[:3] == JPEG_MAGIC:
        return "image/jpeg"
    if content[:8] == PNG_MAGIC:
        return "image/png"
    return "unknown"


def validate_document(
    file_content: bytes,
    original_filename: str,
) -> Tuple[FileValidationResult, str, int]:
    """
    Validate uploaded document.

    Returns:
        (FileValidationResult, safe_mime_type, page_count)

    Raises:
        ValueError with a safe, user-facing message on validation failure.
    """
    safe_name = sanitize_filename(original_filename)
    logger.info("file_validation_start", filename=safe_name, size_bytes=len(file_content))

    # --- Empty / zero-byte ---
    if not file_content or len(file_content) == 0:
        logger.warning("file_validation_empty", filename=safe_name)
        result = FileValidationResult(
            file_type=None,
            is_supported=False,
            is_readable=False,
            page_count=None,
            status="FAILED",
        )
        raise ValueError("EMPTY_FILE:The uploaded file is empty or zero bytes.")

    # --- Detect MIME from content ---
    mime = detect_mime(file_content)

    if mime not in SUPPORTED_MIME:
        logger.warning("file_validation_unsupported", filename=safe_name, detected_mime=mime)
        result = FileValidationResult(
            file_type=mime if mime != "unknown" else "unsupported",
            is_supported=False,
            is_readable=False,
            page_count=None,
            status="FAILED",
        )
        raise ValueError("UNSUPPORTED_FILE_TYPE:Only PDF / JPG / PNG documents are supported.")

    # --- Validate readability and page count ---
    page_count = 0

    if mime == "application/pdf":
        try:
            pdf_doc = fitz.open(stream=io.BytesIO(file_content), filetype="pdf")
            page_count = len(pdf_doc)
            pdf_doc.close()
        except Exception as exc:
            logger.warning("file_validation_corrupt_pdf", filename=safe_name, error=str(exc))
            raise ValueError("CORRUPT_FILE:The PDF file appears to be corrupted or unreadable.")

        if page_count == 0:
            raise ValueError("CORRUPT_FILE:The PDF file contains no readable pages.")

        if page_count > MAX_PAGES:
            raise ValueError(
                f"TOO_MANY_PAGES:Document has {page_count} pages. Maximum allowed is {MAX_PAGES}."
            )

    else:  # JPEG or PNG
        try:
            img = Image.open(io.BytesIO(file_content))
            img.verify()  # will raise on corrupt
        except (UnidentifiedImageError, Exception) as exc:
            logger.warning("file_validation_corrupt_image", filename=safe_name, error=str(exc))
            raise ValueError("CORRUPT_FILE:The image file appears to be corrupted or unreadable.")
        page_count = 1  # one image = one page

    result = FileValidationResult(
        file_type=mime,
        is_supported=True,
        is_readable=True,
        page_count=page_count,
        status="PASS",
    )

    logger.info(
        "file_validation_pass",
        filename=safe_name,
        mime=mime,
        pages=page_count,
    )
    return result, mime, page_count
