import os
from unittest.mock import patch, MagicMock
import pytest
from src.services.email import send_reminder_email

def test_send_email_calls_sendgrid():
    # Mock the SendGridAPIClient and its send method
    with patch('src.services.email.SendGridAPIClient') as mock_sendgrid:
        # Create a mock response
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_sendgrid.return_value.send.return_value = mock_response

        # Create a dummy invoice object
        class DummyDebtor:
            email = 'client@example.com'
            name = 'Acme Corp'

        class DummyInvoice:
            debtor = DummyDebtor()
            invoice_number = 'INV-001'
            amount = '1000.00'
            due_date = '2026-09-01'
            payment_instructions = 'Pay via bank transfer.'

        # Call the function
        send_reminder_email(DummyInvoice())

        # Assert that SendGridAPIClient was instantiated with the API key
        mock_sendgrid.assert_called_once_with(os.getenv('SENDGRID_API_KEY'))
        # Assert that the send method was called once
        mock_sendgrid.return_value.send.assert_called_once()