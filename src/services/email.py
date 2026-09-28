"""Email service with retry logic and structured logging."""
import os
import smtplib
from email.message import EmailMessage
from typing import Any, Dict

import structlog
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from jinja2 import Environment, FileSystemLoader
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.config.settings import get_settings
from src.db import SessionLocal
from src.models.email_template import EmailTemplate

logger = structlog.get_logger(__name__)
settings = get_settings()

# Singleton SendGrid client
_sendgrid_client: SendGridAPIClient | None = None


def get_sendgrid_client() -> SendGridAPIClient:
    """Get or create SendGrid client singleton."""
    global _sendgrid_client
    if _sendgrid_client is None:
        if not settings.sendgrid_api_key:
            raise RuntimeError("SENDGRID_API_KEY not configured")
        _sendgrid_client = SendGridAPIClient(settings.sendgrid_api_key)
    return _sendgrid_client


def render_template(invoice: Any) -> str:
    """Render default email template."""
    env = Environment(loader=FileSystemLoader('templates'))
    tmpl = env.get_template('reminder_email.html')
    return tmpl.render(invoice=invoice)


def _build_replacements(invoice: Any, company_name: str) -> Dict[str, str]:
    """Build template variable replacements."""
    return {
        "{{debtor_name}}": invoice.debtor.name,
        "{{amount_due}}": f"${invoice.amount:.2f}",
        "{{invoice_number}}": invoice.invoice_number,
        "{{due_date}}": str(invoice.due_date),
        "{{company_name}}": company_name,
        "{{payment_link}}": invoice.payment_link or "",
    }


def _apply_replacements(text: str, replacements: Dict[str, str]) -> str:
    """Apply template variable replacements."""
    for key, val in replacements.items():
        text = text.replace(key, val)
    return text


@retry(
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type((smtplib.SMTPException, ConnectionError, TimeoutError)),
    reraise=True,
)
def _send_via_smtp(
    host: str,
    port: int,
    username: str,
    password: str,
    from_email: str,
    to_email: str,
    subject: str,
    html_body: str,
) -> Dict[str, str]:
    """Send email via custom SMTP with retry logic."""
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = from_email
    msg['To'] = to_email
    msg.set_content("Please enable HTML to view this email.")
    msg.add_alternative(html_body, subtype='html')

    server = smtplib.SMTP(host, port, timeout=30)
    try:
        server.starttls()
        server.login(username, password)
        server.send_message(msg)
        return {"status": "success", "method": "smtp"}
    finally:
        server.quit()


@retry(
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type((ConnectionError, TimeoutError)),
    reraise=True,
)
def _send_via_sendgrid(
    to_email: str,
    subject: str,
    html_body: str,
) -> Dict[str, Any]:
    """Send email via SendGrid with retry logic."""
    sg = get_sendgrid_client()
    message = Mail(
        from_email='reminders@yourinboxhero.com',
        to_emails=to_email,
        subject=subject,
        html_content=html_body,
    )
    response = sg.send(message)
    if response.status_code >= 400:
        raise Exception(f"SendGrid error {response.status_code}: {response.body}")
    return {"status": "success", "method": "sendgrid", "status_code": response.status_code}


def send_reminder_email(invoice: Any) -> Dict[str, Any]:
    """
    Send reminder email for an invoice.
    
    Tries custom SMTP first, falls back to SendGrid.
    Uses retry logic for transient failures.
    """
    correlation_id = getattr(invoice, 'correlation_id', 'unknown')
    user = invoice.debtor.user
    company_name = user.company_name or 'YourInboxHero'
    
    logger.info(
        "preparing_reminder_email",
        invoice_id=str(invoice.id),
        invoice_number=invoice.invoice_number,
        debtor_email=invoice.debtor.email,
        correlation_id=correlation_id,
    )
    
    # Get custom template if available
    db = SessionLocal()
    try:
        custom_template = db.query(EmailTemplate).filter(
            EmailTemplate.user_id == user.id,
            EmailTemplate.template_type == invoice.status.value
        ).first()
    finally:
        db.close()
    
    replacements = _build_replacements(invoice, company_name)
    
    if custom_template:
        subject = _apply_replacements(custom_template.subject, replacements)
        body = _apply_replacements(custom_template.body, replacements)
        html_body = body.replace('\n', '<br>')
    else:
        subject = f'Reminder: Invoice {invoice.invoice_number} from {company_name} is due'
        html_body = render_template(invoice)
    
    # Try custom SMTP first
    if user.smtp_host and user.smtp_port and user.smtp_username and user.smtp_password:
        try:
            result = _send_via_smtp(
                host=user.smtp_host,
                port=int(user.smtp_port),
                username=user.smtp_username,
                password=user.smtp_password,
                from_email=user.smtp_from_email or user.smtp_username,
                to_email=invoice.debtor.email,
                subject=subject,
                html_body=html_body,
            )
            logger.info(
                "reminder_email_sent_smtp",
                invoice_id=str(invoice.id),
                debtor_email=invoice.debtor.email,
                correlation_id=correlation_id,
            )
            return result
        except Exception as e:
            logger.warning(
                "smtp_send_failed_falling_back_to_sendgrid",
                invoice_id=str(invoice.id),
                error=str(e),
                correlation_id=correlation_id,
            )
    
    # Fallback to SendGrid
    try:
        result = _send_via_sendgrid(
            to_email=invoice.debtor.email,
            subject=subject,
            html_body=html_body,
        )
        logger.info(
            "reminder_email_sent_sendgrid",
            invoice_id=str(invoice.id),
            debtor_email=invoice.debtor.email,
            correlation_id=correlation_id,
        )
        return result
    except Exception as e:
        logger.error(
            "reminder_email_failed_all_methods",
            invoice_id=str(invoice.id),
            debtor_email=invoice.debtor.email,
            error=str(e),
            correlation_id=correlation_id,
        )
        raise