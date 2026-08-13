import pytest
from unittest.mock import patch, MagicMock
from src.services.email import send_reminder_email
from datetime import date

def test_send_email_calls_sendgrid():
    # Mock the SendGridAPIClient and its send method
    with patch('src.services.email.SendGridAPIClient') as mock_sendgrid:
        # Create a mock response
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_sendgrid.return_value.send.return_value = mock_response

        # Create dummy objects
        class DummyUser:
            company_name = 'Test Company'
            
        class DummyDebtor:
            email = 'client@example.com'
            name = 'Acme Corp'
            user = DummyUser()
            def __init__(self, user_id=None):
                self.user_id = user_id

        class DummyInvoice:
            invoice_number = 'INV-123'
            amount = 1000.50
            due_date = date(2023, 1, 15)
            payment_instructions = 'Pay via wire transfer.'
            debtor = DummyDebtor(user_id='test-id')

        # Call the function
        response = send_reminder_email(DummyInvoice())

        # Assertions
        mock_sendgrid.assert_called_once()
        mock_sendgrid.return_value.send.assert_called_once()
        assert response.status_code == 202