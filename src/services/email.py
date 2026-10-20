"""Email service with retry logic and structured logging."""
import base64
import html
import smtplib
from email.message import EmailMessage
from typing import Any, Dict, Optional

import requests
import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.config.settings import get_settings
from src.db import SessionLocal
from src.models.email_template import EmailTemplate
from src.services.plan_features import plan_has_feature
from src.services.secrets import decrypt_secret

logger = structlog.get_logger(__name__)
settings = get_settings()

RESEND_API_URL = "https://api.resend.com/emails"


# Per-status wording and color for the template's banner/intro line.
# 'manual'/'paused' are intentionally absent -- send_reminder_email is
# only ever called for upcoming/due/overdue invoices (the legal guardrail
# against automated contact on paused or already-paid invoices lives at
# the call sites: reminder_worker.py, reminder_manual.py, scheduler.py).
_STATUS_COPY = {
    "upcoming": {
        "banner_text": "Upcoming Invoice",
        "banner_color": "#2563eb",
        "intro_line": "This is a friendly reminder that the invoice below will be due soon.",
    },
    "due": {
        "banner_text": "Invoice Due Today",
        "banner_color": "#d97706",
        "intro_line": "This is a reminder that the invoice below is due today.",
    },
    "overdue": {
        "banner_text": "Payment Overdue",
        "banner_color": "#dc2626",
        "intro_line": "The invoice below is now past its due date. Please arrange payment at your earliest convenience.",
    },
}
_DEFAULT_STATUS_COPY = _STATUS_COPY["upcoming"]
_DEFAULT_SUBJECTS = {
    "upcoming": "Reminder: Invoice {number} from {company} is due on {due}",
    "due": "Invoice {number} from {company} is due today",
    "overdue": "Invoice {number} from {company} is overdue",
}


def render_template(invoice: Any, pdf_attached: bool = False, stage: Optional[str] = None) -> str:
    """Render the default (non-custom-template) reminder email.

    Pulls plain, pre-formatted values out of the invoice/debtor/user ORM
    objects before handing them to Jinja -- the template itself stays
    free of model internals (e.g. invoice.debtor.user.company_name),
    which also makes it straightforward to unit-test with plain fixtures
    rather than full ORM instances.
    """
    env = Environment(loader=FileSystemLoader('templates'), autoescape=select_autoescape(['html']))
    tmpl = env.get_template('reminder_email.html')

    status_value = stage or (invoice.status.value if hasattr(invoice.status, 'value') else str(invoice.status))
    copy = _STATUS_COPY.get(status_value, _DEFAULT_STATUS_COPY)
    company_name = invoice.debtor.user.company_name or 'YourInboxHero'

    return tmpl.render(
        company_name=company_name,
        debtor_name=invoice.debtor.name,
        invoice_number=invoice.invoice_number,
        description=invoice.description or None,
        due_date=str(invoice.due_date),
        amount_due=f"${invoice.amount:.2f}",
        payment_link=invoice.payment_link or None,
        payment_instructions=invoice.payment_instructions or None,
        pdf_attached=pdf_attached,
        banner_text=copy["banner_text"],
        banner_color=copy["banner_color"],
        intro_line=copy["intro_line"],
    )


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


# Customers pick one of these providers in the UI. Enforced on save AND at
# connect time, so a host saved before the allowlist existed (or written
# directly to the DB) can't be used to make the server connect elsewhere.
ALLOWED_SMTP_HOSTS = {"smtp.gmail.com", "smtp.mail.yahoo.com"}
ALLOWED_SMTP_PORTS = {587, 465}


def _open_smtp(host: str, port: int, timeout: int = 30) -> smtplib.SMTP:
    """Port 465 is implicit TLS (SMTP_SSL); 587 is a plain connection
    upgraded with STARTTLS."""
    if host not in ALLOWED_SMTP_HOSTS or port not in ALLOWED_SMTP_PORTS:
        raise ValueError(f"Unsupported email provider {host}:{port}.")
    if port == 465:
        return smtplib.SMTP_SSL(host, port, timeout=timeout)
    server = smtplib.SMTP(host, port, timeout=timeout)
    try:
        server.starttls()
    except Exception:
        server.close()
        raise
    return server


def _close_smtp(server: smtplib.SMTP) -> None:
    # A provider that rejects the login often drops the connection; quit()
    # on it raises SMTPServerDisconnected, which used to replace the real
    # error ("authentication failed") with "please run connect() first".
    try:
        server.quit()
    except Exception:
        pass


