"""
Pydantic schemas for structured extraction output.

Every meaningful extracted value carries:
  - value      : the extracted value (null if missing/not found)
  - page_number: source page (null if unknown)
  - evidence   : verbatim source text snippet (null if not available)

Financial statement line items carry an additional 'values' dict
keyed by period string (e.g. "31-Mar-17").

Rules enforced here:
  - NEVER invent missing values; use None.
  - Preserve original labels.
  - Preserve negative signs (parentheses → negative float during extraction).
  - Preserve units / currency from source.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, model_validator


# ---------------------------------------------------------------------------
# Universal field wrapper
# ---------------------------------------------------------------------------

class ExtractedField(BaseModel):
    """Generic extracted field with page grounding and evidence."""
    value: Optional[Any] = None
    page_number: Optional[int] = None
    evidence: Optional[str] = None


class ExtractedLineItem(BaseModel):
    """Invoice line item with full column preservation."""
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    unit_price: Optional[float] = None
    net_amount: Optional[float] = None
    tax_rate: Optional[float] = None
    tax_amount: Optional[float] = None
    gross_amount: Optional[float] = None
    page_number: Optional[int] = None
    evidence: Optional[str] = None


class FinancialLineItem(BaseModel):
    """Financial statement line item preserving original label and comparative periods."""
    label: str
    normalized_key: Optional[str] = None
    values: Dict[str, Optional[float]] = {}  # keyed by period string
    page_number: Optional[int] = None
    evidence: Optional[str] = None


# ---------------------------------------------------------------------------
# Invoice schema
# ---------------------------------------------------------------------------

class InvoiceExtraction(BaseModel):
    invoice_number: Optional[ExtractedField] = None
    invoice_date: Optional[ExtractedField] = None
    due_date: Optional[ExtractedField] = None
    vendor_name: Optional[ExtractedField] = None
    vendor_address: Optional[ExtractedField] = None
    vendor_tax_id: Optional[ExtractedField] = None
    customer_name: Optional[ExtractedField] = None
    customer_address: Optional[ExtractedField] = None
    customer_tax_id: Optional[ExtractedField] = None
    billing_address: Optional[ExtractedField] = None
    shipping_address: Optional[ExtractedField] = None
    purchase_order: Optional[ExtractedField] = None
    reference_number: Optional[ExtractedField] = None
    currency: Optional[ExtractedField] = None
    currency_symbol: Optional[ExtractedField] = None
    payment_terms: Optional[ExtractedField] = None
    IBAN: Optional[ExtractedField] = None
    subtotal: Optional[ExtractedField] = None
    tax_amount: Optional[ExtractedField] = None
    tax_rate: Optional[ExtractedField] = None
    discount: Optional[ExtractedField] = None
    shipping: Optional[ExtractedField] = None
    total_amount: Optional[ExtractedField] = None
    amount_paid: Optional[ExtractedField] = None
    balance_due: Optional[ExtractedField] = None
    notes: Optional[ExtractedField] = None
    line_items: List[ExtractedLineItem] = []
    tax_summary: Optional[List[Dict[str, Any]]] = None
    other_fields: Optional[Dict[str, ExtractedField]] = None


# ---------------------------------------------------------------------------
# Balance Sheet schema
# ---------------------------------------------------------------------------

class BalanceSheetExtraction(BaseModel):
    statement_title: Optional[ExtractedField] = None
    company_name: Optional[ExtractedField] = None
    statement_date: Optional[ExtractedField] = None
    currency: Optional[ExtractedField] = None
    unit: Optional[ExtractedField] = None
    periods: List[str] = []

    # Summary totals (multi-period)
    total_assets: Optional[FinancialLineItem] = None
    total_liabilities: Optional[FinancialLineItem] = None
    total_equity: Optional[FinancialLineItem] = None
    total_capital_and_liabilities: Optional[FinancialLineItem] = None

    # All raw line items extracted from the document
    line_items: List[FinancialLineItem] = []

    # Sections (dict of section_name -> list of line items)
    sections: Optional[Dict[str, List[FinancialLineItem]]] = None


# ---------------------------------------------------------------------------
# Profit & Loss schema
# ---------------------------------------------------------------------------

class ProfitAndLossExtraction(BaseModel):
    statement_title: Optional[ExtractedField] = None
    company_name: Optional[ExtractedField] = None
    periods: List[str] = []
    currency: Optional[ExtractedField] = None
    unit: Optional[ExtractedField] = None

    # Key summary fields (multi-period)
    interest_earned: Optional[FinancialLineItem] = None
    other_income: Optional[FinancialLineItem] = None
    total_income: Optional[FinancialLineItem] = None
    interest_expended: Optional[FinancialLineItem] = None
    operating_expenses: Optional[FinancialLineItem] = None
    provisions_and_contingencies: Optional[FinancialLineItem] = None
    total_expenditure: Optional[FinancialLineItem] = None
    net_profit: Optional[FinancialLineItem] = None
    minority_interest: Optional[FinancialLineItem] = None
    share_in_profits_of_associates: Optional[FinancialLineItem] = None
    consolidated_profit_attributable_to_group: Optional[FinancialLineItem] = None
    earnings_per_equity_share_basic: Optional[FinancialLineItem] = None
    earnings_per_equity_share_diluted: Optional[FinancialLineItem] = None

    # All raw line items
    line_items: List[FinancialLineItem] = []
    sections: Optional[Dict[str, List[FinancialLineItem]]] = None


# ---------------------------------------------------------------------------
# Cash Flow schema
# ---------------------------------------------------------------------------

class CashFlowExtraction(BaseModel):
    statement_title: Optional[ExtractedField] = None
    company_name: Optional[ExtractedField] = None
    periods: List[str] = []
    currency: Optional[ExtractedField] = None
    unit: Optional[ExtractedField] = None

    # Summary totals (multi-period)
    operating_cash_flow: Optional[FinancialLineItem] = None
    investing_cash_flow: Optional[FinancialLineItem] = None
    financing_cash_flow: Optional[FinancialLineItem] = None
    fx_adjustment: Optional[FinancialLineItem] = None
    net_change_in_cash: Optional[FinancialLineItem] = None
    opening_cash: Optional[FinancialLineItem] = None
    closing_cash: Optional[FinancialLineItem] = None
    cash_acquired_on_amalgamation: Optional[FinancialLineItem] = None

    # All line items
    line_items: List[FinancialLineItem] = []
    sections: Optional[Dict[str, List[FinancialLineItem]]] = None


# ---------------------------------------------------------------------------
# Union for routing
# ---------------------------------------------------------------------------

ExtractionResult = Union[InvoiceExtraction, BalanceSheetExtraction, ProfitAndLossExtraction, CashFlowExtraction]
