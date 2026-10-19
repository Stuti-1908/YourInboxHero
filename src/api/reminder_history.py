"""Endpoint to view the history of sent reminders."""
from datetime import date
from typing import List, Optional
import csv
import io

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from sqlalchemy import union_all, select

from src.db import get_db
from src.models.reminder import ReminderLog
from src.models.invoice import Invoice
from src.models.debtor import Debtor
from src.models.document_request import DocumentRequest
from src.models.document_client import DocumentClient
from src.auth import get_current_user
from src.models.user import User


class ReminderLogResponse(BaseModel):
    id: str
    invoice_id: Optional[str] = None
    document_request_id: Optional[str] = None
    item_label: str
    contact_name: str
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
    """Retrieve history of reminders sent, for both invoices and document
    requests."""
    rows = _fetch_history_rows(start_date, end_date, limit, db, current_user)
    return [
        {
            "id": r.id,
            "invoice_id": r.invoice_id,
            "document_request_id": r.document_request_id,
            "item_label": r.item_label,
            "contact_name": r.contact_name,
            "sent_at": r.sent_at.isoformat() if r.sent_at else "",
            "channel": r.channel,
            "status": r.status,
            "payload": r.payload,
        } for r in rows
    ]


@router.get('/reminders/history/csv')
def get_reminder_history_csv(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Export reminder history as CSV, for both invoices and document
    requests."""
    rows = _fetch_history_rows(start_date, end_date, None, db, current_user)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['id', 'type', 'item_label', 'contact_name', 'sent_at', 'channel', 'status'])
    for r in rows:
        row_type = 'invoice' if r.invoice_id else 'document'
        writer.writerow([r.id, row_type, r.item_label, r.contact_name, r.sent_at, r.channel, r.status])

    response = Response(content=output.getvalue(), media_type="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=reminders_history.csv"
    return response


def _fetch_history_rows(start_date, end_date, limit, db, current_user):
    """Union of invoice-linked and document-request-linked reminder logs
    scoped to the current user, since a single ORM join can only traverse
    one of ReminderLog's two mutually-exclusive foreign keys at a time."""
    invoice_q = (
        select(
            ReminderLog.id, ReminderLog.invoice_id, ReminderLog.document_request_id,
            Invoice.invoice_number.label("item_label"), Debtor.name.label("contact_name"),
            ReminderLog.sent_at, ReminderLog.channel, ReminderLog.status, ReminderLog.payload,
        )
        .join(Invoice, ReminderLog.invoice_id == Invoice.id)
        .join(Debtor, Invoice.debtor_id == Debtor.id)
        .where(Debtor.user_id == current_user.id)
    )
    document_q = (
        select(
            ReminderLog.id, ReminderLog.invoice_id, ReminderLog.document_request_id,
            DocumentRequest.title.label("item_label"), DocumentClient.name.label("contact_name"),
            ReminderLog.sent_at, ReminderLog.channel, ReminderLog.status, ReminderLog.payload,
        )
        .join(DocumentRequest, ReminderLog.document_request_id == DocumentRequest.id)
        .join(DocumentClient, DocumentRequest.client_id == DocumentClient.id)
        .where(DocumentClient.user_id == current_user.id)
    )

    if start_date:
        invoice_q = invoice_q.where(ReminderLog.sent_at >= start_date)
        document_q = document_q.where(ReminderLog.sent_at >= start_date)
    if end_date:
        invoice_q = invoice_q.where(ReminderLog.sent_at <= end_date)
        document_q = document_q.where(ReminderLog.sent_at <= end_date)

    # union_all() can't portably take an ORDER BY referencing either select's
    # own columns, so wrap it and order by the unioned subquery's column.
    combined = union_all(invoice_q, document_q)
    subq = combined.subquery()
    final_q = select(subq).order_by(subq.c.sent_at.desc())
    if limit:
        final_q = final_q.limit(limit)

    return db.execute(final_q).all()
