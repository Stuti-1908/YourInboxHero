"""Email service with retry logic and structured logging."""
import smtplib
from email.message import EmailMessage
from typing import Any, Dict

import requests
import structlog
from jinja2 import Environment, FileSystemLoader
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.config.settings import get_settings
from src.db import SessionLocal
from src.models.email_template import EmailTemplate
from src.services.plan_features import plan_has_feature
from src.services.secrets import decrypt_secret

logger = structlog.get_logger(__name__)
settings = get_settings()

RESEND_API_URL = "https://api.resend.com/emails"


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
    retry=retry_if_exception_type((ConnectionError, TimeoutError, requests.exceptions.RequestException)),
    reraise=True,
)
def _send_via_resend(
    to_email: str,
    subject: str,
    html_body: str,
) -> Dict[str, Any]:
    """Send email via Resend with retry logic."""
    if not settings.resend_api_key:
        raise RuntimeError("RESEND_API_KEY not configured")

    response = requests.post(
        RESEND_API_URL,
        headers={
            "Authorization": f"Bearer {settings.resend_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "from": settings.resend_from_email,
            "to": [to_email],
            "subject": subject,
            "html": html_body,
        },
        timeout=15,
    )
    if response.status_code >= 400:
        raise Exception(f"Resend error {response.status_code}: {response.text}")
    return {"status": "success", "method": "resend", "status_code": response.status_code, "id": response.json().get("id")}


def send_reminder_email(invoice: Any) -> Dict[str, Any]:
    """
    Send reminder email for an invoice.

    Tries custom SMTP first, falls back to Resend.
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

    # Custom templates and custom SMTP are both Growth+ features. A
    # downgraded or never-upgraded Starter user may still have saved
    # values for either (saving isn't blocked — see email_template.py and
    # auth.py's /users/me — only applying them is), so re-check the plan
    # at send time rather than trusting that the data being present means
    # it's allowed to be used.
    has_custom_templates = plan_has_feature(user.subscription_plan, "custom_templates")
    has_custom_smtp = plan_has_feature(user.subscription_plan, "custom_smtp")

    # Get custom template if available and entitled
    custom_template = None
    if has_custom_templates:
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

    # Try custom SMTP first, if entitled
    smtp_password = decrypt_secret(user.smtp_password) if has_custom_smtp else None
    if has_custom_smtp and user.smtp_host and user.smtp_port and user.smtp_username and smtp_password:
        try:
            result = _send_via_smtp(
                host=user.smtp_host,
                port=int(user.smtp_port),
                username=user.smtp_username,
                password=smtp_password,
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
                "smtp_send_failed_falling_back_to_resend",
                invoice_id=str(invoice.id),
                error=str(e),
                correlation_id=correlation_id,
            )

    # Fallback to Resend
    try:
        result = _send_via_resend(
            to_email=invoice.debtor.email,
            subject=subject,
            html_body=html_body,
        )
        logger.info(
            "reminder_email_sent_resend",
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
