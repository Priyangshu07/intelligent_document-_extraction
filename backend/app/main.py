"""
Financial Document Intelligence Platform
FastAPI application entry point.

Serves:
  - REST API at /api/v1/
  - Swagger UI at /docs
  - HTML dashboard at /
  - Static files at /static/

On startup: creates database tables if they do not exist.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api import api_router
from app.core.config import settings
from app.core.database import create_tables
from app.core.logging import configure_logging, get_logger

# Configure logging before anything else
configure_logging()
logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("app_startup", app=settings.APP_NAME, version=settings.APP_VERSION)
    try:
        create_tables()
        logger.info("db_tables_ready")
    except Exception as exc:
        logger.error("db_startup_error", error=str(exc)[:200])
    yield
    # Shutdown
    logger.info("app_shutdown")


# ---------------------------------------------------------------------------
# App instance
# ---------------------------------------------------------------------------
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "AI-powered financial document intelligence platform. "
        "Supports Invoice, Balance Sheet, Profit & Loss, and Cash Flow Statement extraction "
        "with deterministic financial validation."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
cors_origins = settings.CORS_ORIGINS if isinstance(settings.CORS_ORIGINS, list) else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Static files & templates
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/

# Frontend paths (relative to project root)
FRONTEND_DIR = BASE_DIR.parent / "frontend"
TEMPLATES_DIR = FRONTEND_DIR / "templates"
STATIC_DIR = FRONTEND_DIR / "static"

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates: Jinja2Templates | None = None
if TEMPLATES_DIR.exists():
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------
app.include_router(api_router)

# ---------------------------------------------------------------------------
# Frontend routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard(request: Request):
    """Main dashboard page."""
    if templates:
        return templates.TemplateResponse("dashboard.html", {"request": request})
    return HTMLResponse("<h1>Dashboard — templates not found</h1>")


@app.get("/document/{document_name}", response_class=HTMLResponse, include_in_schema=False)
async def document_result(request: Request, document_name: str):
    """Document result detail page."""
    if templates:
        return templates.TemplateResponse(
            "document_result.html",
            {"request": request, "document_name": document_name},
        )
    return HTMLResponse(f"<h1>Result for {document_name}</h1>")


# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all handler. Never exposes stack traces."""
    logger.error(
        "unhandled_exception",
        path=str(request.url.path),
        error=str(exc)[:200],
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred. Please try again.",
            }
        },
    )
