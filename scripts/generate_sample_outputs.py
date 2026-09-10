#!/usr/bin/env python3
"""
Script to process all 4 sample reference documents through the live API
and save outputs to sample_outputs/ directory.

Usage:
  cd /Users/priyangshuadhikari/Desktop/intelligent_document_extraction
  python3 scripts/generate_sample_outputs.py

Requires: server running at http://localhost:8000
"""
import requests
import json
import os
import sys
from pathlib import Path

BASE_URL = "http://localhost:8000"
PROJECT_ROOT = Path(__file__).parent.parent
DATASET_ROOT = PROJECT_ROOT / "New Dataset"
OUTPUT_DIR = PROJECT_ROOT / "sample_outputs"

def process_document(file_path: Path, doc_type: str, label: str) -> dict:
    """Process a document through the API and return result."""
    print(f"\n📄 Processing {label}: {file_path.name}")
    
    with open(file_path, "rb") as f:
        resp = requests.post(
            f"{BASE_URL}/api/v1/documents/process",
            files={"file": (file_path.name, f, "application/octet-stream")},
            data={"document_type": doc_type},
            timeout=180,
        )
    
    if resp.status_code in (200, 422):
        result = resp.json()
        status = result.get("processing_status", "UNKNOWN")
        val_status = result.get("validation", {}).get("overall_status", "N/A")
        print(f"   Status: {status} | Validation: {val_status}")
        return result
    else:
        print(f"   ERROR {resp.status_code}: {resp.text[:200]}")
        return {"error": {"code": str(resp.status_code), "message": resp.text[:200]}}


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    # Verify server is running
    try:
        health = requests.get(f"{BASE_URL}/api/v1/health", timeout=5)
        print(f"✅ Server health: {health.json()}")
    except Exception as e:
        print(f"❌ Server not running at {BASE_URL}: {e}")
        sys.exit(1)
    
    # 1. Invoice
    invoice_dir = DATASET_ROOT / "Invoices"
    invoice_file = invoice_dir / "X51005361895.jpg"  # Use a clear sample
    result = process_document(invoice_file, "invoice", "Invoice")
    with open(OUTPUT_DIR / "invoice.json", "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"   Saved: sample_outputs/invoice.json")
    
    # 2. Balance Sheet
    bs_dir = DATASET_ROOT / "Balance Sheet"
    bs_file = bs_dir / "Consolidated Balance Sheet 2017.pdf"
    result = process_document(bs_file, "balance_sheet", "Balance Sheet")
    with open(OUTPUT_DIR / "balance_sheet.json", "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"   Saved: sample_outputs/balance_sheet.json")
    
    # 3. Profit & Loss
    pl_dir = DATASET_ROOT / "Profit & Loss"
    pl_file = pl_dir / "Consolidated Profit & Loss 2017.pdf"
    result = process_document(pl_file, "profit_and_loss", "Profit & Loss")
    with open(OUTPUT_DIR / "profit_and_loss.json", "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"   Saved: sample_outputs/profit_and_loss.json")
    
    # 4. Cash Flow
    cf_dir = DATASET_ROOT / "Cash Flows"
    cf_file = cf_dir / "Consolidated Cash Flow Statement 2017.pdf"
    result = process_document(cf_file, "cash_flow_statement", "Cash Flow Statement")
    with open(OUTPUT_DIR / "cash_flow.json", "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"   Saved: sample_outputs/cash_flow.json")
    
    print(f"\n✅ All sample outputs saved to sample_outputs/")


if __name__ == "__main__":
    main()
