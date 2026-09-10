"""
Tests for financial validation service.
These are pure unit tests — no AI, no database, no network.
"""
import pytest
from app.services.financial_validation_service import (
    validate_invoice,
    validate_balance_sheet,
    validate_profit_and_loss,
    validate_cash_flow,
)


# ============================================================
# Invoice Tests
# ============================================================

class TestInvoiceValidation:

    def test_invoice_pass_all_fields(self):
        data = {
            "subtotal": {"value": 100.0},
            "tax_amount": {"value": 10.0},
            "discount": {"value": 0.0},
            "total_amount": {"value": 110.0},
            "line_items": [
                {"quantity": 2, "unit_price": 50.0, "net_amount": 100.0}
            ]
        }
        result = validate_invoice(data)
        assert result.overall_status == "PASS"
        checks = {c.name: c for c in result.checks}
        assert checks["invoice_total_check"].status == "PASS"
        assert checks["sum_line_items_equals_subtotal"].status == "PASS"

    def test_invoice_fail_total_mismatch(self):
        data = {
            "subtotal": {"value": 100.0},
            "tax_amount": {"value": 10.0},
            "discount": {"value": 0.0},
            "total_amount": {"value": 200.0},  # WRONG
            "line_items": []
        }
        result = validate_invoice(data)
        assert result.overall_status == "FAIL"
        checks = {c.name: c for c in result.checks}
        assert checks["invoice_total_check"].status == "FAIL"

    def test_invoice_not_applicable_missing_total(self):
        data = {
            "subtotal": {"value": 100.0},
            "tax_amount": {"value": 10.0},
            # total_amount missing
            "line_items": []
        }
        result = validate_invoice(data)
        checks = {c.name: c for c in result.checks}
        assert checks["invoice_total_check"].status == "NOT_APPLICABLE"

    def test_invoice_with_discount(self):
        data = {
            "subtotal": {"value": 200.0},
            "tax_amount": {"value": 20.0},
            "discount": {"value": 10.0},
            "total_amount": {"value": 210.0},  # 200 + 20 - 10
            "line_items": []
        }
        result = validate_invoice(data)
        checks = {c.name: c for c in result.checks}
        assert checks["invoice_total_check"].status == "PASS"

    def test_invoice_line_item_qty_x_price(self):
        data = {
            "subtotal": {"value": 50.0},
            "tax_amount": {"value": 5.0},
            "total_amount": {"value": 55.0},
            "line_items": [
                {"quantity": 5, "unit_price": 10.0, "net_amount": 50.0}
            ]
        }
        result = validate_invoice(data)
        checks = {c.name: c for c in result.checks}
        assert checks["line_item_1_quantity_x_price"].status == "PASS"

    def test_invoice_line_item_fail(self):
        data = {
            "subtotal": {"value": 50.0},
            "tax_amount": {"value": 5.0},
            "total_amount": {"value": 55.0},
            "line_items": [
                {"quantity": 5, "unit_price": 10.0, "net_amount": 99.0}  # WRONG
            ]
        }
        result = validate_invoice(data)
        checks = {c.name: c for c in result.checks}
        assert checks["line_item_1_quantity_x_price"].status == "FAIL"

    def test_invoice_null_fields_not_applicable(self):
        data = {"line_items": []}
        result = validate_invoice(data)
        statuses = {c.status for c in result.checks}
        assert "NOT_APPLICABLE" in statuses
        assert "FAIL" not in statuses

    def test_invoice_tolerance_within_range(self):
        """Values within tolerance (0.5%) should PASS."""
        data = {
            "subtotal": {"value": 10000.0},
            "tax_amount": {"value": 1000.0},
            "discount": {"value": 0.0},
            "total_amount": {"value": 11000.5},  # within 0.5%
            "line_items": []
        }
        result = validate_invoice(data)
        checks = {c.name: c for c in result.checks}
        assert checks["invoice_total_check"].status == "PASS"


# ============================================================
# Balance Sheet Tests
# ============================================================

