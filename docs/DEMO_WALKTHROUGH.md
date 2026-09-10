# Demo Walkthrough — 5–8 Minute Script

> Use this exact script during your NeoStats interview demo. Each step includes what to say AND what to do on screen.

---

## Pre-Demo Checklist
- [ ] Application is running (local or deployed)
- [ ] Browser open at `http://localhost:8000` (or live URL)
- [ ] Sample documents ready: invoice, balance sheet, P&L, cash flow
- [ ] Swagger at `http://localhost:8000/docs`
- [ ] GitHub repository open in another tab

---

## Step 1 — Open Frontend Dashboard (0:00–0:20)

**Action**: Open `http://localhost:8000`

**Say**: "This is FinDoc AI — a Financial Document Intelligence Platform I built for the case study. The dashboard shows all processed documents, processing status, and allows uploading new ones. Everything you see here comes from the real backend API — no fake frontend data."

---

## Step 2 — Show Dashboard Overview (0:20–0:40)

**Action**: Point to the stats row and document list

**Say**: "The stats row shows total processed documents, PASS count, and FAILED count — all queried live from PostgreSQL. The document table shows the document name, type, validation status, whether OCR was used, and when it was processed."

---

## Step 3 — Select Document Type (0:40–1:00)

**Action**: Click the document type dropdown

**Say**: "The user selects the document type manually — the system supports Invoice, Balance Sheet, Profit & Loss, and Cash Flow Statement. Automatic classification is not implemented — this was a design decision to keep the scope focused and the extraction more accurate, since each document type has a completely different extraction schema."

---

## Step 4 — Upload Invoice (1:00–1:30)

**Action**: Select "Invoice" from dropdown, drop an invoice JPG file, click Process

**Say**: "I'll upload one of the sample invoice images. The system accepts PDF, JPG, and PNG files up to 3 pages. Processing is happening now — the file is being validated, rendered for vision, sent to the AI, and validated."

*(Wait for processing — approximately 20–40 seconds)*

---

## Step 5 — Show Invoice Extraction (1:30–2:30)

**Action**: View result page — click Extraction tab

**Say**: "Here are the extracted invoice fields — invoice number, date, vendor, customer, currency, subtotal, tax, total. Notice each field has a page number and evidence — the exact text from the source document that supports this value. If a field wasn't found, it shows 'null — not found' in red rather than guessing a value."

**Point to evidence tags**: "This evidence grounding means an auditor can always trace any value back to its source page."

**Scroll to line items**: "All line items are extracted with their full column data — description, quantity, unit price, net amount, tax, and gross amount."

---

## Step 6 — Show Invoice Validation (2:30–3:00)

**Action**: Click Validation tab

**Say**: "This is the financial validation section. Four checks are run: quantity times unit price equals line total, sum of line items equals subtotal, subtotal plus tax minus discount equals total, and balance due check. Each check shows the formula, the actual operands used, the calculated value, the reported value, the variance, and the tolerance. This is pure Python arithmetic — the AI has no role in determining PASS or FAIL."

---

## Step 7 — Show Raw JSON (3:00–3:20)

**Action**: Click JSON tab

**Say**: "This is the complete raw JSON response from the API — exactly what the REST API returns. Evaluators can call `POST /api/v1/documents/process` directly and get this structure. The structure includes file validation, extracted data, completeness check, financial validation, and processing metadata."

---

## Step 8 — Return to Dashboard (3:20–3:30)

**Action**: Click ← Back

**Say**: "Back on the dashboard, the invoice now appears in the processed documents table."

---

## Step 9 — Process Balance Sheet (3:30–4:30)

**Action**: Upload "Consolidated Balance Sheet 2017.pdf", document type "Balance Sheet"

**Say**: "Now I'll process a multi-year consolidated balance sheet. This is a native text PDF — PyMuPDF will extract the text directly without needing to render pages. The extraction prompt asks for all capital & liability line items, all asset line items, and comparative period values."

*(Wait for processing)*

**On result page — show extraction**:

"Notice the periods array — two years are extracted: 31-Mar-17 and 31-Mar-16. All the major line items show values for both periods. The unit field shows 'rupees in thousands' — we preserve this exactly without multiplying."

**Show validation**:

"The balance sheet validation checks `Total Capital & Liabilities ≈ Total Assets` independently for each period. You can see the formula, the operands, and the variance."

