"""Document reminder worker — processes individual document-request
reminders. Mirrors src/services/reminder_worker.py for invoices.

ReminderLog now supports document requests (document_request_id column,
added alongside relaxing invoice_id to nullable) -- previously this
module didn't log anything there, leaving no audit trail for document
email/SMS/voice sends despite the History page implying one exists.
"""
import logging
from datetime import datetime, timezone
from typing import List

from src.db import get_session
from src.models.document_request import DocumentRequest
from src.models.reminder import ReminderLog, Channel, ReminderStatus
from src.services.document_email import send_document_request_email
from src.services.usage_limits import can_send_chase, record_chase_used


class ChaseLimitReached(Exception):
    """Raised when the owning user has exhausted their plan's monthly
    chase allowance, or their subscription is no longer active. Mirrors
    reminder_worker.ChaseLimitReached exactly."""
    pass


def handle_document_reminder(doc_request_id: str) -> None:
    """Send a reminder for a single document request. Thin wrapper over
    handle_document_reminder_group, kept for callers that work per request."""
    handle_document_reminder_group([doc_request_id])


def handle_document_reminder_group(doc_request_ids: List[str]) -> None:
    """Send ONE reminder email covering every given document request.
    All requests must belong to the same client; the caller
    (process_due_document_reminders) groups them that way.

    One email counts as one chase against the plan allowance, and every
    request in it gets its own ReminderLog row and last_reminder_sent
    stamp so the History page and same-day dedupe stay per-document.

    Raises:
        ValueError: If any document request is not found.
        ChaseLimitReached: If the owning user has no chases left this
            cycle. Nothing is touched -- no usage increment -- so a retry
            next cycle behaves as if this attempt never happened.
    """
    with get_session() as sess:
        docs = sess.query(DocumentRequest).filter(DocumentRequest.id.in_(doc_request_ids)).all()
        found = {d.id for d in docs}
        missing = [i for i in doc_request_ids if i not in found]
        if missing:
            raise ValueError(f'Document request(s) {missing} not found')
        if len({d.client_id for d in docs}) != 1:
            raise ValueError('Grouped document reminders must all belong to one client')
        docs.sort(key=lambda d: (d.due_date, d.title))

        user = docs[0].client.user
        if not can_send_chase(user):
            raise ChaseLimitReached(
                f'User {user.id} cannot receive a chase right now '
                f'(subscription_status={user.subscription_status}, '
                f'chases_used={user.chases_used}/{user.chases_limit})'
            )

        now = datetime.now(timezone.utc)
        try:
            send_document_request_email(docs)
        except Exception as exc:
            logging.error(f'Failed to send reminder for document request(s) {doc_request_ids}: {exc}')
            for doc in docs:
                sess.add(ReminderLog(
                    document_request_id=doc.id,
                    sent_at=now,
                    channel=Channel.email,
                    payload={'title': doc.title, 'client_email': doc.client.email},
                    status=ReminderStatus.failed,
                ))
            sess.commit()
            # Re-raise so the caller's per-group try/except in
            # process_due_document_reminders counts it as failed rather
            # than silently treating it as sent.
            raise

        for doc in docs:
            sess.add(ReminderLog(
                document_request_id=doc.id,
                sent_at=now,
                channel=Channel.email,
                payload={'title': doc.title, 'client_email': doc.client.email},
                status=ReminderStatus.sent,
            ))
            doc.last_reminder_sent = now
        record_chase_used(user, sess, channel='email', invoice_id=docs[0].id)
        sess.commit()