class TestBalanceSheetValidation:

    def test_balance_sheet_pass(self):
        data = {
            "periods": ["31-Mar-17"],
            "total_assets": {"label": "Total Assets", "values": {"31-Mar-17": 1000000.0}},
            "total_capital_and_liabilities": {"label": "Total", "values": {"31-Mar-17": 1000000.0}},
        }
        result = validate_balance_sheet(data)
        assert result.overall_status == "PASS"

    def test_balance_sheet_fail(self):
        data = {
            "periods": ["31-Mar-17"],
            "total_assets": {"label": "Total Assets", "values": {"31-Mar-17": 1000000.0}},
            "total_capital_and_liabilities": {"label": "Total", "values": {"31-Mar-17": 900000.0}},  # WRONG
        }
        result = validate_balance_sheet(data)
        assert result.overall_status == "FAIL"

    def test_balance_sheet_comparative_periods(self):
        data = {
            "periods": ["31-Mar-17", "31-Mar-16"],
            "total_assets": {"values": {"31-Mar-17": 1000000.0, "31-Mar-16": 900000.0}},
            "total_capital_and_liabilities": {"values": {"31-Mar-17": 1000000.0, "31-Mar-16": 900000.0}},
        }
        result = validate_balance_sheet(data)
        assert result.overall_status == "PASS"
        assert len(result.checks) == 2  # one per period

    def test_balance_sheet_not_applicable_no_data(self):
        data = {"periods": ["31-Mar-17"]}
        result = validate_balance_sheet(data)
        checks = {c.status for c in result.checks}
        assert "NOT_APPLICABLE" in checks

    def test_balance_sheet_missing_period_not_applicable(self):
        data = {
            "periods": ["31-Mar-17"],
            "total_assets": {"values": {}},  # empty
            "total_capital_and_liabilities": {"values": {}},
        }
        result = validate_balance_sheet(data)
        checks = {c.status for c in result.checks}
        assert "NOT_APPLICABLE" in checks


# ============================================================
# P&L Tests
# ============================================================

class TestProfitAndLossValidation:

    def test_pl_total_income_pass(self):
        data = {
            "periods": ["31-Mar-17"],
            "interest_earned": {"values": {"31-Mar-17": 800000.0}},
            "other_income": {"values": {"31-Mar-17": 200000.0}},
            "total_income": {"values": {"31-Mar-17": 1000000.0}},
        }
        result = validate_profit_and_loss(data)
        checks = {c.name: c for c in result.checks}
        assert checks["total_income_check_31-Mar-17"].status == "PASS"

    def test_pl_total_income_fail(self):
        data = {
            "periods": ["31-Mar-17"],
            "interest_earned": {"values": {"31-Mar-17": 800000.0}},
            "other_income": {"values": {"31-Mar-17": 200000.0}},
            "total_income": {"values": {"31-Mar-17": 500000.0}},  # WRONG
        }
        result = validate_profit_and_loss(data)
        checks = {c.name: c for c in result.checks}
        assert checks["total_income_check_31-Mar-17"].status == "FAIL"

    def test_pl_net_profit_check(self):
        data = {
            "periods": ["31-Mar-17"],
            "interest_earned": {"values": {"31-Mar-17": 900000.0}},
            "other_income": {"values": {"31-Mar-17": 100000.0}},
            "total_income": {"values": {"31-Mar-17": 1000000.0}},
            "interest_expended": {"values": {"31-Mar-17": 500000.0}},
            "operating_expenses": {"values": {"31-Mar-17": 200000.0}},
            "provisions_and_contingencies": {"values": {"31-Mar-17": 100000.0}},
            "total_expenditure": {"values": {"31-Mar-17": 800000.0}},
            "net_profit": {"values": {"31-Mar-17": 200000.0}},
        }
        result = validate_profit_and_loss(data)
        checks = {c.name: c for c in result.checks}
        assert checks["net_profit_check_31-Mar-17"].status == "PASS"

    def test_pl_negative_values(self):
        """Negative minority interest should be handled correctly."""
        data = {
            "periods": ["31-Mar-17"],
            "net_profit": {"values": {"31-Mar-17": 200000.0}},
            "minority_interest": {"values": {"31-Mar-17": -50000.0}},  # negative
            "consolidated_profit_attributable_to_group": {"values": {"31-Mar-17": 250000.0}},
        }
        result = validate_profit_and_loss(data)
        checks = {c.name: c for c in result.checks}
        # 200000 - (-50000) = 250000
        assert checks["consolidated_profit_check_31-Mar-17"].status == "PASS"


