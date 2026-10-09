"""Document reminder worker — processes individual document-request
reminders. Mirrors src/services/reminder_worker.py for invoices.

Unlike invoices, document requests don't get a ReminderLog audit-trail
entry -- that table's invoice_id column is NOT NULL and FK'd
specifically to invoice, so logging document sends there isn't possible
without a schema change. DocumentRequest already carries its own
last_reminder_sent/sms_sent_count/voice_call_count columns, which is
the equivalent visibility for this module (same fields the UI's
Document Collection table already displays).
"""
import logging
from datetime import datetime, timezone

from src.db import get_session
from src.models.document_request import DocumentRequest
from src.services.document_email import send_document_request_email
from src.services.usage_limits import can_send_chase, record_chase_used


class ChaseLimitReached(Exception):
    """Raised when the owning user has exhausted their plan's monthly
    chase allowance, or their subscription is no longer active. Mirrors
    reminder_worker.ChaseLimitReached exactly."""
    pass


def handle_document_reminder(doc_request_id: str) -> None:
    """Send a reminder for a single document request.

    Args:
        doc_request_id: The document request primary key (string UUID).

    Raises:
        ValueError: If the document request is not found.
        ChaseLimitReached: If the owning user has no chases left this
            cycle. The request is left untouched -- no usage increment --
            so a retry next cycle behaves as if this attempt never happened.
    """
    with get_session() as sess:
        doc = sess.query(DocumentRequest).filter(DocumentRequest.id == doc_request_id).first()
        if not doc:
            raise ValueError(f'Document request {doc_request_id} not found')

        user = doc.client.user
        if not can_send_chase(user):
            raise ChaseLimitReached(
                f'User {user.id} cannot receive a chase right now '
                f'(subscription_status={user.subscription_status}, '
                f'chases_used={user.chases_used}/{user.chases_limit})'
            )

        try:
            send_document_request_email(doc)
        except Exception as exc:
            logging.error(f'Failed to send reminder for document request {doc_request_id}: {exc}')
            # Unlike invoices (which always log+commit a failed attempt to
            # ReminderLog), a failed document-email send here simply isn't
            # recorded anywhere -- re-raise so the caller's per-request
            # try/except in process_due_document_reminders counts it as
            # failed rather than silently treating it as sent.
            raise

        doc.last_reminder_sent = datetime.now(timezone.utc)
        record_chase_used(user, sess, channel='email', invoice_id=doc_request_id)
        sess.commit()
