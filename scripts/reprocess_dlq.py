import os
import logging
from azure.servicebus import ServiceBusClient

SERVICE_BUS_CONNECTION_STR = os.getenv('SERVICE_BUS_CONNECTION_STRING')
QUEUE_NAME = os.getenv('REMINDER_QUEUE_NAME', 'reminder-queue')
DLQ_NAME = f"{QUEUE_NAME}/$DeadLetterQueue"

def reprocess_dlq():
    """Reads messages from the Dead Letter Queue and moves them back to the main queue."""
    if not SERVICE_BUS_CONNECTION_STR:
        logging.error("SERVICE_BUS_CONNECTION_STRING not set")
        return

    client = ServiceBusClient.from_connection_string(SERVICE_BUS_CONNECTION_STR)
    dlq_receiver = client.get_queue_receiver(DLQ_NAME)
    main_sender = client.get_queue_sender(QUEUE_NAME)
    
    count = 0
    with dlq_receiver, main_sender:
        messages = dlq_receiver.receive_messages(max_message_count=50, max_wait_time=5)
        for msg in messages:
            try:
                # Clone message and send to main queue
                # msg.message_id is preserved by default when cloning if not specified, 
                # but we re-create it to clear DLQ properties
                from azure.servicebus import ServiceBusMessage
                new_msg = ServiceBusMessage(str(msg), message_id=msg.message_id)
                main_sender.send_messages(new_msg)
                
                # Complete the message on the DLQ so it's removed
                dlq_receiver.complete_message(msg)
                count += 1
                logging.info(f"Reprocessed DLQ message {msg.message_id}")
            except Exception as e:
                logging.error(f"Failed to reprocess message {msg.message_id}: {e}")
                
    logging.info(f"Finished reprocessing {count} messages from DLQ.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    reprocess_dlq()
