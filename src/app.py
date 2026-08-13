from fastapi import FastAPI
from src.api.reminder_manual import router as reminder_manual_router

app = FastAPI()
app.include_router(reminder_manual_router, prefix="")