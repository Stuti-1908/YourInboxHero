"""Azure Function Timer entry point — nightly overdue transition job.

Triggered by a TimerTrigger (configured in function.json, e.g. daily at 00:30 UTC).
Finds all invoices past their due_date and marks them 'overdue', preventing
further automated reminders (legal guardrail).
"""
import logging


def main(mytimer) -> None:
    """Entry point invoked by the Azure Functions runtime on a timer schedule."""
    logging.info('Overdue transition job started')
    from src.db import get_session
    from src.services.overdue_service import transition_overdue

    with get_session() as sess:
        count = transition_overdue(sess)
        logging.info(f'Transitioned {count} invoice(s) to overdue status')
