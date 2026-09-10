# Interview Notes — FinDoc AI Financial Document Intelligence Platform

> Based on the ACTUAL IMPLEMENTED CODE. Study these before the interview.

---

## ⏱️ Explanations by Duration

### 30-Second Explanation
"I built a Financial Document Intelligence Platform that accepts invoices, balance sheets, profit & loss statements and cash flow statements as PDFs or images. It uses a vision AI model to extract every visible financial field with evidence grounding — tracking exactly which page and text each value came from. Then it runs deterministic Python arithmetic to validate financial equations like Assets = Liabilities + Equity. All results are stored in PostgreSQL and surfaced through a professional dashboard and REST API."

### 1-Minute Explanation
"The platform solves the problem of manually processing financial documents. A user uploads a PDF or image and selects the document type. The system first validates the file — checking magic bytes, not just extension, to detect corruption or wrong types, enforcing a 3-page limit. Then PyMuPDF extracts native text if available; if the document is scanned or image-based, pages are rendered at 200 DPI and sent to a vision LLM. The LLM uses document-specific prompts — not a generic prompt — to return structured JSON with every extracted value accompanied by page number and evidence text. A completeness guard then checks if the extracted data covers all numeric candidates in the raw text. Finally, pure Python arithmetic validates financial equations with configurable tolerance. Everything is persisted in PostgreSQL and accessible via REST API and a Jinja2 dashboard."

### 3-Minute Explanation
"The architecture follows a strict separation of concerns: AI handles semantic understanding, Python handles all arithmetic decisions. The pipeline has seven stages:

**1. File Validation** — We read magic bytes (PDF=%PDF, JPEG=\xff\xd8\xff, PNG=\x89PNG) to detect actual type, not trusting the file extension. Filenames are sanitized to prevent path traversal. Files over 3 pages are rejected.

**2. OCR / Text Extraction** — PyMuPDF extracts native text. If average chars per page is below 50, we classify it as scanned and render pages to 200 DPI PNG images.

**3. AI Extraction** — A vision-capable LLM (GPT-4o/Claude/Gemini, configurable) receives the document content plus a document-specific system prompt. The prompt specifies the exact JSON schema, evidence requirements, negative value handling (parentheses → negative), and explicitly prohibits inventing values. Missing fields must be null.

**4. Evidence + Completeness** — Every field carries page_number and evidence (verbatim source text). A completeness guard tokenizes OCR numerics and compares coverage.

**5. Financial Validation** — Pure Python functions for each document type. Invoice: qty×price, sum of lines, subtotal+tax-discount=total. Balance Sheet: Capital&Liabilities=Assets per period. P&L: income checks, expenditure checks, net profit. Cash Flow: operating+investing+financing+FX=net_change; opening+net=closing. Status is PASS, FAIL, or NOT_APPLICABLE when required fields are missing. Tolerance: max(1.0, 0.5% of reported value).

**6. PostgreSQL** — SQLAlchemy upserts by document_name. Same file reprocessed → latest result returned.

**7. API + Dashboard** — FastAPI serves REST API at /api/v1/ and Jinja2 dashboard at /. Swagger at /docs."

---

## 🏗️ Architecture Walkthrough

### Key Files
| File | Role |
|------|------|
| `app/main.py` | FastAPI app, lifespan, routes, CORS, static files |
| `app/core/config.py` | Pydantic-settings configuration from .env |
| `app/core/database.py` | SQLAlchemy engine, session factory, table creation |
| `app/models/document.py` | ProcessedDocument ORM model with JSONB columns |
| `app/schemas/extraction.py` | Pydantic schemas: InvoiceExtraction, BalanceSheetExtraction, etc. |
| `app/schemas/document.py` | API schemas: DocumentProcessResponse, ValidationCheck, etc. |
| `app/services/document_validation_service.py` | File validation: magic bytes, page count, sanitization |
| `app/services/ocr_service.py` | PyMuPDF text + page rendering for scanned docs |
| `app/services/extraction_service.py` | LLM API calls, document-specific prompts, JSON parsing |
| `app/services/financial_validation_service.py` | All deterministic arithmetic: PASS/FAIL/NOT_APPLICABLE |
| `app/services/document_service.py` | Pipeline orchestration: calls all stages in order |
| `app/utils/completeness_guard.py` | OCR text vs extraction coverage check |
| `app/repositories/document_repository.py` | DB upsert, list, get by name |
| `app/api/routes/documents.py` | FastAPI route handlers |

