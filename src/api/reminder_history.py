"""Reminder history endpoint — read-only access to the audit log.

Provides JSON and CSV export of reminder_log entries for compliance
and operational visibility.
"""
import csv
import io
from typing import List, Optional

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from src.db import get_db
from src.models.reminder import ReminderLog


class ReminderLogResponse(BaseModel):
    """Pydantic schema for a single reminder log entry."""
    id: str
    invoice_id: str
    sent_at: str
    channel: str
    status: str

    model_config = ConfigDict(from_attributes=True)


router = APIRouter()


@router.get('/reminders/history', response_model=List[ReminderLogResponse])
def reminder_history(limit: int = 100, db: Session = Depends(get_db)):
    """Return the most recent reminder log entries as JSON."""
    rows = (
        db.query(ReminderLog)
        .order_by(ReminderLog.sent_at.desc())
        .limit(limit)
        .all()
    )
    return [
        ReminderLogResponse(
            id=str(r.id),
            invoice_id=str(r.invoice_id),
            sent_at=str(r.sent_at) if r.sent_at else '',
            channel=r.channel.value if hasattr(r.channel, 'value') else str(r.channel),
            status=r.status.value if hasattr(r.status, 'value') else str(r.status),
        )
        for r in rows
    ]


@router.get('/reminders/history/csv')
def reminder_history_csv(limit: int = 100, db: Session = Depends(get_db)):
    """Return the most recent reminder log entries as a CSV download."""
    rows = (
        db.query(ReminderLog)
        .order_by(ReminderLog.sent_at.desc())
        .limit(limit)
        .all()
    )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['id', 'invoice_id', 'sent_at', 'channel', 'status'])
    for r in rows:
        writer.writerow([
            str(r.id),
            str(r.invoice_id),
            str(r.sent_at) if r.sent_at else '',
            r.channel.value if hasattr(r.channel, 'value') else str(r.channel),
            r.status.value if hasattr(r.status, 'value') else str(r.status),
        ])
    return Response(
        content=output.getvalue(),
        media_type='text/csv',
        headers={'Content-Disposition': 'attachment; filename=reminder_history.csv'},
    )