# ============================================================
# Cash Flow Tests
# ============================================================

class TestCashFlowValidation:

    def test_cash_flow_pass(self):
        data = {
            "periods": ["31-Mar-17"],
            "operating_cash_flow": {"values": {"31-Mar-17": 500000.0}},
            "investing_cash_flow": {"values": {"31-Mar-17": -200000.0}},
            "financing_cash_flow": {"values": {"31-Mar-17": -100000.0}},
            "net_change_in_cash": {"values": {"31-Mar-17": 200000.0}},
            "opening_cash": {"values": {"31-Mar-17": 300000.0}},
            "closing_cash": {"values": {"31-Mar-17": 500000.0}},
        }
        result = validate_cash_flow(data)
        assert result.overall_status == "PASS"

    def test_cash_flow_negative_bracketed(self):
        """Test that negative values are handled correctly."""
        data = {
            "periods": ["31-Mar-17"],
            "operating_cash_flow": {"values": {"31-Mar-17": 100000.0}},
            "investing_cash_flow": {"values": {"31-Mar-17": -80000.0}},  # (80000) → -80000
            "financing_cash_flow": {"values": {"31-Mar-17": -10000.0}},
            "net_change_in_cash": {"values": {"31-Mar-17": 10000.0}},
            "opening_cash": {"values": {"31-Mar-17": 50000.0}},
            "closing_cash": {"values": {"31-Mar-17": 60000.0}},
        }
        result = validate_cash_flow(data)
        assert result.overall_status == "PASS"

    def test_cash_flow_fail(self):
        data = {
            "periods": ["31-Mar-17"],
            "operating_cash_flow": {"values": {"31-Mar-17": 100000.0}},
            "investing_cash_flow": {"values": {"31-Mar-17": -50000.0}},
            "financing_cash_flow": {"values": {"31-Mar-17": -20000.0}},
            "net_change_in_cash": {"values": {"31-Mar-17": 999999.0}},  # WRONG
            "opening_cash": {"values": {"31-Mar-17": 50000.0}},
            "closing_cash": {"values": {"31-Mar-17": 80000.0}},
        }
        result = validate_cash_flow(data)
        assert result.overall_status == "FAIL"

    def test_cash_flow_not_applicable(self):
        data = {"periods": ["31-Mar-17"]}
        result = validate_cash_flow(data)
        statuses = {c.status for c in result.checks}
        assert "NOT_APPLICABLE" in statuses

    def test_cash_flow_with_fx_adjustment(self):
        data = {
            "periods": ["31-Mar-17"],
            "operating_cash_flow": {"values": {"31-Mar-17": 500000.0}},
            "investing_cash_flow": {"values": {"31-Mar-17": -200000.0}},
            "financing_cash_flow": {"values": {"31-Mar-17": -100000.0}},
            "fx_adjustment": {"values": {"31-Mar-17": 5000.0}},
            "net_change_in_cash": {"values": {"31-Mar-17": 205000.0}},  # 500-200-100+5=205
            "opening_cash": {"values": {"31-Mar-17": 100000.0}},
            "closing_cash": {"values": {"31-Mar-17": 305000.0}},
        }
        result = validate_cash_flow(data)
        assert result.overall_status == "PASS"

    def test_cash_flow_comparative_periods(self):
        data = {
            "periods": ["31-Mar-17", "31-Mar-16"],
            "operating_cash_flow": {"values": {"31-Mar-17": 500.0, "31-Mar-16": 400.0}},
            "investing_cash_flow": {"values": {"31-Mar-17": -200.0, "31-Mar-16": -150.0}},
            "financing_cash_flow": {"values": {"31-Mar-17": -100.0, "31-Mar-16": -80.0}},
            "net_change_in_cash": {"values": {"31-Mar-17": 200.0, "31-Mar-16": 170.0}},
            "opening_cash": {"values": {"31-Mar-17": 300.0, "31-Mar-16": 130.0}},
            "closing_cash": {"values": {"31-Mar-17": 500.0, "31-Mar-16": 300.0}},
        }
        result = validate_cash_flow(data)
        assert result.overall_status == "PASS"
        # Should have 4 checks (2 per period)
        assert len(result.checks) == 4