---

## 🔍 Deep Dive: Key Decisions

### Why FastAPI?
- Native async support for I/O-bound LLM calls
- Automatic Pydantic validation and Swagger generation
- Dependency injection (database sessions, config)
- Handles `multipart/form-data` for file uploads natively

### Why PostgreSQL?
- JSONB columns allow flexible extraction storage without schema migrations for each new field
- Indexed document_name for fast lookup by filename
- ACID transactions for data integrity
- Managed PostgreSQL available on all deployment platforms (Render, Railway, etc.)

### Why Jinja2 (not React/Vue)?
- No build step, no Node.js dependencies
- Single FastAPI process serves both API and HTML
- Simpler deployment (one Dockerfile, one process)
- Dashboard data is loaded from real API calls in the browser

### Why PyMuPDF?
- Fastest Python PDF library (C++ binding)
- Native text extraction preserves text order for financial tables
- Built-in page rendering with configurable DPI

### Why Vision LLM (not traditional OCR)?
- Traditional OCR (Tesseract) struggles with financial tables, mixed fonts, curved text
- Vision LLM understands document structure semantically
- Can handle handwritten annotations, complex layouts
- No local model download required

### Why Pydantic?
- Strongly typed extraction schemas catch LLM output errors immediately
- `model_dump()` serializes to JSON for PostgreSQL JSONB storage
- Pydantic-settings reads environment variables with type coercion

### Why structured outputs?
- `response_format={"type": "json_object"}` forces JSON from OpenAI
- Google Gemini `response_mime_type="application/json"` ensures JSON
- Prevents markdown-wrapped responses that break parsing

---

## 🛡️ Hallucination Prevention

**Q: How do you prevent the AI from inventing financial values?**

