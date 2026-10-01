"""FastAPI application with API versioning, structured logging, correlation IDs, health probes, and rate limiting."""
import contextlib
import logging
import uuid
from typing import Optional

from fastapi import FastAPI, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from src.api.reminder_manual import router as reminder_manual_router
from src.api.invoice_pause import router as invoice_pause_router
from src.api.reminder_history import router as reminder_history_router
from src.api.invoice_list import router as invoice_list_router
from src.api.health import router as health_router
from src.api.auth import router as auth_router
from src.api.email_template import router as email_template_router
from src.auth import get_current_user, get_password_hash, require_active_subscription
from src.db import SessionLocal, engine
from src.models.user import User
from src.models.base import Base
from src.config.settings import get_settings, validate_production_settings

# Import ALL models so Base.metadata.create_all() knows about every table
from src.models.debtor import Debtor  # noqa: F401
from src.models.invoice import Invoice  # noqa: F401
from src.models.reminder import ReminderLog  # noqa: F401
from src.models.email_template import EmailTemplate  # noqa: F401
from src.models.document_request import DocumentRequest  # noqa: F401

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
logger = logging.getLogger("yourinboxhero")

# Rate limiter - uses client IP by default
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])


class CorrelationIdMiddleware:
    """Middleware to add correlation ID to each request for tracing."""
    
    def __init__(self, app: FastAPI):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        # Generate or extract correlation ID
        correlation_id = None
        for header_name, header_value in scope.get("headers", []):
            if header_name == b"x-correlation-id":
                correlation_id = header_value.decode()
                break
        
        if not correlation_id:
            correlation_id = str(uuid.uuid4())[:8]
        
        # Add to logging context
        logging.LoggerAdapter(logger, {"correlation_id": correlation_id})
        
        async def send_with_correlation(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-correlation-id", correlation_id.encode()))
                message["headers"] = headers
            await send(message)
        
        # Bind correlation_id to request state for access in route handlers
        scope["state"] = scope.get("state", {})
        scope["state"]["correlation_id"] = correlation_id
        
        await self.app(scope, receive, send_with_correlation)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Validate production settings
    settings = get_settings()
    validate_production_settings(settings)

    # Ensure tables are created (useful if alembic isn't run in dev)
    Base.metadata.create_all(bind=engine)

    # Seed a default admin user for local development only. In production
    # this would create a well-known admin/admin login on a public app —
    # never seed default credentials outside dev.
    if settings.environment == "development":
        db = SessionLocal()
        try:
            if db.query(User).count() == 0:
                logger.info("Seeding default admin user (development only)")
                admin_user = User(username="admin", hashed_password=get_password_hash("admin"), company_name="YourInboxHero Admin")
                db.add(admin_user)
                db.commit()
        finally:
            db.close()

    # Start the daily sweep scheduler (overdue transition, reminders,
    # SMS/voice escalation). Runs in-process; the distributed advisory lock
    # in scheduler.py keeps it safe if this app ever scales to >1 instance.
    from src.scheduler import start_scheduler, shutdown_scheduler
    start_scheduler()

    logger.info("Application startup complete", extra={"environment": settings.environment})
    yield
    shutdown_scheduler()
    logger.info("Application shutdown")


app = FastAPI(
    title="YourInboxHero API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if get_settings().environment != "production" else None,
    redoc_url=None,
)

# Rate limiter state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Correlation ID middleware (must be first)
app.add_middleware(CorrelationIdMiddleware)

# CORS middleware - configure allowed origins from settings
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Azure Monitor OpenTelemetry if connection string is present
try:
    if settings.applicationinsights_connection_string:
        from azure.monitor.opentelemetry import configure_azure_monitor
        configure_azure_monitor()
except ImportError:
    pass


# Dependency to get correlation ID in routes
def get_correlation_id(request: Request) -> str:
    return request.state.correlation_id if hasattr(request.state, "correlation_id") else "unknown"


# Health check endpoints (not versioned - infrastructure level)
@app.get("/health/live", tags=["health"])
async def liveness_probe():
    """Liveness probe - process is alive."""
    return {"status": "alive"}


@app.get("/health/ready", tags=["health"])
async def readiness_probe(request: Request, db: Session = Depends(lambda: next(get_db()))):
    """Readiness probe - checks DB and critical dependencies."""
    correlation_id = get_correlation_id(request)
    
    checks = {}
    
    # Database connectivity
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "healthy"
    except Exception as e:
        logger.error("Database health check failed", extra={"correlation_id": correlation_id, "error": str(e)})
        checks["database"] = "unhealthy"
    
    # Resend (if configured)
    checks["resend"] = "healthy" if settings.resend_api_key else "not_configured"
    
    # Overall readiness
    all_healthy = all(v in ("healthy", "not_configured") for v in checks.values())
    
    return {
        "status": "ready" if all_healthy else "not_ready",
        "checks": checks,
        "correlation_id": correlation_id
    }


# Re-export get_db for backward compatibility
from src.db import get_db

# ============================================================
# LEGACY ROUTES (non-versioned) - for backward compatibility
# ============================================================

# Public routes
app.include_router(auth_router, prefix="")
app.include_router(health_router, prefix="")

from src.api.webhooks import router as webhooks_router
app.include_router(webhooks_router, prefix="/api/webhooks")

from src.api.debtor import router as debtor_router
from src.api.invoice_create import router as invoice_create_router
from src.api.analytics import router as analytics_router
from src.api.invoice_pdf import router as invoice_pdf_router

# Protected routes. require_active_subscription allows GET/HEAD/OPTIONS
# through regardless of subscription state (so a lapsed account can still
# view its data) but blocks POST/PUT/PATCH/DELETE until the plan is active.
app.include_router(reminder_manual_router, prefix="", dependencies=[Depends(require_active_subscription)])
app.include_router(invoice_pause_router, prefix="", dependencies=[Depends(require_active_subscription)])
app.include_router(reminder_history_router, prefix="", dependencies=[Depends(require_active_subscription)])
app.include_router(invoice_list_router, prefix="", dependencies=[Depends(require_active_subscription)])
app.include_router(debtor_router, prefix="", dependencies=[Depends(require_active_subscription)])
app.include_router(invoice_create_router, prefix="", dependencies=[Depends(require_active_subscription)])
app.include_router(analytics_router, prefix="", dependencies=[Depends(require_active_subscription)])
app.include_router(invoice_pdf_router, prefix="", dependencies=[Depends(require_active_subscription)])
app.include_router(email_template_router, prefix="", dependencies=[Depends(require_active_subscription)])

from src.api.document_request import router as document_request_router
from src.api.document_client import router as document_client_router
# Public: upload endpoint (debtors use their token), protected CRUD routes
app.include_router(document_request_router, prefix="", tags=["documents"])
app.include_router(document_client_router, prefix="", tags=["document_clients"])

from src.api.stripe_payments import router as stripe_payments_router
# Public: Stripe webhook + checkout session creation + plans listing
app.include_router(stripe_payments_router, prefix="/api/payments", tags=["payments"])


# ============================================================
# API v1 ROUTES (versioned)
# ============================================================
from fastapi import APIRouter
api_v1 = APIRouter(prefix="/api/v1")

# Public routes (v1)
api_v1.include_router(auth_router, prefix="")
api_v1.include_router(health_router, prefix="")
api_v1.include_router(webhooks_router, prefix="/webhooks")

from src.api.debtor import router as debtor_router
from src.api.invoice_create import router as invoice_create_router
from src.api.analytics import router as analytics_router
from src.api.invoice_pdf import router as invoice_pdf_router

# Protected routes (v1)
api_v1.include_router(reminder_manual_router, prefix="", dependencies=[Depends(require_active_subscription)])
api_v1.include_router(invoice_pause_router, prefix="", dependencies=[Depends(require_active_subscription)])
api_v1.include_router(reminder_history_router, prefix="", dependencies=[Depends(require_active_subscription)])
api_v1.include_router(invoice_list_router, prefix="", dependencies=[Depends(require_active_subscription)])
api_v1.include_router(debtor_router, prefix="", dependencies=[Depends(require_active_subscription)])
api_v1.include_router(invoice_create_router, prefix="", dependencies=[Depends(require_active_subscription)])
api_v1.include_router(analytics_router, prefix="", dependencies=[Depends(require_active_subscription)])
api_v1.include_router(invoice_pdf_router, prefix="", dependencies=[Depends(require_active_subscription)])
api_v1.include_router(email_template_router, prefix="", dependencies=[Depends(require_active_subscription)])

api_v1.include_router(document_request_router, prefix="", tags=["documents"])
api_v1.include_router(document_client_router, prefix="", tags=["document_clients"])

api_v1.include_router(stripe_payments_router, prefix="/payments", tags=["payments"])

# Mount API v1
app.include_router(api_v1)


import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Serve React App in production
if os.path.isdir("frontend/dist"):
    app.mount("/assets", StaticFiles(directory="frontend/dist/assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_react(full_path: str):
        return FileResponse("frontend/dist/index.html")