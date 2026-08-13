"""Endpoint to view the history of sent reminders."""
from datetime import date
from typing import List, Optional
import csv
import io

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from src.db import get_db
from src.models.reminder import ReminderLog
from src.models.invoice import Invoice
from src.models.debtor import Debtor
from src.auth import get_current_user
from src.models.user import User

class ReminderLogResponse(BaseModel):
    id: str
    invoice_id: str
    sent_at: str
    channel: str
    status: str
    payload: Optional[dict] = None

    model_config = ConfigDict(from_attributes=True)


router = APIRouter()


@router.get('/reminders/history', response_model=List[ReminderLogResponse])
def get_reminder_history(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    limit: Optional[int] = Query(100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve history of reminders sent."""
    query = _build_history_query(start_date, end_date, db, current_user)
    if limit:
        query = query.limit(limit)
    logs = query.all()
    
    return [
        {
            "id": log.id,
            "invoice_id": log.invoice_id,
            "sent_at": log.sent_at.isoformat() if log.sent_at else "",
            "channel": log.channel.value,
            "status": log.status.value,
            "payload": log.payload
        } for log in logs
    ]

@router.get('/reminders/history/csv')
def get_reminder_history_csv(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Export reminder history as CSV."""
    query = _build_history_query(start_date, end_date, db, current_user)
    logs = query.all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['id', 'invoice_id', 'sent_at', 'channel', 'status'])
    for log in logs:
        writer.writerow([log.id, log.invoice_id, log.sent_at, log.channel.value, log.status.value])
    
    response = Response(content=output.getvalue(), media_type="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=reminders_history.csv"
    return response

def _build_history_query(start_date, end_date, db, current_user):
    query = (
        db.query(ReminderLog)
        .join(Invoice, ReminderLog.invoice_id == Invoice.id)
        .join(Debtor, Invoice.debtor_id == Debtor.id)
        .filter(Debtor.user_id == current_user.id)
    )
    if start_date:
        query = query.filter(ReminderLog.sent_at >= start_date)
    if end_date:
        query = query.filter(ReminderLog.sent_at <= end_date)
    return query.order_by(ReminderLog.sent_at.desc())
