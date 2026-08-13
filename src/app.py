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

app = FastAPI(lifespan=lifespan)

# Public routes
app.include_router(auth_router, prefix="")
app.include_router(health_router, prefix="")

from src.api.debtor_create import router as debtor_create_router
from src.api.invoice_create import router as invoice_create_router
from src.api.debtor_list import router as debtor_list_router

# Protected routes
app.include_router(reminder_manual_router, prefix="", dependencies=[Depends(get_current_user)])
app.include_router(invoice_pause_router, prefix="", dependencies=[Depends(get_current_user)])
app.include_router(reminder_history_router, prefix="", dependencies=[Depends(get_current_user)])
app.include_router(invoice_list_router, prefix="", dependencies=[Depends(get_current_user)])
app.include_router(debtor_create_router, prefix="", dependencies=[Depends(get_current_user)])
app.include_router(invoice_create_router, prefix="", dependencies=[Depends(get_current_user)])
app.include_router(debtor_list_router, prefix="", dependencies=[Depends(get_current_user)])