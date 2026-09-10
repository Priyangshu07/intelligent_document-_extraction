# FinDoc AI — Financial Document Intelligence Platform

> AI-powered financial document extraction, validation and intelligence — built for the NeoStats AI Engineer Internship Case Study.

---

## 🎯 Problem Statement

Financial institutions and enterprises process large volumes of financial documents — invoices, balance sheets, profit & loss statements, and cash flow statements. Manual extraction is slow, error-prone and unscalable. Existing OCR-only solutions lack structured understanding and financial validation.

## ✅ Solution

A production-grade **Financial Document Intelligence Platform** that:
1. Accepts PDF, JPG and PNG financial documents (up to 3 pages)
2. Extracts all meaningful financial data using AI vision with strict evidence grounding
3. Validates extracted numbers using deterministic Python arithmetic (not AI guesses)
4. Stores all results in PostgreSQL with full JSON extraction data
5. Serves a professional dashboard and REST API

---

## 🏗️ Architecture

```
Browser / Client
       ↓
FastAPI Application (REST API + Jinja2 Dashboard + Swagger)
       ↓
File Validation (magic bytes, MIME, page count, filename sanitization)
       ↓
OCR / Text Extraction (PyMuPDF native text OR page rendering for scanned docs)
       ↓
AI Vision Extraction (GPT-4o / Claude / Gemini — document-specific prompts)
       ↓
Evidence + Completeness Guard (page grounding, omission detection)
       ↓
Deterministic Financial Validation (Pure Python — PASS/FAIL/NOT_APPLICABLE)
       ↓
PostgreSQL Persistence (upsert by filename, JSONB columns)
       ↓
REST API Response + Dashboard
```

See [`docs/architecture.png`](docs/architecture.png) for the visual diagram.

---

## 🚀 Features

- **4 Document Types**: Invoice, Balance Sheet, Profit & Loss, Cash Flow Statement
- **Hybrid OCR**: Native PDF text extraction; automatic fallback to rendered page images for scanned PDFs
- **AI Vision**: Vision-capable LLM extracts complete structured data from rendered document images
- **Evidence Grounding**: Every extracted value carries page number and verbatim source evidence
- **Completeness Guard**: Detects potential extraction omissions by comparing OCR text against extracted data
- **Deterministic Validation**: PASS / FAIL / NOT_APPLICABLE — pure Python, no LLM guessing
- **PostgreSQL**: Full JSONB storage, upsert-by-filename, dashboard queries
- **Professional Dashboard**: Dark-theme UI with upload, document list, result explorer
- **Swagger/OpenAPI**: Full interactive API docs at `/docs`
- **52 Tests**: All passing

---

## 🛠️ Technology Stack

| Layer | Technology | Reason |
|-------|-----------|--------|
| Backend | Python + FastAPI | Fast, async-capable, excellent Pydantic integration |
| Database | PostgreSQL + SQLAlchemy | Reliable, supports JSONB for flexible extraction storage |
| Schema | Pydantic v2 | Type-safe structured output validation |
| PDF | PyMuPDF | Fast native text extraction + page rendering |
| OCR/Vision | LLM vision API | Handles scanned/image-based documents without local models |
| AI | OpenAI GPT-4o / Anthropic Claude / Google Gemini | Configurable via env var; best-in-class vision understanding |
| Frontend | Jinja2 + HTML + Vanilla CSS/JS | Lightweight, no JS framework overhead |
| Container | Docker | Portable, reproducible deployment |

---

## ⚙️ Processing Pipeline

1. **File Validation** — Magic bytes (not extension alone), page count limit, filename sanitization, path traversal prevention
2. **OCR / Text Extraction** — PyMuPDF native text; if avg < 50 chars/page → scanned PDF; render at 200 DPI
3. **AI Extraction** — Vision LLM receives: system prompt (document-specific), text content, and/or page images
4. **Completeness Guard** — Tokenizes OCR text numerics vs. extracted values; flags potential omissions
5. **Financial Validation** — Pure Python arithmetic for all checks (see below)
6. **PostgreSQL Persistence** — Upsert by document_name; latest result always returned
7. **API Response** — Structured JSON with all stages

---

## 🔍 OCR Approach

