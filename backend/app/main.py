"""
HctrConvert — Application Factory
──────────────────────────────────
Creates and configures the FastAPI application instance.

SOFTWARE ENGINEERING PRINCIPLE: "Application Factory Pattern"
- Separation between app creation and app running
- Registers security/observability middleware, global error handlers,
  periodic stale temp-file sweeping, API routes, and static UI serving
"""
from __future__ import annotations

import asyncio
import warnings
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.logging import setup_logging, get_logger
from app.core.exceptions import HctrConvertError
from app.core.middleware import ObservabilityAndSecurityMiddleware
from app.api.routes import router
from app.utils.file_utils import sweep_stale_temp_files

# Suppress third-party pdf2docx -> fitz import FutureWarning
warnings.filterwarnings("ignore", message=".*`fitz` API is deprecated.*", category=FutureWarning)


async def _periodic_temp_sweeper(interval_seconds: int) -> None:
    """Background loop that sweeps orphaned temporary files."""
    while True:
        await asyncio.sleep(interval_seconds)
        sweep_stale_temp_files()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle hooks."""
    settings = get_settings()
    logger = get_logger(__name__)

    # Clean stale temp files on startup and schedule periodic sweeps
    sweep_stale_temp_files()
    sweeper_task = asyncio.create_task(
        _periodic_temp_sweeper(max(60, settings.CLEANUP_AFTER_SECONDS // 2))
    )

    logger.info(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} starting up")
    logger.info(f"   Upload dir:  {settings.UPLOAD_DIR}")
    logger.info(f"   Output dir:  {settings.OUTPUT_DIR}")
    logger.info(f"   Max file:    {settings.MAX_FILE_SIZE_MB} MB")
    logger.info(f"   Max workers: {settings.MAX_CONCURRENT_JOBS}")
    logger.info(f"   CORS:        {settings.CORS_ORIGINS}")
    try:
        yield
    finally:
        sweeper_task.cancel()
        with suppress(asyncio.CancelledError):
            await sweeper_task
        logger.info(f"🛑 {settings.APP_NAME} shutting down")


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""

    settings = get_settings()
    setup_logging()
    logger = get_logger(__name__)

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Universal file converter API — documents, images, audio, video.",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ── Middleware ─────────────────────────────────────────────
    app.add_middleware(ObservabilityAndSecurityMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition", "X-Request-ID", "X-Process-Time-Ms"],
    )

    # ── Global exception handlers ─────────────────────────────
    @app.exception_handler(HctrConvertError)
    async def hctrconvert_error_handler(request: Request, exc: HctrConvertError):
        req_id = getattr(request.state, "request_id", None)
        logger.error(f"[{req_id}] {exc.__class__.__name__}: {exc.detail}")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": exc.detail,
                "error_code": exc.__class__.__name__,
                "request_id": req_id,
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        req_id = getattr(request.state, "request_id", None)
        logger.exception(f"[{req_id}] Unhandled error: {exc}")
        return JSONResponse(
            status_code=500,
            content={
                "detail": "An unexpected internal server error occurred.",
                "error_code": "InternalServerError",
                "request_id": req_id,
            },
        )

    # ── Register routes ───────────────────────────────────────
    app.include_router(router)

    # ── Serve frontend static files ───────────────────────────
    frontend_dir = Path(__file__).parent.parent.parent / "frontend" / "src"
    if frontend_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
        logger.info(f"Serving frontend from {frontend_dir}")

    return app


app = create_app()
