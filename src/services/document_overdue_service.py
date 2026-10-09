"""Overdue transition service for document requests — mirrors
src/services/overdue_service.py for invoices exactly.

Business rule: any 'pending' document request whose due_date is strictly
before today must transition to 'overdue'. Once overdue, no automated
pre-due reminder is sent again (it moves into the SMS/voice escalation
path instead, same as an overdue invoice) -- 'submitted'/'approved'
requests are already resolved and never touched here.
"""
from datetime import date

from src.models.document_request import DocumentRequest


def transition_overdue(session):
    """Find all pending document requests past their due date and mark
    them overdue.

    Args:
        session: SQLAlchemy session (caller is responsible for commit).

    Returns:
        int: Number of document requests transitioned.
    """
    today = date.today()
    overdue_requests = (
        session.query(DocumentRequest)
        .filter(
            DocumentRequest.due_date < today,
            DocumentRequest.status == "pending",
        )
        .all()
    )
    for req in overdue_requests:
        req.status = "overdue"
    session.commit()
    return len(overdue_requests)