- **Native text extraction** (PyMuPDF): Used when PDF pages contain ≥50 chars/page on average
- **Scanned PDF detection**: Below threshold → automatically classified as image-based
- **Page rendering**: Scanned pages rendered to PNG at 200 DPI, base64-encoded, sent to vision LLM
- **Image files** (JPG/PNG): Always rendered to base64 PNG for vision LLM

**No local models are downloaded.** The LLM vision API handles OCR for scanned documents.

---

## 🤖 AI Model / Provider

Configurable via environment variables. Default: **Google Gemini 1.5 Pro** (or GPT-4o).

```env
AI_PROVIDER=google    # openai | anthropic | google
AI_MODEL=gemini-3.6-flash
GOOGLE_API_KEY=your_key_here
```

**Document-specific prompts** are used for each document type — not a generic weak prompt. Each prompt specifies:
- Required JSON schema
- Evidence grounding requirements  
- Negative value handling (parentheses → negative)
- Missing value handling (always null, never invented)
- Unit preservation rules
- Multi-period comparative data handling

---

## 📊 Structured Extraction

Every important value:
```json
{
  "value": 12500.00,
  "page_number": 1,
  "evidence": "Subtotal: 12,500.00"
}
```

Financial line items:
```json
{
  "label": "Interest Earned",
  "normalized_key": "interest_earned",
  "values": {"31-Mar-17": 5234567, "31-Mar-16": 4876543},
  "page_number": 1,
  "evidence": "Interest Earned 5,234,567 4,876,543"
}
```

---

## 🔍 Evidence Grounding

- Every extracted value includes `page_number` and `evidence` (verbatim source text)
- Frontend displays evidence snippets with page references
- Completeness guard compares OCR text against extraction to flag omissions

---

## ✅ Financial Validation

**The LLM never decides PASS/FAIL.** All arithmetic is deterministic Python.

### Tolerance
```
passes if: abs(calculated - reported) <= max(ABS_TOLERANCE, REL_TOLERANCE × abs(reported))
Default: ABS_TOLERANCE=1.0 units, REL_TOLERANCE=0.5%
```

Configurable via:
```env
VALIDATION_ABS_TOLERANCE=1.0
VALIDATION_REL_TOLERANCE=0.005
```

### Invoice Checks
- `Qty × Unit Price ≈ Net Amount` (per line item)
- `Σ(line_net_amounts) ≈ Subtotal`
- `Subtotal + Tax − Discount ≈ Total`
- `Total − Amount Paid ≈ Balance Due`

### Balance Sheet Checks
- `Total Capital & Liabilities ≈ Total Assets` (per period)

### P&L Checks
- `Interest Earned + Other Income ≈ Total Income` (per period)
- `Σ(Expenditure components) ≈ Total Expenditure` (per period)
- `Total Income − Total Expenditure ≈ Net Profit` (per period)
- `Net Profit − Minority Interest ≈ Consolidated Profit` (per period)

### Cash Flow Checks
- `Operating + Investing + Financing + FX ≈ Net Change in Cash` (per period)
- `Opening Cash + Net Change + Amalgamation ≈ Closing Cash` (per period)

---

## 🗄️ Database Schema

Table: `processed_documents`

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| document_name | VARCHAR(512) | Original filename (safe) |
| document_type | VARCHAR(64) | invoice \| balance_sheet \| profit_and_loss \| cash_flow_statement |
| processing_status | VARCHAR(32) | PASS \| FAILED |
| file_type | VARCHAR(64) | MIME type |
| page_count | INTEGER | Number of pages |
| is_readable | BOOLEAN | File readability |
| ocr_used | BOOLEAN | Whether OCR path was taken |
| extracted_data | JSONB | Full extraction result |
| validation | JSONB | All validation checks |
| file_validation | JSONB | File validation details |
| processing_metadata | JSONB | Timing, provider, model |
| completeness | JSONB | Completeness guard result |
| error_detail | TEXT | Safe error message if failed |
| created_at | TIMESTAMPTZ | First processed |
| updated_at | TIMESTAMPTZ | Last updated |

**Same filename processed again → latest result returned** (upsert by document_name).

---

## 📡 API Reference

### Base URL
```
https://your-deployment.onrender.com
```

### Endpoints

#### `GET /api/v1/health`
Health check.
```json
{"status": "ok", "version": "1.0.0", "database": "connected"}
```

#### `POST /api/v1/documents/process`
Upload and process a document.

**Request** (`multipart/form-data`):
- `file`: PDF / JPG / PNG (max 3 pages)
- `document_type`: `invoice` | `balance_sheet` | `profit_and_loss` | `cash_flow_statement`

