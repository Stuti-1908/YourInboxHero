from fastapi import FastAPI, Depends
from src.api.reminder_manual import router as reminder_manual_router
from src.api.invoice_pause import router as invoice_pause_router
from src.api.reminder_history import router as reminder_history_router
from src.api.invoice_list import router as invoice_list_router
from src.api.health import router as health_router
from src.api.auth import router as auth_router
from src.auth import get_current_user

app = FastAPI()

# Public routes
app.include_router(auth_router, prefix="")
app.include_router(health_router, prefix="")

# Protected routes
app.include_router(reminder_manual_router, prefix="", dependencies=[Depends(get_current_user)])
app.include_router(invoice_pause_router, prefix="", dependencies=[Depends(get_current_user)])
app.include_router(reminder_history_router, prefix="", dependencies=[Depends(get_current_user)])
app.include_router(invoice_list_router, prefix="", dependencies=[Depends(get_current_user)])