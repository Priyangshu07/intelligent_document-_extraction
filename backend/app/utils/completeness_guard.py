"""
Extraction Completeness Guard.

Compares the raw OCR/text representation against the structured
extraction to detect potential omissions.

IMPORTANT:
  - This guard ONLY identifies potential omissions.
  - It NEVER invents or fills in missing values.
  - It produces warnings, not corrections.

Strategy:
  1. Tokenize known numerical candidates from OCR text.
  2. Check whether key expected labels appear in raw text but are absent from extraction.
  3. Flag any meaningful discrepancy as a WARNING.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.core.logging import get_logger
from app.schemas.document import CompletenessResult

logger = get_logger(__name__)

# Labels we expect to find for each document type
EXPECTED_LABELS = {
    "invoice": [
        "invoice", "date", "total", "subtotal", "tax", "vat", "gst",
        "quantity", "unit price", "amount", "vendor", "customer", "bill",
    ],
    "balance_sheet": [
        "total assets", "total liabilities", "capital", "reserves", "deposits",
        "advances", "investments", "cash", "borrowings", "equity",
    ],
    "profit_and_loss": [
        "interest earned", "other income", "total income", "interest expended",
        "operating expenses", "provisions", "net profit", "earnings per share",
        "basic", "diluted", "appropriations",
    ],
    "cash_flow_statement": [
        "operating", "investing", "financing", "opening cash", "closing cash",
        "net increase", "net decrease", "cash equivalents",
    ],
}


def _extract_numerical_candidates(text: str) -> List[str]:
    """
    Find all numerical patterns in raw text.
    Detects: 1,234,567 | 1234567 | (1,234) | -1234 | 3.49 | 3,49
    """
    pattern = r"[\(\-]?\d[\d,\.]+\d"
    return re.findall(pattern, text)


def _count_non_null_values(extracted_data: Dict, depth: int = 0) -> int:
    """Recursively count non-null extracted values."""
    if depth > 5:
        return 0
    count = 0
    if isinstance(extracted_data, dict):
        for k, v in extracted_data.items():
            if k == "value" and v is not None:
                count += 1
            elif k == "values" and isinstance(v, dict):
                count += sum(1 for vv in v.values() if vv is not None)
            elif isinstance(v, (dict, list)):
                count += _count_non_null_values(v, depth + 1)
    elif isinstance(extracted_data, list):
        for item in extracted_data:
            count += _count_non_null_values(item, depth + 1)
    return count


def check_completeness(
    raw_text: str,
    extracted_data: Dict,
    document_type: str,
) -> CompletenessResult:
    """
    Analyze whether extraction appears complete relative to raw text.
    Returns a CompletenessResult with status OK or WARNING.
    """
    potential_missing: List[str] = []
    notes_parts: List[str] = []

    expected = EXPECTED_LABELS.get(document_type, [])
    raw_lower = raw_text.lower() if raw_text else ""

    # Check 1: Are expected labels present in raw text but missing from extraction?
    extracted_str = str(extracted_data).lower()
    for label in expected:
        if label in raw_lower and label not in extracted_str:
            potential_missing.append(label)

    # Check 2: Numerical value coverage
    if raw_text:
        numerical_candidates = _extract_numerical_candidates(raw_text)
        extracted_values = _count_non_null_values(extracted_data)
        raw_count = len(numerical_candidates)

        if raw_count > 0:
            coverage = extracted_values / raw_count if raw_count > 0 else 1.0
            notes_parts.append(
                f"OCR numerical candidates: {raw_count}, "
                f"extracted non-null values: {extracted_values}, "
                f"coverage ratio: {coverage:.1%}"
            )
            if coverage < 0.3 and raw_count > 5:
                notes_parts.append("Low extraction coverage detected.")
                if "low extraction coverage" not in potential_missing:
                    potential_missing.append("potential_low_extraction_coverage")

    # Check 3: Line items present in text but not extracted
    if document_type == "invoice" and raw_text:
        if "line_items" not in extracted_str or "[]" in extracted_str:
            if any(kw in raw_lower for kw in ["qty", "quantity", "item", "product"]):
                potential_missing.append("line_items_may_be_missing")

    status = "WARNING" if potential_missing else "OK"
    notes = "; ".join(notes_parts) if notes_parts else None

    if potential_missing:
        logger.warning(
            "completeness_warning",
            document_type=document_type,
            missing_count=len(potential_missing),
            potential_missing=potential_missing[:10],
        )
    else:
        logger.info("completeness_ok", document_type=document_type)

    return CompletenessResult(
        completeness_status=status,
        potential_missing_fields=potential_missing,
        notes=notes,
    )
