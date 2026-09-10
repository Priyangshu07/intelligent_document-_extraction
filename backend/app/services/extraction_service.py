"""
AI Extraction Service.

Uses a configurable vision-capable LLM to extract structured financial data
from document text and/or rendered page images.

Design principles:
  - AI is responsible for SEMANTIC UNDERSTANDING ONLY.
  - Python (financial_validation_service) is responsible for all arithmetic.
  - Structured JSON output is requested via Pydantic schemas.
  - Document-specific prompts are used — no generic weak prompts.
  - The AI is never asked to produce PASS/FAIL; only extraction.
  - Missing values → null (never invented).
  - Evidence grounding is always requested.

Supported AI providers (configurable via AI_PROVIDER env var):
  - openai (default, uses responses API with structured output)
  - anthropic
  - google
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.services.ocr_service import NormalizedDocument

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Document-specific extraction prompts
# ---------------------------------------------------------------------------

INVOICE_SYSTEM_PROMPT = """You are an expert financial document parser. 
Extract ALL visible information from the invoice document provided.

Rules (STRICTLY ENFORCED):
1. Extract ONLY what is explicitly visible. NEVER invent or infer missing values.
2. For every field, include: "value", "page_number", "evidence" (verbatim source text).
3. Missing/not-found fields MUST be null: {"value": null, "page_number": null, "evidence": null}
4. Decimal comma: "3,49" → 3.49 (but do NOT blindly replace ALL commas in large numbers).
5. Do NOT infer USD merely because "$" appears — identify the actual currency.
6. Extract ALL line items with ALL visible columns.
7. Parentheses/brackets around numbers indicate negative values: (100) → -100.
8. Return ONLY valid JSON. No markdown, no explanation.

Required JSON structure:
{
  "invoice_number": {"value": ..., "page_number": 1, "evidence": "..."},
  "invoice_date": {"value": ..., "page_number": 1, "evidence": "..."},
  "due_date": {"value": ..., "page_number": null, "evidence": null},
  "vendor_name": {"value": ..., "page_number": 1, "evidence": "..."},
  "vendor_address": {"value": ..., "page_number": null, "evidence": null},
  "vendor_tax_id": {"value": null, "page_number": null, "evidence": null},
  "customer_name": {"value": ..., "page_number": 1, "evidence": "..."},
  "customer_address": {"value": null, "page_number": null, "evidence": null},
  "customer_tax_id": {"value": null, "page_number": null, "evidence": null},
  "billing_address": {"value": null, "page_number": null, "evidence": null},
  "shipping_address": {"value": null, "page_number": null, "evidence": null},
  "purchase_order": {"value": null, "page_number": null, "evidence": null},
  "reference_number": {"value": null, "page_number": null, "evidence": null},
  "currency": {"value": ..., "page_number": 1, "evidence": "..."},
  "currency_symbol": {"value": null, "page_number": null, "evidence": null},
  "payment_terms": {"value": null, "page_number": null, "evidence": null},
  "IBAN": {"value": null, "page_number": null, "evidence": null},
  "subtotal": {"value": ..., "page_number": 1, "evidence": "..."},
  "tax_amount": {"value": ..., "page_number": 1, "evidence": "..."},
  "tax_rate": {"value": null, "page_number": null, "evidence": null},
  "discount": {"value": null, "page_number": null, "evidence": null},
  "shipping": {"value": null, "page_number": null, "evidence": null},
  "total_amount": {"value": ..., "page_number": 1, "evidence": "..."},
  "amount_paid": {"value": null, "page_number": null, "evidence": null},
  "balance_due": {"value": null, "page_number": null, "evidence": null},
  "notes": {"value": null, "page_number": null, "evidence": null},
  "line_items": [
    {
      "description": "...",
      "quantity": 1.0,
      "unit": null,
      "unit_price": 0.0,
      "net_amount": 0.0,
      "tax_rate": null,
      "tax_amount": null,
      "gross_amount": null,
      "page_number": 1,
      "evidence": "..."
    }
  ],
  "tax_summary": null,
  "other_fields": {}
}"""

BALANCE_SHEET_SYSTEM_PROMPT = """You are an expert financial document parser specializing in banking sector balance sheets.
Extract ALL visible financial data from this Consolidated Balance Sheet.

Rules (STRICTLY ENFORCED):
1. Extract ONLY what is explicitly visible. NEVER invent or infer missing values.
2. For every field: include "value", "page_number", "evidence".
3. Missing fields → null values.
4. For multi-period comparative statements: use the column header (e.g. "31-Mar-17") as the key.
5. ALL financial line items must be extracted — do not skip any row.
6. Preserve ORIGINAL source labels exactly (e.g. "Reserves and Surplus", not "reserves").
7. Parentheses/brackets → negative: (1,000) → -1000.
8. Preserve units exactly as stated (e.g. "₹ in '000").
9. Do NOT multiply reported values by 1000 or any factor.
10. Return ONLY valid JSON. No markdown.

