"""SMTP transport: implicit TLS vs STARTTLS, credential verification, and
the failure handling that used to hide the real error."""
import smtplib
from unittest.mock import MagicMock, patch

import pytest

from src.services import email as email_service


def test_port_465_uses_smtp_ssl():
    with patch("src.services.email.smtplib.SMTP_SSL") as ssl_cls, \
         patch("src.services.email.smtplib.SMTP") as plain_cls:
        email_service._open_smtp("smtp.gmail.com", 465)
    ssl_cls.assert_called_once()
    plain_cls.assert_not_called()


def test_port_587_uses_starttls():
    server = MagicMock()
    with patch("src.services.email.smtplib.SMTP", return_value=server) as plain_cls:
        email_service._open_smtp("smtp.gmail.com", 587)
    plain_cls.assert_called_once()
    server.starttls.assert_called_once()


def test_verify_reports_auth_failure_not_disconnect():
    """quit() on a connection the provider already dropped must not
    replace the real authentication error."""
    server = MagicMock()
    server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted")
    server.quit.side_effect = smtplib.SMTPServerDisconnected("please run connect() first")
    with patch("src.services.email._open_smtp", return_value=server):
        with pytest.raises(ValueError) as exc:
            email_service.verify_smtp_credentials("smtp.gmail.com", 587, "a@b.com", "bad")
    assert "rejected" in str(exc.value)
    assert "Username and Password not accepted" in str(exc.value)


def test_send_does_not_retry_auth_failure():
    server = MagicMock()
    server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"bad creds")
    with patch("src.services.email._open_smtp", return_value=server) as opener:
        with pytest.raises(smtplib.SMTPAuthenticationError):
            email_service._send_via_smtp(
                host="smtp.gmail.com", port=587, username="a", password="b",
                from_email="a@b.com", to_email="c@d.com", subject="s", html_body="<p>x</p>",
            )
    assert opener.call_count == 1


def test_send_success_returns_smtp_method():
    server = MagicMock()
    with patch("src.services.email._open_smtp", return_value=server):
        result = email_service._send_via_smtp(
            host="smtp.gmail.com", port=587, username="a", password="b",
            from_email="a@b.com", to_email="c@d.com", subject="s", html_body="<p>x</p>",
        )
    assert result == {"status": "success", "method": "smtp"}
    server.send_message.assert_called_once()


def test_open_smtp_refuses_unlisted_host_without_connecting():
    with patch("src.services.email.smtplib.SMTP") as plain, patch("src.services.email.smtplib.SMTP_SSL") as ssl:
        with pytest.raises(ValueError):
            email_service._open_smtp("169.254.169.254", 587)
        with pytest.raises(ValueError):
            email_service._open_smtp("smtp.gmail.com", 25)
    plain.assert_not_called()
    ssl.assert_not_called()


def test_open_smtp_closes_socket_when_starttls_fails():
    with patch("src.services.email.smtplib.SMTP") as plain:
        plain.return_value.starttls.side_effect = smtplib.SMTPException("no tls")
        with pytest.raises(smtplib.SMTPException):
            email_service._open_smtp("smtp.gmail.com", 587)
    plain.return_value.close.assert_called_once()


def test_verify_treats_hangup_during_login_as_rejected_credentials():
    """Gmail frequently drops the connection on a bad password instead of
    replying 535; the customer still needs the app-password hint."""
    with patch("src.services.email._open_smtp") as opener:
        opener.return_value.login.side_effect = smtplib.SMTPServerDisconnected("Connection unexpectedly closed")
        with pytest.raises(ValueError, match="app password"):
            email_service.verify_smtp_credentials("smtp.gmail.com", 587, "a@b.com", "bad")
