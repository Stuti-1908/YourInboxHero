import contextlib
from fastapi import FastAPI, Depends
from src.api.reminder_manual import router as reminder_manual_router
from src.api.invoice_pause import router as invoice_pause_router
from src.api.reminder_history import router as reminder_history_router
from src.api.invoice_list import router as invoice_list_router
from src.api.health import router as health_router
from src.api.auth import router as auth_router
from src.auth import get_current_user, get_password_hash
from src.db import SessionLocal
from src.models.user import User
from src.models.base import Base
from src.db import engine
import logging

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure tables are created (useful if alembic isn't run in dev)
    Base.metadata.create_all(bind=engine)
    
    # Seed default admin user
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            logging.info("Seeding default admin user")
            admin_user = User(username="admin", hashed_password=get_password_hash("admin"))
            db.add(admin_user)
            db.commit()
    finally:
        db.close()
    yield

import os
from azure.monitor.opentelemetry import configure_azure_monitor

# Initialize Azure Monitor OpenTelemetry if connection string is present
if os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"):
    configure_azure_monitor()

app = FastAPI(lifespan=lifespan)

# Public routes
app.include_router(auth_router, prefix="")
app.include_router(health_router, prefix="")

from src.api.debtor import router as debtor_router
from src.api.invoice_create import router as invoice_create_router

# Protected routes
app.include_router(reminder_manual_router, prefix="", dependencies=[Depends(get_current_user)])
app.include_router(invoice_pause_router, prefix="", dependencies=[Depends(get_current_user)])
app.include_router(reminder_history_router, prefix="", dependencies=[Depends(get_current_user)])
app.include_router(invoice_list_router, prefix="", dependencies=[Depends(get_current_user)])
app.include_router(debtor_router, prefix="", dependencies=[Depends(get_current_user)])
app.include_router(invoice_create_router, prefix="", dependencies=[Depends(get_current_user)])

import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Serve React App in production
if os.path.isdir("frontend/dist"):
    app.mount("/assets", StaticFiles(directory="frontend/dist/assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_react(full_path: str):
        return FileResponse("frontend/dist/index.html")