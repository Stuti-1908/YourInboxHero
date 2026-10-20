"""Document reminder service — queries eligible document requests and
processes pre-due reminders. Mirrors src/services/reminder_service.py
for invoices.

Business rules:
  - Only 'pending' document requests qualify (not yet submitted/approved,
    not yet overdue).
  - Overdue requests are NEVER sent this pre-due reminder -- once overdue,
    they're picked up by the SMS/voice escalation sweep instead, same
    legal-guardrail split as invoices.
"""
import logging
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from src.models.document_request import DocumentRequest


def get_eligible_document_requests(db: Session, lookahead_days: int = 14):
    """Return document requests eligible for a pre-due reminder.

    Eligibility criteria:
      1. status == 'pending'
      2. due_date >= today  (not overdue)
      3. due_date <= today + lookahead_days  (within the reminder window)
      4. last_reminder_sent is NULL or < today (no double sends on same day)
    """
    today = date.today()
    upper = today + timedelta(days=lookahead_days)
    today_start = datetime.combine(today, datetime.min.time())

    return (
        db.query(DocumentRequest)
        .join(DocumentRequest.client)
        .filter(
            DocumentRequest.status == "pending",
            DocumentRequest.due_date >= today,
            DocumentRequest.due_date <= upper,
            (DocumentRequest.last_reminder_sent == None)  # noqa: E711 — SQLAlchemy Column needs `== None` for IS NULL
            | (DocumentRequest.last_reminder_sent < today_start)
        )
        .all()
    )


def process_due_document_reminders():
    """Fetch eligible document requests and send one reminder email per
    client covering all of that client's eligible requests.

    Each client is sent and logged independently, so one send failure
    never blocks the rest of the batch.

    Aborts early if the 'reminders-enabled' feature flag is off (shared
    with invoice reminders).
    """
    from src.feature_flags import reminders_enabled
    if not reminders_enabled():
        logging.info('Reminders disabled via feature flag — skipping document reminders')
        return

    from src.db import get_session

    with get_session() as sess:
        requests = get_eligible_document_requests(sess)
        if not requests:
            logging.info('No eligible document requests found')
            return
        # One email per client per day, listing every document they owe,
        # instead of one email per document.
        groups = {}
        for r in requests:
            groups.setdefault(str(r.client_id), []).append(str(r.id))

    from src.services.document_reminder_worker import handle_document_reminder_group, ChaseLimitReached

    sent = 0
    failed = 0
    limit_reached = 0
    for client_id, request_ids in groups.items():
        try:
            handle_document_reminder_group(request_ids)
            sent += 1
        except ChaseLimitReached as exc:
            limit_reached += 1
            logging.warning(f'Chase limit reached, skipping document reminders for client {client_id}: {exc}')
        except Exception as exc:
            failed += 1
            logging.error(f'Reminder failed for document client {client_id}: {exc}')

    logging.info(
        f'Processed document reminders for {len(groups)} client(s): {sent} sent, {failed} failed, '
        f'{limit_reached} skipped (chase limit reached)'
    )
