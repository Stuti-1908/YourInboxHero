"""Tests for queue service — enqueue_reminder using mocked Azure Service Bus.

Since azure.servicebus may not be installed in the test environment, we mock
the import at the point where enqueue_reminder calls it.
"""
import sys
from unittest.mock import patch, MagicMock, Mock
import types


def _install_fake_azure_servicebus():
    """Install a fake azure.servicebus module into sys.modules so imports succeed."""
    azure_mod = types.ModuleType('azure')
    azure_mod.__path__ = []
    servicebus_mod = types.ModuleType('azure.servicebus')
    servicebus_mod.ServiceBusClient = MagicMock()
    servicebus_mod.ServiceBusMessage = MagicMock()
    azure_mod.servicebus = servicebus_mod
    sys.modules['azure'] = azure_mod
    sys.modules['azure.servicebus'] = servicebus_mod
    return servicebus_mod


def test_enqueue_calls_servicebus():
    """enqueue_reminder should create a ServiceBusClient, get a queue sender,
    and send a ServiceBusMessage with the invoice ID."""
    fake_sb = _install_fake_azure_servicebus()

    # Reset mocks
    mock_client_class = fake_sb.ServiceBusClient
    mock_message_class = fake_sb.ServiceBusMessage
    mock_client_class.reset_mock()
    mock_message_class.reset_mock()

    # Set up the sender context manager chain
    mock_sender = MagicMock()
    mock_client_class.from_connection_string.return_value.get_queue_sender.return_value.__enter__ = MagicMock(return_value=mock_sender)
    mock_client_class.from_connection_string.return_value.get_queue_sender.return_value.__exit__ = MagicMock(return_value=False)

    # Force reimport to pick up the fake module
    import importlib
    import src.services.queue as queue_mod
    importlib.reload(queue_mod)

    queue_mod.enqueue_reminder('invoice-1234')

    # Verify ServiceBusClient was created from connection string
    mock_client_class.from_connection_string.assert_called_once()
    # Verify the sender was requested for the correct queue
    mock_client_class.from_connection_string.return_value.get_queue_sender.assert_called_once_with('reminder-queue')
    # Verify a message was sent
    mock_sender.send_messages.assert_called_once()
    # Verify ServiceBusMessage was created with the invoice ID
    mock_message_class.assert_called_once_with('invoice-1234')

    # Clean up
    sys.modules.pop('azure.servicebus', None)
    sys.modules.pop('azure', None)


def test_enqueue_uses_custom_queue_name(monkeypatch):
    """If REMINDER_QUEUE_NAME env var is set, enqueue should use that queue."""
    monkeypatch.setenv('REMINDER_QUEUE_NAME', 'custom-queue')

    fake_sb = _install_fake_azure_servicebus()
    mock_client_class = fake_sb.ServiceBusClient
    mock_client_class.reset_mock()

    mock_sender = MagicMock()
    mock_client_class.from_connection_string.return_value.get_queue_sender.return_value.__enter__ = MagicMock(return_value=mock_sender)
    mock_client_class.from_connection_string.return_value.get_queue_sender.return_value.__exit__ = MagicMock(return_value=False)

    import importlib
    import src.services.queue as queue_mod
    importlib.reload(queue_mod)

    queue_mod.enqueue_reminder('invoice-5678')

    mock_client_class.from_connection_string.return_value.get_queue_sender.assert_called_once_with('custom-queue')

    # Clean up
    sys.modules.pop('azure.servicebus', None)
    sys.modules.pop('azure', None)
