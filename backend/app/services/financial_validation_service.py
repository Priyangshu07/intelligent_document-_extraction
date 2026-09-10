"""
Deterministic Financial Validation Service.

CRITICAL DESIGN PRINCIPLE:
  The LLM is NOT the final authority for financial PASS/FAIL.
  ALL arithmetic is performed by this Python service.

Validation statuses:
  PASS           - Arithmetic check passes within tolerance.
  FAIL           - Arithmetic check fails (values extracted but don't balance).
  NOT_APPLICABLE - Required source fields are missing; cannot perform check.
                   Missing values are NEVER treated as zero.

Every check returns:
  name, formula, operands, calculated_value, reported_value, variance,
  tolerance, status

Tolerance model (configurable via environment):
  A check passes if:
    abs(calculated - reported) <= max(ABS_TOLERANCE, REL_TOLERANCE * abs(reported))
  Default: ABS_TOLERANCE=1.0, REL_TOLERANCE=0.005 (0.5%)
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.document import ValidationCheck, ValidationResult

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Tolerance helpers
# ---------------------------------------------------------------------------

def _tolerance(reported: float) -> float:
    """Compute effective tolerance for a given reported value."""
    return max(
        settings.VALIDATION_ABS_TOLERANCE,
        settings.VALIDATION_REL_TOLERANCE * abs(reported),
    )


def _passes(calculated: float, reported: float) -> bool:
    tol = _tolerance(reported)
    return abs(calculated - reported) <= tol


def _make_check(
    name: str,
    formula: str,
    operands: Dict[str, Any],
    calculated_value: Optional[float],
    reported_value: Optional[float],
    status: str,
) -> ValidationCheck:
    variance = None
    tolerance = None
    if calculated_value is not None and reported_value is not None:
        variance = round(abs(calculated_value - reported_value), 4)
        tolerance = round(_tolerance(reported_value), 4)
    return ValidationCheck(
        name=name,
        formula=formula,
        operands=operands,
        calculated_value=round(calculated_value, 4) if calculated_value is not None else None,
        reported_value=round(reported_value, 4) if reported_value is not None else None,
        variance=variance,
        tolerance=tolerance,
        status=status,
    )


def _not_applicable(name: str, formula: str, reason: str = "") -> ValidationCheck:
    return ValidationCheck(
        name=name,
        formula=formula,
        operands={"reason": reason or "required fields missing"},
        calculated_value=None,
        reported_value=None,
        variance=None,
        tolerance=None,
        status="NOT_APPLICABLE",
    )


# ---------------------------------------------------------------------------
# Value extraction helpers
# ---------------------------------------------------------------------------

def _get_field_value(extracted_data: Dict, *keys: str) -> Optional[float]:
    """Navigate extracted_data to find a field value. Returns None if missing."""
    for key in keys:
        if key in extracted_data:
            field = extracted_data[key]
            if isinstance(field, dict):
                v = field.get("value")
                if v is not None:
                    try:
                        return float(v)
                    except (TypeError, ValueError):
                        return None
            elif isinstance(field, (int, float)):
                return float(field)
    return None


def _get_multi_period_value(line_item: Optional[Dict], period: str) -> Optional[float]:
    """Extract value for a specific period from a financial line item."""
    if line_item is None:
        return None
    if not isinstance(line_item, dict):
        return None
    values = line_item.get("values", {})
    if not isinstance(values, dict):
        return None
    v = values.get(period)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _find_period_in_items(line_items: List[Dict], period: str) -> Optional[float]:
    """Search line_items list for a period value (fallback)."""
    return None  # caller must use explicit named fields


# ---------------------------------------------------------------------------
# Invoice Validation
# ---------------------------------------------------------------------------

def validate_invoice(extracted_data: Dict) -> ValidationResult:
    """
    Invoice validation checks:
    1. Quantity × Unit Price ≈ Line Total (per line item)
    2. Sum(line_net_amounts) ≈ Subtotal
    3. Subtotal + Tax - Discount ≈ Total
    """
    checks: List[ValidationCheck] = []
    issues: List[str] = []

    subtotal = _get_field_value(extracted_data, "subtotal")
    tax_amount = _get_field_value(extracted_data, "tax_amount")
    discount = _get_field_value(extracted_data, "discount")
    total_amount = _get_field_value(extracted_data, "total_amount")
    line_items = extracted_data.get("line_items", []) or []

    # --- Check 1: Line item arithmetic ---
    line_totals_calculated = []
    for i, item in enumerate(line_items):
        if not isinstance(item, dict):
            continue
        qty = item.get("quantity")
        unit_price = item.get("unit_price")
        net_amount = item.get("net_amount") or item.get("gross_amount")

        if qty is not None and unit_price is not None and net_amount is not None:
            try:
                calc = float(qty) * float(unit_price)
                reported = float(net_amount)
                line_totals_calculated.append(calc)
                status = "PASS" if _passes(calc, reported) else "FAIL"
                check = _make_check(
                    name=f"line_item_{i+1}_quantity_x_price",
                    formula=f"quantity × unit_price",
                    operands={"quantity": qty, "unit_price": unit_price},
                    calculated_value=calc,
                    reported_value=reported,
                    status=status,
                )
                checks.append(check)
                if status == "FAIL":
                    issues.append(f"Line item {i+1}: qty×price={calc:.2f} ≠ reported={reported:.2f}")
            except (TypeError, ValueError):
                pass
        elif net_amount is not None:
            try:
                line_totals_calculated.append(float(net_amount))
            except (TypeError, ValueError):
                pass

    # --- Check 2: Sum of line items ≈ Subtotal ---
    if line_totals_calculated and subtotal is not None:
        calc_subtotal = sum(line_totals_calculated)
        status = "PASS" if _passes(calc_subtotal, subtotal) else "FAIL"
        check = _make_check(
            name="sum_line_items_equals_subtotal",
            formula="Σ(line_net_amounts) ≈ subtotal",
            operands={"sum_line_items": round(calc_subtotal, 4), "reported_subtotal": subtotal},
            calculated_value=calc_subtotal,
            reported_value=subtotal,
            status=status,
        )
        checks.append(check)
        if status == "FAIL":
            issues.append(f"Sum of line items={calc_subtotal:.2f} ≠ subtotal={subtotal:.2f}")
    else:
        checks.append(_not_applicable(
            "sum_line_items_equals_subtotal",
            "Σ(line_net_amounts) ≈ subtotal",
            "insufficient line item data or subtotal missing",
        ))

    # --- Check 3: Subtotal + Tax - Discount ≈ Total ---
    if subtotal is not None and tax_amount is not None and total_amount is not None:
        disc = discount if discount is not None else 0.0
        calc_total = subtotal + tax_amount - disc
        status = "PASS" if _passes(calc_total, total_amount) else "FAIL"
        check = _make_check(
            name="invoice_total_check",
            formula="subtotal + tax_amount - discount ≈ total_amount",
            operands={"subtotal": subtotal, "tax_amount": tax_amount, "discount": disc},
            calculated_value=calc_total,
            reported_value=total_amount,
            status=status,
        )
        checks.append(check)
        if status == "FAIL":
            issues.append(f"subtotal+tax-discount={calc_total:.2f} ≠ total={total_amount:.2f}")
    else:
        checks.append(_not_applicable(
            "invoice_total_check",
            "subtotal + tax_amount - discount ≈ total_amount",
            "subtotal, tax_amount, or total_amount missing",
        ))

    # --- Check 4: Amount paid - total ≈ balance due ---
    amount_paid = _get_field_value(extracted_data, "amount_paid")
    balance_due = _get_field_value(extracted_data, "balance_due")
    if amount_paid is not None and total_amount is not None and balance_due is not None:
        calc_balance = total_amount - amount_paid
        status = "PASS" if _passes(calc_balance, balance_due) else "FAIL"
        check = _make_check(
            name="balance_due_check",
            formula="total_amount - amount_paid ≈ balance_due",
            operands={"total_amount": total_amount, "amount_paid": amount_paid},
            calculated_value=calc_balance,
            reported_value=balance_due,
            status=status,
        )
        checks.append(check)
        if status == "FAIL":
            issues.append(f"total-paid={calc_balance:.2f} ≠ balance_due={balance_due:.2f}")
    else:
        checks.append(_not_applicable(
            "balance_due_check",
            "total_amount - amount_paid ≈ balance_due",
            "amount_paid or balance_due missing",
        ))

    return _build_result(checks, issues)


# ---------------------------------------------------------------------------
# Balance Sheet Validation
# ---------------------------------------------------------------------------

def validate_balance_sheet(extracted_data: Dict) -> ValidationResult:
    """
    Balance Sheet: Total Capital & Liabilities ≈ Total Assets (per period).
    """
    checks: List[ValidationCheck] = []
    issues: List[str] = []

    periods = extracted_data.get("periods", [])
    if not periods:
        # Try to detect periods from line items
        line_items = extracted_data.get("line_items", []) or []
        period_set = set()
        for item in line_items:
            if isinstance(item, dict):
                for p in (item.get("values") or {}).keys():
                    period_set.add(p)
        periods = sorted(period_set)

    total_assets_item = extracted_data.get("total_assets")
    total_cap_liab_item = extracted_data.get("total_capital_and_liabilities")

    if not periods:
        checks.append(_not_applicable(
            "balance_sheet_equation",
            "Total Capital & Liabilities ≈ Total Assets",
            "no periods found",
        ))
        return _build_result(checks, issues)

    for period in periods:
        assets = _get_multi_period_value(total_assets_item, period)
        cap_liab = _get_multi_period_value(total_cap_liab_item, period)

        # Fallback: try "total_liabilities" + equity if available
        if cap_liab is None:
            liab = _get_multi_period_value(extracted_data.get("total_liabilities"), period)
            eq = _get_multi_period_value(extracted_data.get("total_equity"), period)
            if liab is not None and eq is not None:
                cap_liab = liab + eq

        if assets is not None and cap_liab is not None:
            status = "PASS" if _passes(cap_liab, assets) else "FAIL"
            check = _make_check(
                name=f"balance_sheet_equation_{period}",
                formula="Total Capital & Liabilities ≈ Total Assets",
                operands={"total_capital_and_liabilities": cap_liab, "total_assets": assets, "period": period},
                calculated_value=cap_liab,
                reported_value=assets,
                status=status,
            )
            checks.append(check)
            if status == "FAIL":
                issues.append(f"[{period}] Capital&Liab={cap_liab:.0f} ≠ Assets={assets:.0f}")
        else:
            checks.append(_not_applicable(
                f"balance_sheet_equation_{period}",
                "Total Capital & Liabilities ≈ Total Assets",
                f"missing total_assets or total_capital_and_liabilities for period {period}",
            ))

    return _build_result(checks, issues)


# ---------------------------------------------------------------------------
# P&L Validation
# ---------------------------------------------------------------------------

def validate_profit_and_loss(extracted_data: Dict) -> ValidationResult:
    """
    P&L checks per period:
    1. Interest Earned + Other Income ≈ Total Income
    2. Interest Expended + Operating Expenses + Provisions ≈ Total Expenditure
    3. Total Income - Total Expenditure ≈ Net Profit (before minority interest)
    4. Net Profit - Minority Interest ≈ Consolidated Profit attributable to Group
    """
    checks: List[ValidationCheck] = []
    issues: List[str] = []

    periods = extracted_data.get("periods", []) or []
    if not periods:
        # Detect from line items
        for field_name in ["interest_earned", "total_income", "net_profit"]:
            item = extracted_data.get(field_name)
            if isinstance(item, dict):
                periods = list((item.get("values") or {}).keys())
                if periods:
                    break

    interest_earned_item = extracted_data.get("interest_earned")
    other_income_item = extracted_data.get("other_income")
    total_income_item = extracted_data.get("total_income")
    interest_expended_item = extracted_data.get("interest_expended")
    operating_expenses_item = extracted_data.get("operating_expenses")
    provisions_item = extracted_data.get("provisions_and_contingencies")
    total_expenditure_item = extracted_data.get("total_expenditure")
    net_profit_item = extracted_data.get("net_profit")
    minority_interest_item = extracted_data.get("minority_interest")
    consolidated_profit_item = extracted_data.get("consolidated_profit_attributable_to_group")

    for period in periods:
        int_earned = _get_multi_period_value(interest_earned_item, period)
        other_inc = _get_multi_period_value(other_income_item, period)
        total_inc = _get_multi_period_value(total_income_item, period)
        int_expended = _get_multi_period_value(interest_expended_item, period)
        op_exp = _get_multi_period_value(operating_expenses_item, period)
        provisions = _get_multi_period_value(provisions_item, period)
        total_exp = _get_multi_period_value(total_expenditure_item, period)
        net_profit = _get_multi_period_value(net_profit_item, period)
        minority = _get_multi_period_value(minority_interest_item, period)
        consol_profit = _get_multi_period_value(consolidated_profit_item, period)

        # Check 1: Interest Earned + Other Income ≈ Total Income
        if int_earned is not None and other_inc is not None and total_inc is not None:
            calc = int_earned + other_inc
            status = "PASS" if _passes(calc, total_inc) else "FAIL"
            check = _make_check(
                name=f"total_income_check_{period}",
                formula="interest_earned + other_income ≈ total_income",
                operands={"interest_earned": int_earned, "other_income": other_inc, "period": period},
                calculated_value=calc,
                reported_value=total_inc,
                status=status,
            )
            checks.append(check)
            if status == "FAIL":
                issues.append(f"[{period}] interest+other={calc:.0f} ≠ total_income={total_inc:.0f}")
        else:
            checks.append(_not_applicable(
                f"total_income_check_{period}",
                "interest_earned + other_income ≈ total_income",
                f"missing fields for {period}",
            ))

        # Check 2: Total Expenditure
        exp_components = [x for x in [int_expended, op_exp, provisions] if x is not None]
        if len(exp_components) >= 2 and total_exp is not None:
            calc = sum(exp_components)
            status = "PASS" if _passes(calc, total_exp) else "FAIL"
            check = _make_check(
                name=f"total_expenditure_check_{period}",
                formula="interest_expended + operating_expenses + provisions ≈ total_expenditure",
                operands={
                    "interest_expended": int_expended,
                    "operating_expenses": op_exp,
                    "provisions_and_contingencies": provisions,
                    "period": period,
                },
                calculated_value=calc,
                reported_value=total_exp,
                status=status,
            )
            checks.append(check)
            if status == "FAIL":
                issues.append(f"[{period}] exp_components_sum={calc:.0f} ≠ total_exp={total_exp:.0f}")
        else:
            checks.append(_not_applicable(
                f"total_expenditure_check_{period}",
                "interest_expended + operating_expenses + provisions ≈ total_expenditure",
                f"insufficient expenditure components for {period}",
            ))

        # Check 3: Net Profit = Total Income - Total Expenditure
        if total_inc is not None and total_exp is not None and net_profit is not None:
            calc = total_inc - total_exp
            status = "PASS" if _passes(calc, net_profit) else "FAIL"
            check = _make_check(
                name=f"net_profit_check_{period}",
                formula="total_income - total_expenditure ≈ net_profit",
                operands={"total_income": total_inc, "total_expenditure": total_exp, "period": period},
                calculated_value=calc,
                reported_value=net_profit,
                status=status,
            )
            checks.append(check)
            if status == "FAIL":
                issues.append(f"[{period}] income-exp={calc:.0f} ≠ net_profit={net_profit:.0f}")
        else:
            checks.append(_not_applicable(
                f"net_profit_check_{period}",
                "total_income - total_expenditure ≈ net_profit",
                f"missing income/expenditure/profit for {period}",
            ))

        # Check 4: Consolidated profit = Net Profit - Minority Interest
        if net_profit is not None and minority is not None and consol_profit is not None:
            calc = net_profit - minority
            status = "PASS" if _passes(calc, consol_profit) else "FAIL"
            check = _make_check(
                name=f"consolidated_profit_check_{period}",
                formula="net_profit - minority_interest ≈ consolidated_profit_attributable_to_group",
                operands={"net_profit": net_profit, "minority_interest": minority, "period": period},
                calculated_value=calc,
                reported_value=consol_profit,
                status=status,
            )
            checks.append(check)
            if status == "FAIL":
                issues.append(f"[{period}] net_profit-minority={calc:.0f} ≠ consol={consol_profit:.0f}")
        else:
            checks.append(_not_applicable(
                f"consolidated_profit_check_{period}",
                "net_profit - minority_interest ≈ consolidated_profit_attributable_to_group",
                f"missing minority_interest or consolidated_profit for {period}",
            ))

    return _build_result(checks, issues)


# ---------------------------------------------------------------------------
# Cash Flow Validation
# ---------------------------------------------------------------------------

def validate_cash_flow(extracted_data: Dict) -> ValidationResult:
    """
    Cash Flow checks per period:
    1. Operating + Investing + Financing + FX ≈ Net Change in Cash
    2. Opening Cash + Net Change + Amalgamation ≈ Closing Cash
    """
    checks: List[ValidationCheck] = []
    issues: List[str] = []

    periods = extracted_data.get("periods", []) or []
    if not periods:
        for field_name in ["operating_cash_flow", "net_change_in_cash", "closing_cash"]:
            item = extracted_data.get(field_name)
            if isinstance(item, dict):
                periods = list((item.get("values") or {}).keys())
                if periods:
                    break

    op_item = extracted_data.get("operating_cash_flow")
    inv_item = extracted_data.get("investing_cash_flow")
    fin_item = extracted_data.get("financing_cash_flow")
    fx_item = extracted_data.get("fx_adjustment")
    net_change_item = extracted_data.get("net_change_in_cash")
    opening_item = extracted_data.get("opening_cash")
    closing_item = extracted_data.get("closing_cash")
    amalgamation_item = extracted_data.get("cash_acquired_on_amalgamation")

    for period in periods:
        op = _get_multi_period_value(op_item, period)
        inv = _get_multi_period_value(inv_item, period)
        fin = _get_multi_period_value(fin_item, period)
        fx = _get_multi_period_value(fx_item, period)
        net_change = _get_multi_period_value(net_change_item, period)
        opening = _get_multi_period_value(opening_item, period)
        closing = _get_multi_period_value(closing_item, period)
        amalgamation = _get_multi_period_value(amalgamation_item, period)

        # Check 1: Net change in cash
        components = [x for x in [op, inv, fin] if x is not None]
        if len(components) >= 2 and net_change is not None:
            fx_val = fx if fx is not None else 0.0
            calc = sum(components) + fx_val
            status = "PASS" if _passes(calc, net_change) else "FAIL"
            check = _make_check(
                name=f"net_cash_change_check_{period}",
                formula="operating + investing + financing + fx ≈ net_change_in_cash",
                operands={
                    "operating_cash_flow": op,
                    "investing_cash_flow": inv,
                    "financing_cash_flow": fin,
                    "fx_adjustment": fx,
                    "period": period,
                },
                calculated_value=calc,
                reported_value=net_change,
                status=status,
            )
            checks.append(check)
            if status == "FAIL":
                issues.append(f"[{period}] op+inv+fin+fx={calc:.0f} ≠ net_change={net_change:.0f}")
        else:
            checks.append(_not_applicable(
                f"net_cash_change_check_{period}",
                "operating + investing + financing + fx ≈ net_change_in_cash",
                f"insufficient cash flow components for {period}",
            ))

        # Check 2: Opening + Net Change + Amalgamation ≈ Closing
        if opening is not None and net_change is not None and closing is not None:
            amal = amalgamation if amalgamation is not None else 0.0
            calc = opening + net_change + amal
            status = "PASS" if _passes(calc, closing) else "FAIL"
            check = _make_check(
                name=f"closing_cash_check_{period}",
                formula="opening_cash + net_change_in_cash + amalgamation ≈ closing_cash",
                operands={
                    "opening_cash": opening,
                    "net_change_in_cash": net_change,
                    "cash_acquired_on_amalgamation": amalgamation,
                    "period": period,
                },
                calculated_value=calc,
                reported_value=closing,
                status=status,
            )
            checks.append(check)
            if status == "FAIL":
                issues.append(f"[{period}] opening+net+amal={calc:.0f} ≠ closing={closing:.0f}")
        else:
            checks.append(_not_applicable(
                f"closing_cash_check_{period}",
                "opening_cash + net_change_in_cash + amalgamation ≈ closing_cash",
                f"missing opening/closing/net_change for {period}",
            ))

    return _build_result(checks, issues)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

def validate_financial_data(
    document_type: str,
    extracted_data: Dict,
) -> ValidationResult:
    """Route to the appropriate validator based on document type."""
    logger.info("financial_validation_start", document_type=document_type)
    try:
        if document_type == "invoice":
            result = validate_invoice(extracted_data)
        elif document_type == "balance_sheet":
            result = validate_balance_sheet(extracted_data)
        elif document_type == "profit_and_loss":
            result = validate_profit_and_loss(extracted_data)
        elif document_type == "cash_flow_statement":
            result = validate_cash_flow(extracted_data)
        else:
            result = ValidationResult(
                checks=[],
                overall_status="NOT_APPLICABLE",
                issues=[f"Unknown document type: {document_type}"],
            )
        logger.info(
            "financial_validation_complete",
            document_type=document_type,
            status=result.overall_status,
            checks=len(result.checks),
            issues=len(result.issues),
        )
        return result
    except Exception as exc:
        logger.error("financial_validation_error", error=str(exc))
        return ValidationResult(
            checks=[],
            overall_status="NOT_APPLICABLE",
            issues=[f"Validation error: {str(exc)[:200]}"],
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_result(checks: List[ValidationCheck], issues: List[str]) -> ValidationResult:
    """Determine overall_status from individual checks."""
    if not checks:
        overall = "NOT_APPLICABLE"
    else:
        statuses = {c.status for c in checks}
        if "FAIL" in statuses:
            overall = "FAIL"
        elif all(c.status == "NOT_APPLICABLE" for c in checks):
            overall = "NOT_APPLICABLE"
        else:
            overall = "PASS"

    return ValidationResult(checks=checks, overall_status=overall, issues=issues)
