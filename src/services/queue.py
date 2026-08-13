"""Azure Service Bus queue integration — enqueues reminder tasks for async processing.

In production, the connection string is injected via Azure Key Vault / Managed Identity.
For local testing, SERVICE_BUS_CONNECTION_STRING must be set (tests mock this entirely).
"""
import os

SERVICE_BUS_CONNECTION_STR = os.getenv('SERVICE_BUS_CONNECTION_STRING')
QUEUE_NAME = os.getenv('REMINDER_QUEUE_NAME', 'reminder-queue')


def enqueue_reminder(invoice_id: str) -> None:
    """Push an invoice ID onto the Service Bus reminder queue."""
    from azure.servicebus import ServiceBusClient, ServiceBusMessage

    client = ServiceBusClient.from_connection_string(SERVICE_BUS_CONNECTION_STR)
    with client.get_queue_sender(QUEUE_NAME) as sender:
        msg = ServiceBusMessage(invoice_id)
        sender.send_messages(msg)