---

## Step 10 — Process P&L (4:30–5:20)

**Action**: Upload "Consolidated Profit & Loss 2017.pdf", document type "Profit & Loss"

**Say**: "The Profit & Loss extraction includes income, expenditure, profit, appropriations, and earnings per share — EPS is explicitly required and not discarded. Four validation checks run per period: income components sum, expenditure components sum, net profit, and consolidated profit after minority interest."

*(Highlight key validation checks)*

---

## Step 11 — Process Cash Flow (5:20–6:00)

**Action**: Upload "Consolidated Cash Flow Statement 2017.pdf", document type "Cash Flow Statement"

**Say**: "The cash flow statement spans 2 pages. Both pages are sent to the AI together, preserving continuity. Negative values — shown as parentheses in the source document — are correctly extracted as negative numbers. The validation checks: operating plus investing plus financing plus FX equals net change; and opening cash plus net change equals closing cash."

**Point to negative investing values**: "You can see investing activities are negative — cash outflows — correctly extracted."

---

## Step 12 — Demonstrate Invalid File (6:00–6:20)

**Action**: Upload a `.txt` or `.docx` file

**Say**: "If an unsupported file type is uploaded, the system rejects it immediately with a structured error response — code UNSUPPORTED_FILE_TYPE — before any processing happens. The file type is detected from magic bytes, not the extension."

---

## Step 13 — Demonstrate Too Many Pages (6:20–6:35)

**Action**: Mention a 4-page PDF would fail

**Say**: "Documents with more than 3 pages are rejected with code TOO_MANY_PAGES. This limit is configurable via environment variable."

---

## Step 14 — Demonstrate Validation Failure (6:35–6:50)

**Action**: Point to any document that has FAIL validation, or describe it

**Say**: "A document can have processing_status PASS — meaning it was successfully extracted — while having validation FAIL, meaning the extracted numbers don't satisfy the financial equations. These are two separate statuses. A corrupt file causes FAILED processing status; incorrect numbers cause FAIL in the validation section."

---

## Step 15 — Open Swagger (6:50–7:10)

**Action**: Open `/docs`

**Say**: "The full Swagger documentation is at /docs. All four endpoints are documented: health check, document processing with the multipart schema, document list, and get by filename. Each endpoint shows request format, response schema, and example responses."

**Try health in Swagger**: Execute the health endpoint live.

---

## Step 16 — Show GitHub (7:10–7:30)

**Action**: Open GitHub repository

**Say**: "The complete source code is in this public GitHub repository. The structure follows the specification exactly: backend with services, schemas, models, repositories, and routes; frontend with templates and static files; tests, docs with architecture diagram, and sample JSON outputs."

**Point to structure**: "52 tests, all passing. No secrets committed — the .env.example shows the required variables without values."

---

## Step 17 — Explain Architecture (7:30–8:00)

**Action**: Open `docs/architecture.png`

**Say**: "The architecture follows a strict separation of concerns — this is the most important design decision. The AI is responsible only for semantic understanding: reading the document and extracting values with evidence. Python is responsible for all arithmetic decisions: financial validation is completely deterministic. This means financial PASS/FAIL results are auditable, testable, and 100% reproducible — independent of whatever the LLM might say."

---

## Demo Complete

**Closing statement**: "In summary: the platform handles all four document types, works with both native and scanned PDFs, extracts structured data with evidence grounding, validates financial arithmetic deterministically, stores everything in PostgreSQL, and exposes a clean REST API with a professional dashboard. Any questions?"

---

## Anticipated Interview Follow-Ups During Demo

| Moment | Likely Question | Answer |
|--------|----------------|--------|
| Showing extraction | "What if the LLM invents a value?" | Evidence requirement exposes it; null default; completeness guard; Python overrides arithmetic |
| Showing validation | "Why not let the AI validate?" | LLMs make arithmetic errors; Python is deterministic and testable |
| Showing OCR badge | "How do you know a PDF is scanned?" | avg chars/page < 50 threshold |
| Showing comparative periods | "How do you prevent mixing years?" | Each period validated independently using its own key |
| Showing negative values | "How do parentheses become negative?" | Prompt rule: (100) → -100; Python arithmetic handles negatives correctly |
| Showing null field | "Why null instead of 0?" | 0 is a valid financial value; null means genuinely missing — prevents false PASS validation |