def verify_smtp_credentials(host: str, port: int, username: str, password: str) -> None:
    """Sign in to the customer's SMTP server without sending anything.
    Raises ValueError with a customer-readable reason on failure."""
    try:
        server = _open_smtp(host, port, timeout=15)
    except ValueError:
        raise
    except (OSError, smtplib.SMTPException) as e:
        raise ValueError(f"Could not connect to {host}:{port} ({e}).")
    try:
        server.login(username, password)
    except smtplib.SMTPAuthenticationError as e:
        detail = e.smtp_error.decode(errors="replace") if isinstance(e.smtp_error, bytes) else str(e.smtp_error)
        raise ValueError(
            f"{host} rejected the email/password ({e.smtp_code}). "
            f"Use an app password, not your normal login password. Provider said: {detail.strip()}"
        )
    except smtplib.SMTPServerDisconnected:
        # Gmail often just hangs up on a bad login instead of replying 535.
        raise ValueError(
            f"{host} rejected the email/password. "
            f"Use an app password, not your normal login password."
        )
    except smtplib.SMTPException as e:
        raise ValueError(f"{host} refused the sign-in: {e}")
    finally:
        _close_smtp(server)


@retry(
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(3),
    # Only transient network failures are retried. Retrying a rejected
    # login just repeats the failure and can get the account locked.
    retry=retry_if_exception_type((smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, ConnectionError, TimeoutError)),
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
    pdf_attachment: Optional[Dict[str, bytes]] = None,
) -> Dict[str, str]:
    """Send email via custom SMTP with retry logic.

    pdf_attachment, if given, is {"filename": str, "content": bytes}.
    """
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = from_email
    msg['To'] = to_email
    msg.set_content("Please enable HTML to view this email.")
    msg.add_alternative(html_body, subtype='html')

    if pdf_attachment:
        msg.add_attachment(
            pdf_attachment["content"],
            maintype="application",
            subtype="pdf",
            filename=pdf_attachment["filename"],
        )

    server = _open_smtp(host, port)
    try:
        server.login(username, password)
        server.send_message(msg)
        return {"status": "success", "method": "smtp"}
    finally:
        _close_smtp(server)


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
    pdf_attachment: Optional[Dict[str, bytes]] = None,
) -> Dict[str, Any]:
    """Send email via Resend with retry logic.

    pdf_attachment, if given, is {"filename": str, "content": bytes}.
    Resend expects attachment content as base64 text, not raw bytes.
    """
    if not settings.resend_api_key:
        raise RuntimeError("RESEND_API_KEY not configured")

    payload = {
        "from": settings.resend_from_email,
        "to": [to_email],
        "subject": subject,
        "html": html_body,
    }
    if pdf_attachment:
        payload["attachments"] = [{
            "filename": pdf_attachment["filename"],
            "content": base64.b64encode(pdf_attachment["content"]).decode("ascii"),
        }]

    response = requests.post(
        RESEND_API_URL,
        headers={
            "Authorization": f"Bearer {settings.resend_api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=15,
    )
    if response.status_code >= 400:
        raise Exception(f"Resend error {response.status_code}: {response.text}")
    return {"status": "success", "method": "resend", "status_code": response.status_code, "id": response.json().get("id")}


def send_reminder_email(invoice: Any, stage: Optional[str] = None) -> Dict[str, Any]:
    """
    Send reminder email for an invoice.

    Tries custom SMTP first, falls back to Resend.
    Uses retry logic for transient failures.

    stage ("upcoming" / "due" / "overdue") picks the wording and the
    customer's template; it defaults to the invoice's status. The follow-up
    schedule passes it explicitly, since an invoice is still "upcoming" on
    its due date until the overdue transition runs the next day.
    """
    stage = stage or (invoice.status.value if hasattr(invoice.status, 'value') else str(invoice.status))
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
                EmailTemplate.template_type == stage
            ).first()
        finally:
            db.close()

    replacements = _build_replacements(invoice, company_name)

    # Attach a PDF copy of the invoice. Best-effort: a PDF generation
    # failure (e.g. a malformed saved logo -- generate_invoice_pdf already
    # catches that specific case, but this guards against anything else)
    # must not block the reminder email itself from sending; the email's
    # own invoice details still cover the essentials without it.
    pdf_attachment = None
    try:
        from src.services.pdf_service import generate_invoice_pdf
        pdf_buffer = generate_invoice_pdf(invoice, invoice.debtor, user)
        pdf_attachment = {
            "filename": f"invoice_{invoice.invoice_number}.pdf",
            "content": pdf_buffer.getvalue(),
        }
    except Exception as e:
        logger.warning(
            "reminder_email_pdf_attachment_failed",
            invoice_id=str(invoice.id),
            error=str(e),
            correlation_id=correlation_id,
        )

    if custom_template:
        subject = _apply_replacements(custom_template.subject, replacements)
        body = _apply_replacements(custom_template.body, replacements)
        # Template bodies are plain text from a textarea and the
        # substituted values (debtor name, invoice number...) are
        # user-supplied, so escape before turning newlines into <br>.
        html_body = html.escape(body).replace('\n', '<br>')
    else:
        subject = _DEFAULT_SUBJECTS.get(stage, _DEFAULT_SUBJECTS["upcoming"]).format(
            number=invoice.invoice_number, company=company_name, due=invoice.due_date)
        html_body = render_template(invoice, pdf_attached=bool(pdf_attachment), stage=stage)

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
                pdf_attachment=pdf_attachment,
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
            pdf_attachment=pdf_attachment,
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
