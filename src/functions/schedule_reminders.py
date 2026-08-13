"""Azure Function Timer entry point — daily pre-due reminder scheduler.

Triggered by a TimerTrigger (configured in function.json to run daily at 00:00 UTC).
Calls process_due_reminders() to query eligible invoices and enqueue reminders.
"""
import logging


def main(mytimer) -> None:
    """Entry point invoked by the Azure Functions runtime on a timer schedule."""
    logging.info('Reminder scheduler triggered')
    # Deferred import to avoid circular dependency at module load time
    from src.services.reminder_service import process_due_reminders
    process_due_reminders()
