"""Azure Function Service Bus consumer — processes reminder messages from the queue.

Triggered by a ServiceBusTrigger bound to the 'reminder-queue'. Each message
contains an invoice_id; the worker looks it up, sends the email, and logs it.
"""
import logging


def main(msg) -> None:
    """Entry point invoked by Azure Functions on each Service Bus message."""
    invoice_id = msg.get_body().decode('utf-8') if hasattr(msg, 'get_body') else str(msg)
    logging.info(f'Processing reminder for invoice {invoice_id}')
    # Deferred import to avoid circular deps at module load time
    from src.services.reminder_worker import handle_invoice_reminder
    handle_invoice_reminder(invoice_id)