**A:** Multiple layers:
1. **System prompt explicit rule**: "NEVER invent or infer missing values. Missing fields MUST be null."
2. **Pydantic null defaults**: All fields have `Optional[...] = None`. If LLM returns a value for a field not in the document, it's validated; if it invents a value with no source, we can't fully prevent it — but the evidence field exposes it.
3. **Evidence requirement**: Every value must include `evidence` — verbatim source text. If the LLM can't cite evidence, it should return null.
4. **Completeness guard**: Detects if extraction coverage is suspiciously low (LLM hallucinated fields that don't exist in OCR text would fail this check if OCR has different content).
5. **Deterministic validation**: AI decisions about financial arithmetic are overridden by Python. The LLM cannot decide a balance sheet balances.

---

## ❓ Missing Value Handling

- Missing values are **always null**, never zero, never estimated
- `{"value": null, "page_number": null, "evidence": null}`
- Financial validation with null fields → `NOT_APPLICABLE` status
- `NOT_APPLICABLE` is never confused with `FAIL`

---

## 📐 Evidence Grounding

- Every important extracted field: `value + page_number + evidence`
- Evidence is a verbatim snippet from the source document
- Frontend displays evidence with page reference badges
- Allows auditors to verify any extraction by looking at the source page

---

## 🔢 Table Extraction

- Prompt specifies: "Preserve table structure, ALL columns, ALL rows"
- For comparative periods: column headers (e.g., "31-Mar-17") become dict keys
- Line items are arrays of objects, preserving all visible columns
- Balance sheet sections are preserved with original labels

---

## 📅 Comparative Periods

- P&L, Balance Sheet, Cash Flow typically have 2 columns (current + prior year)
- Extracted as: `{"values": {"31-Mar-17": 5234567, "31-Mar-16": 4876543}}`
- Validation runs independently for each period: never mixes years
- Period keys come from the actual column headers in the document

---

## ➖ Negative Values

- Parentheses in source document indicate negative: `(1,234,567)` → `-1234567`
- Prompt explicitly states: "Parentheses/brackets → negative: (100) → -100"
- Cash flow investing activities are typically negative (cash outflows)
- Validation checks handle negative values correctly (e.g., negative investing + positive operating)

---

## 🔢 Decimal Comma Handling

- European invoices use comma as decimal separator: `3,49` → `3.49`
- Prompt rule: "Handle decimal comma safely. 3,49 → 3.49. Do NOT blindly replace all commas."
- Large numbers use commas as thousands separators: `1,234,567` stays `1234567`
- LLM is instructed to distinguish based on context (position, adjacent digits)

---

## 📏 Unit Handling

- Source units like `₹ in '000` are preserved exactly in the `unit` field
- Values are NOT multiplied by 1000 — source values are stored as-is
- If downstream systems need normalized values, they can multiply using the `unit` field
- Prevents silent data corruption

---

## 🔍 Completeness Guard

- Extracts all numeric patterns from OCR text using regex
- Counts non-null extracted values
- If coverage ratio < 30% with >5 numeric candidates → WARNING
- Checks for expected labels (e.g., "interest earned" in P&L)
- **NEVER fills in missing values** — only warns

---

## ✅ Deterministic Financial Validation

### Key design principle
```python
# AI = semantic extraction
# Python = deterministic arithmetic
```

### Invoice validation
```python
calc_total = subtotal + tax_amount - discount
passes = abs(calc_total - reported_total) <= max(ABS_TOLERANCE, REL_TOLERANCE * abs(reported_total))
```

### Balance sheet validation
```python
# Per period:
passes = abs(total_capital_liabilities - total_assets) <= tolerance
```

### NOT_APPLICABLE logic
```python
if subtotal is None or tax_amount is None or total_amount is None:
    return NOT_APPLICABLE  # Never treat None as 0
```

---

## 🗄️ Database Repository

- **Upsert pattern**: Query by document_name first; if exists → UPDATE; else → INSERT
- **JSONB storage**: `extracted_data`, `validation`, `file_validation`, `processing_metadata`, `completeness`
- **Latest result**: `ORDER BY updated_at DESC LIMIT 1`
- **Dashboard query**: All documents, newest first, limited to 100

---

## 🛡️ Security

- **No secrets in code**: All credentials via environment variables
- **Filename sanitization**: `Path(filename).name` + regex replace for path traversal prevention
- **Safe error messages**: Exception stack traces never returned to clients
- **Upload limits**: 20MB file size, 3 pages
- **Magic byte validation**: File type validated by content, not extension
- **CORS**: Configurable origins, default `*` for development

---

## 📊 Logging

- **structlog**: Structured JSON logging in production
- **Key log events**: pipeline_start, file_validation_pass/fail, ocr_native_text/scanned, ai_extraction_start/complete, financial_validation_complete, db_persist_ok/error, pipeline_complete
- **Never logs**: API keys, file content, passwords, secrets

---

## 🧪 Testing

52 tests across 3 test files:
- `test_validation.py`: 23 tests — invoice/balance/P&L/cash flow PASS/FAIL/NOT_APPLICABLE
- `test_extraction.py`: 20 tests — file validation, MIME detection, filename sanitization
- `test_api.py`: 9 tests — API endpoints with mocked dependencies

---

## 🚀 Deployment

- **Dockerfile**: python:3.11-slim, installs system deps (libpq-dev for PostgreSQL), copies source
- **Platform**: Render.com or Railway (managed PostgreSQL + web service)
- **Start command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **Environment**: All secrets in deployment platform dashboard

---

## ⚠️ Known Limitations

1. 3-page limit — large annual reports need splitting
2. LLM latency — 20-60s per document, no async job queue
3. Currency ambiguity — `$` alone doesn't confirm USD
4. Complex merged table cells — may mis-align comparative columns
5. Unit multiplication — downstream consumers must handle `₹ in '000`

---

## 🏭 Production Improvements

1. Celery + Redis for async document processing
2. Confidence scoring from LLM logprobs
3. Fine-tuned model for Indian banking statements
4. Human-in-the-loop for low-confidence extractions
5. JWT authentication for multi-tenant usage
6. Prometheus + Grafana monitoring
7. Document batching API
8. Immutable audit trail (append-only vs. upsert)

---

## 💬 40+ Technical Interview Questions

### AI / LLM Engineering

**Q1: How does the AI extract structured data from financial documents?**
- The LLM receives a document-specific system prompt defining the exact JSON schema, a user message with OCR text and/or base64 page images, and returns structured JSON.
- **Why strong**: Explains both text and vision paths. Shows domain-specific prompting.
- **Follow-up**: Why not use a generic extraction prompt?
- **Answer**: Generic prompts miss document-specific structure (e.g., comparative periods in balance sheets, EPS in P&L). Document-specific prompts enforce the correct schema and rules.

**Q2: How do you prevent the LLM from hallucinating financial values?**
- Explicit "NEVER invent" rule in system prompt; evidence requirement exposes unsourced values; null defaults in Pydantic; completeness guard checks coverage; deterministic Python overrides AI for arithmetic decisions.
- **Why strong**: Shows defense-in-depth, not relying on a single mechanism.
- **Follow-up**: Can you 100% guarantee no hallucination?
- **Answer**: No. But we minimize it through multiple layers and make it detectable via evidence grounding.

**Q3: Why do you use document-specific prompts rather than one generic prompt?**
- Balance sheets need comparative periods and section structure. P&L has EPS data. Cash flow has negative bracketed values and 2-page continuity. A generic prompt would miss these requirements.
- **Follow-up**: How do you test that prompts are correct?
- **Answer**: Process the actual sample documents and inspect extraction outputs against known values.

**Q4: How does the vision path work for scanned documents?**
- PyMuPDF detects low native text (< 50 chars/page avg). Scanned pages rendered at 200 DPI to PNG. Base64-encoded. Sent to vision LLM as image_url parts (OpenAI) or image parts (Anthropic/Google).
- **Why strong**: Shows practical OCR strategy without downloading local models.

**Q5: What happens if the LLM returns invalid JSON?**
- `_parse_json_response()` strips markdown code blocks, tries JSON parse, falls back to extracting the JSON object substring. On failure after retries → RuntimeError caught by document_service → partial result with ai_error.

**Q6: How did you configure the AI provider to be swappable?**
- `AI_PROVIDER` and `AI_MODEL` env vars. `extraction_service.py` dispatches to `_call_openai`, `_call_anthropic`, or `_call_google` based on `settings.AI_PROVIDER`. New provider = add a function and a case in the if/elif.

**Q7: How do you handle LLM timeouts?**
- `AI_TIMEOUT_SECONDS` (default 120s) passed to the client. `AI_MAX_RETRIES` (default 2) controls retry count. Exponential backoff: `time.sleep(1 * attempt)`. After all retries → RuntimeError caught at service level → controlled error response.

### OCR / Document Processing

**Q8: How do you detect whether a PDF is scanned or native text?**
- Extract text from all pages with PyMuPDF. If average characters per page < 50 → classified as scanned. Threshold is configurable (`MIN_TEXT_CHARS_PER_PAGE = 50`).
- **Follow-up**: What if a PDF has mixed native and scanned pages?
- **Answer**: Current implementation renders all pages if average is below threshold. Improvement: per-page detection.

**Q9: Why render at 200 DPI specifically?**
- Balance between image quality (readable numbers and text) and file size/token cost. 72 DPI (screen) is too low for financial tables. 300 DPI adds significant size. 200 DPI is a practical balance.

**Q10: How does file type validation work?**
- Magic bytes: PDF starts with `%PDF`, JPEG with `\xff\xd8\xff`, PNG with `\x89PNG\r\n\x1a\n`. File extension is not trusted alone — a JPEG named `.pdf` is correctly detected as JPEG.
- **Why strong**: Shows security awareness.

**Q11: Why validate page count before OCR?**
- Fail fast principle. Reject multi-page documents before running expensive OCR and LLM calls. Saves compute and cost.

**Q12: How do you handle the 2-page cash flow statement?**
- The OCR service combines all pages into a single `raw_text` with PAGE BREAK separators. Images are a list of base64 PNGs, one per page. The LLM receives all pages and extracts with page continuity preserved.

### Financial Validation

**Q13: Why is the LLM not used for financial PASS/FAIL?**
- LLMs can make arithmetic errors. Financial validation requires 100% deterministic, auditable arithmetic. A 0.1% error in reporting a balance sheet validation would be a serious problem. Python arithmetic is deterministic and testable.
- **Why strong**: This is the core design principle.

**Q14: Explain the tolerance model.**
```python
tolerance = max(ABS_TOLERANCE, REL_TOLERANCE * abs(reported))
passes = abs(calculated - reported) <= tolerance
```
Default: `ABS_TOLERANCE=1.0`, `REL_TOLERANCE=0.005` (0.5%).
For a reported value of 10,000,000 → tolerance = max(1.0, 50,000) = 50,000.
For a reported value of 5.0 → tolerance = max(1.0, 0.025) = 1.0.
- **Why strong**: Shows understanding of floating-point issues and practical rounding.

**Q15: What does NOT_APPLICABLE mean and when is it used?**
- The check cannot be performed because required fields are missing (null). It is NOT a failure — the document simply doesn't provide enough data for that check. Null fields are never treated as zero.
- **Why strong**: Shows understanding of the difference between "we checked and it failed" vs "we couldn't check".

**Q16: How does the cash flow validation handle bracketed negative values?**
- The extraction prompt explicitly states: `(19,084,500) → -19084500`. The Python validation then adds these negative numbers correctly (negative investing cash flow reduces net change in cash).

**Q17: How do you validate comparative periods without mixing years?**
- Each period's values are extracted from `item.values["31-Mar-17"]` etc. Validation iterates over `periods` list and creates a separate check for each. `_get_multi_period_value(item, period)` fetches only that period's value.

**Q18: What are the P&L validation checks?**
1. `interest_earned + other_income ≈ total_income`
2. `interest_expended + operating_expenses + provisions ≈ total_expenditure`
3. `total_income - total_expenditure ≈ net_profit`
4. `net_profit - minority_interest ≈ consolidated_profit`
All per period, independently.

### FastAPI / REST API

**Q19: Why did you use FastAPI instead of Flask?**
- Built-in Pydantic integration for request/response validation; automatic Swagger/OpenAPI docs; async support for LLM I/O calls; type hints natively integrated; faster performance.

**Q20: How does the multipart file upload work in FastAPI?**
- `UploadFile` dependency reads file bytes with `await file.read()`. `Form()` reads `document_type` from the form data. File content is validated before any processing.

**Q21: What HTTP status codes do you use and why?**
- 200: Successful processing (even if financial validation fails — that's not an HTTP error)
- 400: Client errors (unsupported file, empty file, invalid document_type)
- 404: Document not found
- 413: File too large
- 422: Unprocessable entity (valid file but processing failed)
- 500: Unexpected server errors (caught by global handler)

**Q22: How does the upsert-by-filename work?**
- `document_repository.py` queries by `document_name` first. If found → UPDATE all fields, set `updated_at`. If not → INSERT new record. `GET /documents/{name}` always returns the latest (by `updated_at DESC`).

**Q23: How did you implement the global exception handler?**
```python
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error("unhandled_exception", error=str(exc)[:200])
    return JSONResponse(status_code=500, content={"error": {...}})
```
Never returns stack traces. Logs the error internally.

### PostgreSQL / SQLAlchemy

**Q24: Why JSONB for extracted_data instead of a normalized schema?**
- Extraction schema varies by document type (invoice has line_items; balance sheet has sections; P&L has EPS). JSONB allows flexible storage without schema migrations every time extraction schema evolves.
- **Follow-up**: What are the trade-offs?
- **Answer**: JSONB is less queryable than normalized columns. Can't easily `WHERE extracted_data.invoice_number = 'INV-001'`. Could add GIN indexes for specific paths if needed.

**Q25: How is database connection pooling configured?**
- `pool_size=10, max_overflow=20, pool_pre_ping=True`. `pool_pre_ping` tests connections before use to detect stale connections after network issues.

**Q26: How are database tables created?**
- `create_tables()` called on app startup (lifespan event). Uses `Base.metadata.create_all()`. Safe to call repeatedly (uses `IF NOT EXISTS` semantics). No Alembic migrations in current implementation — improvement for production.

### Security

**Q27: How do you prevent path traversal attacks in file uploads?**
```python
name = Path(filename).name  # Take only filename, not directory
name = re.sub(r"[^\w.\-]", "_", name)  # Replace unsafe chars
name = name.lstrip(".")  # Remove hidden file prefix
```

**Q28: What information is never logged?**
- API keys, file content, passwords, database credentials. Log messages include document name, type, stage, duration, and error category only.

**Q29: How do you handle the security of the `.env` file?**
- `.env` is in `.gitignore`. Never committed. `.env.example` contains no real values. Production secrets go in deployment platform environment dashboard, not code.

**Q30: How do you validate the actual file content versus trusting the MIME type header?**
- Read magic bytes from the file content itself. Content-Type header from the browser is not trusted for security decisions.

### Testing

**Q31: How do you test the API without a real database?**
- Override the `get_db` FastAPI dependency with a Mock. Mock returns a `MagicMock()` session. `upsert_document` is also mocked to avoid DB calls.

**Q32: How do you test file validation without uploading files?**
- Use `fitz.open()` to create in-memory PDFs. Use `Pillow` to create in-memory JPEG/PNG bytes. Pass bytes directly to `validate_document()`.

**Q33: How do you test financial validation edge cases?**
- Test PASS with exact values. Test FAIL with wrong reported values. Test NOT_APPLICABLE with None fields. Test tolerance boundary (within 0.5% PASS, outside FAIL). Test negative minority interest in P&L.

### Deployment

**Q34: How is the Docker container structured?**
- Base: `python:3.11-slim`. Installs system deps (libpq-dev for PostgreSQL, poppler-utils). Copies requirements first (Docker layer caching). Copies source. Sets `PYTHONPATH`. Runs uvicorn.

**Q35: How would you make this production-ready for high traffic?**
- Add Celery + Redis for async processing. Multiple uvicorn workers behind a load balancer. Connection pooling with PgBouncer. Caching for repeated documents. Kubernetes for horizontal scaling.

**Q36: How does the app handle database connection failures on startup?**
- `create_tables()` is wrapped in try/except. Failure is logged as error but app continues starting. Individual requests will fail with database error if DB is unavailable. Health endpoint reports `"database": "disconnected"`.

### Performance

**Q37: What's the typical processing time?**
- File validation: ~1ms. Native PDF text extraction: ~50ms. LLM extraction: 20–60s (dominant factor). DB persist: ~10ms. Total: 20–65s per document.

**Q38: What's the biggest performance bottleneck?**
- LLM API latency. Mitigation: async processing with job queue (Celery), streaming responses for progress updates, caching identical documents.

**Q39: How would you improve throughput?**
- Run FastAPI with multiple uvicorn workers (`--workers 4`). Use `asyncio` for concurrent LLM calls. Add document processing queue to decouple upload from extraction.

### Scalability / Architecture

**Q40: How would you scale this to millions of documents?**
1. Message queue (SQS/Kafka) for document processing jobs
2. Separate processing workers (scalable horizontally)
3. Object storage (S3) for original files and rendered images
4. Read replicas for dashboard queries
5. Elasticsearch for full-text search over extracted data
6. Fine-tuned smaller model for common document types

**Q41: How would you add authentication?**
- JWT tokens via FastAPI middleware. `Depends(get_current_user)` on protected routes. API keys for programmatic access. Separate public and internal routes.

**Q42: How would you handle a document that takes >2 minutes to process?**
- Return a job ID immediately (202 Accepted). Process in background (Celery worker). Client polls `/jobs/{id}` for status. WebSocket for real-time progress. Store intermediate state in Redis.

**Q43: What monitoring would you add in production?**
- Prometheus metrics: request count, processing time histogram, LLM latency, validation PASS rate
- Grafana dashboards
- Sentry for error tracking
- Structured logging to Elasticsearch/Datadog
- Alerts: LLM timeout rate > 5%, DB connection failures

**Q44: How would you test extraction accuracy at scale?**
- Golden dataset of documents with known correct extractions. Automated regression tests that process documents and compare against expected values. Track accuracy metrics over time. Alert on accuracy degradation after model updates.

**Q45: Can you make a small change during the interview?**
- Yes. The codebase is modular. Adding a new document type requires: a new Pydantic schema in `extraction.py`, a new system prompt in `extraction_service.py`, a new validation function in `financial_validation_service.py`, and registering the type in `VALID_DOCUMENT_TYPES`.