**Response** (200 OK):
```json
{
  "document_name": "invoice.jpg",
  "document_type": "invoice",
  "processing_status": "PASS",
  "file_validation": {"file_type": "image/jpeg", "is_supported": true, "page_count": 1, "status": "PASS"},
  "extracted_data": {"invoice_number": {"value": "INV-001", "page_number": 1, "evidence": "INV-001"}},
  "validation": {"checks": [...], "overall_status": "PASS", "issues": []},
  "completeness": {"completeness_status": "OK", "potential_missing_fields": []},
  "processing_metadata": {"ocr_used": true, "processed_at": "...", "processing_time_ms": 3200}
}
```

#### `GET /api/v1/documents`
List all processed documents (newest first).

#### `GET /api/v1/documents/{document_name}`
Get latest result for a document by filename.

### Error Response Format
```json
{"error": {"code": "UNSUPPORTED_FILE_TYPE", "message": "Only PDF / JPG / PNG documents are supported."}}
```

### Error Codes
| Code | HTTP | Meaning |
|------|------|---------|
| `EMPTY_FILE` | 400 | Zero-byte file |
| `UNSUPPORTED_FILE_TYPE` | 400 | Not PDF/JPG/PNG |
| `CORRUPT_FILE` | 400 | Unreadable file |
| `TOO_MANY_PAGES` | 400 | > 3 pages |
| `INVALID_DOCUMENT_TYPE` | 400 | Unknown document_type |
| `FILE_TOO_LARGE` | 413 | Exceeds 20MB |
| `OCR_FAILURE` | 422 | Could not extract text/render |
| `AI_EXTRACTION_FAILED` | 422 | LLM failure after retries |
| `DOCUMENT_NOT_FOUND` | 404 | No record for that name |
| `INTERNAL_SERVER_ERROR` | 500 | Unexpected error |

---

## 🖥️ Frontend

- **Dashboard** (`/`): Upload form, document type selector, processed documents table
- **Result page** (`/document/{name}`): Tabbed view with file info, extraction, validation checks, raw JSON
- **Swagger** (`/docs`): Full interactive API documentation

---

## 🚀 Local Setup

### Prerequisites
- Python 3.11+
- PostgreSQL 14+
- Google/OpenAI/Anthropic API key

### Steps

```bash
# 1. Clone repository
git clone https://github.com/Priyangshu07/intelligent_document-_extraction.git
cd intelligent_document_extraction

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r backend/requirements.txt

# 4. Configure environment
cp .env.example backend/.env
# Edit backend/.env and set:
#   DATABASE_URL=postgresql://user:pass@localhost:5432/docai
#   AI_PROVIDER=google
#   AI_MODEL=gemini-3.6-flash
#   GOOGLE_API_KEY=your_key_here

# 5. Create database
psql postgres -c "CREATE USER docai WITH PASSWORD 'docai';"
psql postgres -c "CREATE DATABASE docai OWNER docai;"

# 6. Start the application
cd backend
PYTHONPATH=$(pwd) uvicorn app.main:app --host 0.0.0.0 --port 8000 --env-file .env

# App will be at: http://localhost:8000
# API docs:       http://localhost:8000/docs
# Health:         http://localhost:8000/api/v1/health
```

### Run Tests
```bash
cd backend
PYTHONPATH=$(pwd) DATABASE_URL="postgresql://x:x@localhost/x" python3 -m pytest tests/ -v
# Expected: 52 passed
```

---

## 🌐 Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | — | PostgreSQL connection string |
| `AI_PROVIDER` | Yes | `openai` | `openai` \| `anthropic` \| `google` |
| `AI_MODEL` | Yes | `gpt-4o` | Model name for chosen provider |
| `OPENAI_API_KEY` | If openai | — | OpenAI API key |
| `ANTHROPIC_API_KEY` | If anthropic | — | Anthropic API key |
| `GOOGLE_API_KEY` | If google | — | Google API key |
| `AI_TIMEOUT_SECONDS` | No | `120` | LLM request timeout |
| `AI_MAX_RETRIES` | No | `2` | LLM retry count |
| `MAX_FILE_SIZE_MB` | No | `20` | Upload size limit |
| `MAX_PAGES` | No | `3` | Max document pages |
| `VALIDATION_ABS_TOLERANCE` | No | `1.0` | Absolute validation tolerance |
| `VALIDATION_REL_TOLERANCE` | No | `0.005` | Relative validation tolerance (0.5%) |
| `LOG_LEVEL` | No | `INFO` | Log verbosity |
| `CORS_ORIGINS` | No | `*` | CORS allowed origins |