Required JSON structure:
{
  "statement_title": {"value": "...", "page_number": 1, "evidence": "..."},
  "company_name": {"value": "...", "page_number": 1, "evidence": "..."},
  "statement_date": {"value": "...", "page_number": 1, "evidence": "..."},
  "currency": {"value": "...", "page_number": 1, "evidence": "..."},
  "unit": {"value": "₹ in '000", "page_number": 1, "evidence": "..."},
  "periods": ["31-Mar-17", "31-Mar-16"],
  "total_assets": {
    "label": "Total",
    "normalized_key": "total_assets",
    "values": {"31-Mar-17": 8923441607, "31-Mar-16": 7812345678},
    "page_number": 1,
    "evidence": "Total 8,923,441,607 7,812,345,678"
  },
  "total_liabilities": {
    "label": "...",
    "normalized_key": "total_liabilities",
    "values": {"31-Mar-17": ..., "31-Mar-16": ...},
    "page_number": 1,
    "evidence": "..."
  },
  "total_equity": {
    "label": "...",
    "normalized_key": "total_equity",
    "values": {},
    "page_number": null,
    "evidence": null
  },
  "total_capital_and_liabilities": {
    "label": "Total Capital & Liabilities",
    "normalized_key": "total_capital_and_liabilities",
    "values": {},
    "page_number": null,
    "evidence": null
  },
  "line_items": [
    {
      "label": "Capital",
      "normalized_key": "capital",
      "values": {"31-Mar-17": 123456, "31-Mar-16": 112345},
      "page_number": 1,
      "evidence": "Capital 123,456 112,345"
    }
  ],
  "sections": {
    "CAPITAL AND LIABILITIES": [...],
    "ASSETS": [...]
  }
}"""

PROFIT_AND_LOSS_SYSTEM_PROMPT = """You are an expert financial document parser specializing in banking sector P&L statements.
Extract ALL visible financial data from this Consolidated Profit & Loss statement.

Rules (STRICTLY ENFORCED):
1. Extract ONLY what is explicitly visible. NEVER invent or infer missing values.
2. For every field: include "value", "page_number", "evidence".
3. Missing fields → null values.
4. For multi-period comparative: use column header as key (e.g. "31-Mar-17").
5. Extract ALL line items: Income, Expenditure, Profit, Appropriations, EPS.
6. Do NOT discard Earnings Per Share (EPS) data — extract basic AND diluted.
7. Preserve ORIGINAL labels exactly.
8. Parentheses/brackets → negative.
9. Preserve units (e.g. "₹ in '000").
10. Return ONLY valid JSON. No markdown.

Required JSON structure:
{
  "statement_title": {"value": "...", "page_number": 1, "evidence": "..."},
  "company_name": {"value": "...", "page_number": 1, "evidence": "..."},
  "periods": ["31-Mar-17", "31-Mar-16"],
  "currency": {"value": "INR", "page_number": 1, "evidence": "..."},
  "unit": {"value": "₹ in '000", "page_number": 1, "evidence": "..."},
  "interest_earned": {"label": "Interest Earned", "normalized_key": "interest_earned", "values": {"31-Mar-17": ..., "31-Mar-16": ...}, "page_number": 1, "evidence": "..."},
  "other_income": {"label": "Other Income", "normalized_key": "other_income", "values": {}, "page_number": null, "evidence": null},
  "total_income": {"label": "Total Income", "normalized_key": "total_income", "values": {}, "page_number": null, "evidence": null},
  "interest_expended": {"label": "Interest Expended", "normalized_key": "interest_expended", "values": {}, "page_number": null, "evidence": null},
  "operating_expenses": {"label": "Operating Expenses", "normalized_key": "operating_expenses", "values": {}, "page_number": null, "evidence": null},
  "provisions_and_contingencies": {"label": "Provisions & Contingencies", "normalized_key": "provisions_and_contingencies", "values": {}, "page_number": null, "evidence": null},
  "total_expenditure": {"label": "Total Expenditure", "normalized_key": "total_expenditure", "values": {}, "page_number": null, "evidence": null},
  "net_profit": {"label": "Net Profit", "normalized_key": "net_profit", "values": {}, "page_number": null, "evidence": null},
  "minority_interest": {"label": "Minority Interest", "normalized_key": "minority_interest", "values": {}, "page_number": null, "evidence": null},
  "share_in_profits_of_associates": {"label": "Share in profits of Associates", "normalized_key": "share_in_profits_of_associates", "values": {}, "page_number": null, "evidence": null},
  "consolidated_profit_attributable_to_group": {"label": "Consolidated Profit attributable to the Group", "normalized_key": "consolidated_profit_attributable_to_group", "values": {}, "page_number": null, "evidence": null},
  "earnings_per_equity_share_basic": {"label": "Basic EPS", "normalized_key": "earnings_per_equity_share_basic", "values": {}, "page_number": null, "evidence": null},
  "earnings_per_equity_share_diluted": {"label": "Diluted EPS", "normalized_key": "earnings_per_equity_share_diluted", "values": {}, "page_number": null, "evidence": null},
  "line_items": [],
  "sections": {
    "INCOME": [],
    "EXPENDITURE": [],
    "PROFIT": [],
    "APPROPRIATIONS": [],
    "EARNINGS PER EQUITY SHARE": []
  }
}"""

CASH_FLOW_SYSTEM_PROMPT = """You are an expert financial document parser specializing in banking sector cash flow statements.
Extract ALL visible financial data from this Consolidated Cash Flow Statement (may span 2 pages).

