from fastapi import FastAPI
from src.api.reminder_manual import router as reminder_manual_router
from src.api.invoice_pause import router as invoice_pause_router
from src.api.reminder_history import router as reminder_history_router

app = FastAPI()
app.include_router(reminder_manual_router, prefix="")
app.include_router(invoice_pause_router, prefix="")
app.include_router(reminder_history_router, prefix="")