---

## 🧪 Testing

```bash
cd backend
PYTHONPATH=$(pwd) python3 -m pytest tests/ -v
```

**52 tests** covering:
- File validation (valid PDF/JPG/PNG, empty, corrupt, too many pages, unsupported type, path traversal)
- Invoice validation (PASS/FAIL/NOT_APPLICABLE, tolerance, discounts, line items)
- Balance Sheet validation (comparative periods, missing fields)
- P&L validation (income/expenditure/profit checks, negative minority interest)
- Cash Flow validation (neg values, FX adjustment, comparative periods)
- API endpoints (health, upload, list, get by name, error cases)

---

## ☁️ Deployment

### Render.com (Recommended)

1. Push code to GitHub (public repository)
2. Create new Web Service on Render.com
3. Set Build Command: `pip install -r backend/requirements.txt`
4. Set Start Command: `cd backend && PYTHONPATH=$(pwd) uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Add PostgreSQL (Render managed database)
6. Set all environment variables in Render dashboard

### Docker

```bash
docker build -t findoc-ai .
docker run -p 8000:8000 \
  -e DATABASE_URL=postgresql://... \
  -e AI_PROVIDER=google \
  -e AI_MODEL=gemini-3.6-flash \
  -e GOOGLE_API_KEY=your_key \
  findoc-ai
```

---

## 🔗 Live URLs

| Resource | URL |
|----------|-----|
| Frontend | TBD after deployment |
| Backend API | TBD after deployment |
| Swagger/OpenAPI | TBD after deployment |
| Health | TBD after deployment |
| GitHub | https://github.com/Priyangshu07/intelligent_document-_extraction |

---

## 📁 Sample JSON Outputs

See [`sample_outputs/`](sample_outputs/) for real extraction results from the reference documents.

---

## ⚠️ Known Limitations

1. **3-page limit**: Financial statements > 3 pages (common in annual reports) require manual splitting
2. **LLM latency**: AI extraction takes 20–60 seconds per document; async processing would improve UX
3. **Single document type per upload**: Multi-document batches not yet supported
4. **Currency detection**: Relies on LLM to correctly identify currency; may misidentify with ambiguous symbols
5. **Table structure**: Complex merged cells may cause mis-alignment of comparative period columns
6. **Unit normalization**: System preserves source units; downstream consumers must be aware of `₹ in '000`

## 🏭 Production Improvements

1. **Async processing with Celery + Redis**: Return a job ID immediately, poll for results
2. **Document batching**: Process multiple documents per request
3. **Multi-page support**: Implement page chunking for large documents
4. **Confidence scoring**: Add per-field confidence from LLM logprobs
5. **Human-in-the-loop**: Flag low-confidence extractions for manual review
6. **Fine-tuned model**: Domain-specific fine-tuned model for Indian banking financial statements
7. **Caching**: Cache embeddings/extractions for identical documents
8. **Monitoring**: Prometheus metrics, Grafana dashboards, Sentry error tracking
9. **Authentication**: JWT-based auth for multi-tenant usage
10. **Audit trail**: Immutable append-only extraction history (vs. current upsert)

---

## 🤖 AI / Tool Usage Declaration

This project was built with assistance from **Google Antigravity (AI coding assistant)**:
- Architecture design and technology selection
- Implementation of all Python services, schemas, and routes
- Document-specific extraction prompts
- Test suite design and implementation
- Documentation writing

The AI assistant was used to accelerate development. All code was reviewed, the logic was designed by the developer, and all validation arithmetic is manually verifiable. The AI did not produce PASS/FAIL financial decisions — those are implemented as pure Python arithmetic.

---

## 📋 Assumptions

1. Document type is user-selected (not auto-classified)
2. Financial statements use the balance equation `Total Capital & Liabilities = Total Assets`
3. Parentheses around numbers indicate negative values throughout
4. The `₹ in '000` unit is preserved as-is; values are NOT multiplied
5. Same-filename re-uploads overwrite previous results (latest-wins)
6. All financial statements are Indian banking sector consolidated statements
