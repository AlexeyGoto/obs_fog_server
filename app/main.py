"""
OBS Fog Server - Main Application Entry Point

A modern FastAPI application for OBS streaming management.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.core.config import settings
from app.core.database import close_db, init_db
from app.core.rate_limit import limiter
from app.routers import auth, downloads, hooks, payments, pcs, steamslot, users, web

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"Environment: {settings.environment}")

    # Initialize database
    if settings.debug:
        logger.info("Debug mode: Creating tables if not exist")
        await init_db()

    yield

    # Shutdown
    logger.info("Shutting down...")
    await close_db()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="OBS Fog Server - Streaming management platform",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        openapi_url="/openapi.json" if settings.debug else None,
        lifespan=lifespan,
    )

    # Rate limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Validation error handler
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ):
        errors = []
        for error in exc.errors():
            loc = " -> ".join(str(x) for x in error["loc"])
            errors.append(f"{loc}: {error['msg']}")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": errors},
        )

    # Include routers
    api_prefix = "/api/v1"

    app.include_router(auth.router, prefix=api_prefix)
    app.include_router(users.router, prefix=api_prefix)
    app.include_router(pcs.router, prefix=api_prefix)
    app.include_router(hooks.router)  # No prefix - nginx expects /hook/*
    app.include_router(payments.router, prefix=api_prefix)
    app.include_router(downloads.router, prefix=api_prefix)
    app.include_router(steamslot.router, prefix=api_prefix)

    # Web routes (HTML pages) - must be after API routes
    app.include_router(web.router)

    # Mount static files
    try:
        app.mount("/static", StaticFiles(directory="app/static"), name="static")
    except RuntimeError:
        logger.warning("Static directory not found, skipping mount")

    # Health check endpoint
    @app.get("/healthz", tags=["Health"])
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "ok",
            "version": settings.app_version,
            "environment": settings.environment,
        }

    return app


# Create application instance
app = create_app()