Rules (STRICTLY ENFORCED):
1. Extract ONLY what is explicitly visible. NEVER invent or infer missing values.
2. For every field: include "value", "page_number", "evidence".
3. Missing fields → null values.
4. For multi-period comparative: use column header as key.
5. Parentheses/brackets → NEGATIVE: (19,084,500) → -19084500.
6. DO NOT lose negative signs.
7. Preserve page continuity across 2-page documents.
8. Preserve units exactly.
9. Extract ALL line items for: Operating, Investing, Financing activities.
10. Return ONLY valid JSON. No markdown.

Required JSON structure:
{
  "statement_title": {"value": "...", "page_number": 1, "evidence": "..."},
  "company_name": {"value": "...", "page_number": 1, "evidence": "..."},
  "periods": ["31-Mar-17", "31-Mar-16"],
  "currency": {"value": "INR", "page_number": 1, "evidence": "..."},
  "unit": {"value": "₹ in '000", "page_number": 1, "evidence": "..."},
  "operating_cash_flow": {"label": "Net Cash from Operating Activities", "normalized_key": "operating_cash_flow", "values": {"31-Mar-17": ..., "31-Mar-16": ...}, "page_number": 1, "evidence": "..."},
  "investing_cash_flow": {"label": "Net Cash from Investing Activities", "normalized_key": "investing_cash_flow", "values": {}, "page_number": null, "evidence": null},
  "financing_cash_flow": {"label": "Net Cash from Financing Activities", "normalized_key": "financing_cash_flow", "values": {}, "page_number": null, "evidence": null},
  "fx_adjustment": {"label": "Effect of exchange fluctuation", "normalized_key": "fx_adjustment", "values": {}, "page_number": null, "evidence": null},
  "net_change_in_cash": {"label": "Net Increase/(Decrease) in Cash", "normalized_key": "net_change_in_cash", "values": {}, "page_number": null, "evidence": null},
  "opening_cash": {"label": "Opening Cash and Cash Equivalents", "normalized_key": "opening_cash", "values": {}, "page_number": null, "evidence": null},
  "closing_cash": {"label": "Closing Cash and Cash Equivalents", "normalized_key": "closing_cash", "values": {}, "page_number": null, "evidence": null},
  "cash_acquired_on_amalgamation": {"label": "Cash acquired on amalgamation", "normalized_key": "cash_acquired_on_amalgamation", "values": {}, "page_number": null, "evidence": null},
  "line_items": [],
  "sections": {
    "OPERATING ACTIVITIES": [],
    "INVESTING ACTIVITIES": [],
    "FINANCING ACTIVITIES": []
  }
}"""


# ---------------------------------------------------------------------------
# Provider-specific API calls
# ---------------------------------------------------------------------------

def _call_openai(
    system_prompt: str,
    user_message: str,
    images_b64: list,
    model: str,
    timeout: int,
) -> str:
    """Call OpenAI API with optional vision input."""
    from openai import OpenAI

    client = OpenAI(api_key=settings.OPENAI_API_KEY, timeout=timeout)

    messages_content = []

    if images_b64:
        for b64 in images_b64:
            messages_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"},
            })

    if user_message:
        messages_content.append({"type": "text", "text": user_message})

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": messages_content},
        ],
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=4096,
    )
    return response.choices[0].message.content


def _call_anthropic(
    system_prompt: str,
    user_message: str,
    images_b64: list,
    model: str,
    timeout: int,
) -> str:
    """Call Anthropic Claude API with optional vision input."""
    import anthropic

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    content = []
    for b64 in images_b64:
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": b64},
        })

    if user_message:
        content.append({"type": "text", "text": user_message})

    response = client.messages.create(
        model=model,
        system=system_prompt,
        messages=[{"role": "user", "content": content}],
        max_tokens=4096,
    )
    return response.content[0].text


def _call_google(
    system_prompt: str,
    user_message: str,
    images_b64: list,
    model: str,
    timeout: int,
) -> str:
    """Call Google Gemini API using the new google-genai SDK."""
    import base64
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.GOOGLE_API_KEY)

    # Build content parts: images first, then combined text prompt
    full_prompt = system_prompt + "\n\n" + user_message
    parts = []

    for b64 in images_b64:
        img_bytes = base64.b64decode(b64)
        parts.append(
            types.Part.from_bytes(data=img_bytes, mime_type="image/png")
        )

    parts.append(types.Part.from_text(text=full_prompt))

    response = client.models.generate_content(
        model=model,
        contents=parts,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0,
        ),
    )
    return response.text


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

PROMPTS = {
    "invoice": INVOICE_SYSTEM_PROMPT,
    "balance_sheet": BALANCE_SHEET_SYSTEM_PROMPT,
    "profit_and_loss": PROFIT_AND_LOSS_SYSTEM_PROMPT,
    "cash_flow_statement": CASH_FLOW_SYSTEM_PROMPT,
}


def extract_document(
    doc: NormalizedDocument,
    document_type: str,
    document_name: str,
) -> Dict[str, Any]:
    """
    Send document content to configured LLM and return parsed JSON extraction.

    Args:
        doc: NormalizedDocument from OCR service
        document_type: invoice | balance_sheet | profit_and_loss | cash_flow_statement
        document_name: for logging

    Returns:
        dict: parsed JSON from LLM response

    Raises:
        RuntimeError: on LLM failure after retries
    """
    system_prompt = PROMPTS.get(document_type, PROMPTS["invoice"])
    provider = settings.AI_PROVIDER.lower()
    model = settings.AI_MODEL
    timeout = settings.AI_TIMEOUT_SECONDS
    max_retries = settings.AI_MAX_RETRIES

    # Build user message from available content
    if doc.raw_text and len(doc.raw_text.strip()) > 50:
        user_message = (
            f"Document name: {document_name}\n"
            f"Document type: {document_type}\n\n"
            f"DOCUMENT TEXT:\n{doc.raw_text}\n\n"
            "Extract all financial data according to the JSON schema above."
        )
    else:
        user_message = (
            f"Document name: {document_name}\n"
            f"Document type: {document_type}\n\n"
            "Extract all financial data from the document image(s) according to the JSON schema above."
        )

    images_b64 = doc.page_images_b64 if doc.is_scanned else []

    logger.info(
        "ai_extraction_start",
        document=document_name,
        doc_type=document_type,
        provider=provider,
        model=model,
        images_count=len(images_b64),
        has_text=bool(doc.raw_text.strip()),
    )

    last_error = None
    for attempt in range(1, max_retries + 2):
        try:
            start = time.time()

            if provider == "openai":
                raw = _call_openai(system_prompt, user_message, images_b64, model, timeout)
            elif provider == "anthropic":
                raw = _call_anthropic(system_prompt, user_message, images_b64, model, timeout)
            elif provider == "google":
                raw = _call_google(system_prompt, user_message, images_b64, model, timeout)
            else:
                raise ValueError(f"Unknown AI provider: {provider}")

            elapsed_ms = int((time.time() - start) * 1000)
            logger.info(
                "ai_extraction_complete",
                document=document_name,
                attempt=attempt,
                elapsed_ms=elapsed_ms,
            )

            # Parse JSON response
            parsed = _parse_json_response(raw)
            return parsed

        except Exception as exc:
            last_error = exc
            logger.warning(
                "ai_extraction_error",
                document=document_name,
                attempt=attempt,
                error=str(exc)[:200],
            )
            if attempt <= max_retries:
                time.sleep(1 * attempt)  # simple backoff

    raise RuntimeError(f"AI extraction failed after {max_retries + 1} attempts: {last_error}")


def _parse_json_response(raw: str) -> Dict[str, Any]:
    """
    Parse JSON from LLM response, handling markdown code blocks.
    """
    if not raw:
        return {}

    text = raw.strip()

    # Strip markdown code blocks if present
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        # Try to find JSON object in the response
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
        raise ValueError(f"LLM returned invalid JSON: {exc}") from exc
