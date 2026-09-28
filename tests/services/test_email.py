import pytest
from unittest.mock import patch, MagicMock
from src.services.email import send_reminder_email
from datetime import date

def test_send_email_calls_sendgrid():
    # Mock the get_sendgrid_client function and its send method
    with patch('src.services.email.get_sendgrid_client') as mock_get_client:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_client.send.return_value = mock_response
        mock_get_client.return_value = mock_client

        # Create dummy objects
        class DummyUser:
            id = "test-id"
            company_name = 'Test Company'
            smtp_host = None
            smtp_port = None
            smtp_username = None
            smtp_password = None
            smtp_from_email = None
            
        class DummyDebtor:
            email = 'client@example.com'
            name = 'Acme Corp'
            user = DummyUser()
            def __init__(self, user_id=None):
                self.user_id = user_id

        class DummyInvoice:
            id = "test-invoice-id"
            invoice_number = 'INV-123'
            amount = 1000.50
            due_date = date(2023, 1, 15)
            payment_instructions = 'Pay via wire transfer.'
            status = type('Status', (), {'value': 'upcoming'})()
            payment_link = None
            debtor = DummyDebtor(user_id='test-id')

        # Call the function
        response = send_reminder_email(DummyInvoice())

        # Assertions
        mock_get_client.assert_called_once()
        mock_client.send.assert_called_once()
        assert response["status"] == "success"
        assert response["method"] == "sendgrid"
        assert response["status_code"] == 202