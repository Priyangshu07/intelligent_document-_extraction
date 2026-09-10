"""
OCR / Text Extraction Service.

Strategy:
  1. For PDF: attempt native PyMuPDF text extraction.
  2. If native text is insufficient (< MIN_TEXT_CHARS threshold per page average),
     classify the PDF as scanned / image-based.
  3. For scanned PDFs and image files: render each page to an image (300 DPI),
     encode as base64 PNG, and return image bytes suitable for vision LLM input.
  4. Return a NormalizedDocument containing:
     - raw_text      : combined text from all pages (may be empty)
     - page_texts    : per-page text list
     - page_images   : per-page base64 PNG bytes (populated for scanned/image docs)
     - is_scanned    : True if OCR path was taken
     - page_count    : total pages

The LLM vision path (extraction_service.py) handles the actual semantic
extraction; this module only recovers text / renders images.
"""
from __future__ import annotations

import base64
import io
from dataclasses import dataclass, field
from typing import List, Optional

import fitz  # PyMuPDF
from PIL import Image

from app.core.logging import get_logger

logger = get_logger(__name__)

# Threshold: fewer than this many characters per page on average
# indicates a scanned / image-based PDF.
MIN_TEXT_CHARS_PER_PAGE = 50
RENDER_DPI = 200  # balance quality vs. token cost


@dataclass
class NormalizedDocument:
    raw_text: str = ""
    page_texts: List[str] = field(default_factory=list)
    page_images_b64: List[str] = field(default_factory=list)  # base64 PNG strings
    is_scanned: bool = False
    page_count: int = 0
    mime: str = ""


def extract_pdf_text(file_content: bytes) -> NormalizedDocument:
    """
    Extract text from a PDF. Falls back to page rendering if insufficient text.
    """
    pdf = fitz.open(stream=io.BytesIO(file_content), filetype="pdf")
    page_count = len(pdf)
    page_texts: List[str] = []

    for page in pdf:
        page_texts.append(page.get_text("text"))

    total_chars = sum(len(t) for t in page_texts)
    avg_chars = total_chars / page_count if page_count else 0

    if avg_chars >= MIN_TEXT_CHARS_PER_PAGE:
        # Native text is usable
        raw_text = "\n\n--- PAGE BREAK ---\n\n".join(page_texts)
        logger.info("ocr_native_text", pages=page_count, avg_chars=round(avg_chars))
        result = NormalizedDocument(
            raw_text=raw_text,
            page_texts=page_texts,
            page_images_b64=[],
            is_scanned=False,
            page_count=page_count,
            mime="application/pdf",
        )
    else:
        # Scanned / image-based PDF → render to images
        logger.info(
            "ocr_scanned_pdf_detected",
            pages=page_count,
            avg_chars=round(avg_chars),
            action="render_to_images",
        )
        page_images_b64 = _render_pdf_pages(pdf)
        result = NormalizedDocument(
            raw_text="\n\n--- PAGE BREAK ---\n\n".join(page_texts),  # may have partial text
            page_texts=page_texts,
            page_images_b64=page_images_b64,
            is_scanned=True,
            page_count=page_count,
            mime="application/pdf",
        )

    pdf.close()
    return result


def _render_pdf_pages(pdf: fitz.Document) -> List[str]:
    """Render each PDF page to a base64-encoded PNG string."""
    images_b64: List[str] = []
    mat = fitz.Matrix(RENDER_DPI / 72, RENDER_DPI / 72)  # 72 is PDF point density

    for page_num, page in enumerate(pdf):
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img_bytes = pix.tobytes("png")
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        images_b64.append(b64)
        logger.debug("page_rendered", page=page_num + 1, size_bytes=len(img_bytes))

    return images_b64


def extract_image(file_content: bytes, mime: str) -> NormalizedDocument:
    """
    Process an image file (JPEG/PNG).
    Encodes as base64 PNG for vision LLM.
    """
    # Convert JPEG to PNG for uniform handling
    img = Image.open(io.BytesIO(file_content))
    if img.mode not in ("RGB", "RGBA", "L"):
        img = img.convert("RGB")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    logger.info("image_encoded_for_vision", mime=mime, size_bytes=len(file_content))
    return NormalizedDocument(
        raw_text="",
        page_texts=[""],
        page_images_b64=[b64],
        is_scanned=True,
        page_count=1,
        mime=mime,
    )


def process_document(file_content: bytes, mime: str) -> NormalizedDocument:
    """
    Main entry point: dispatch to PDF or image extraction based on MIME type.
    """
    if mime == "application/pdf":
        return extract_pdf_text(file_content)
    else:
        return extract_image(file_content, mime)
