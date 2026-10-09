"""Document request emails — the Document Collection module's equivalent
of src/services/email.py's invoice reminders.

Same custom-SMTP-first-then-Resend-fallback pattern, same per-status
banner wording, same plan-gated custom-SMTP check -- document requests
share the user's email setup and subscription plan with invoices, so
this intentionally reuses email.py's low-level senders rather than
duplicating them.
"""
from typing import Any, Dict

import structlog
from jinja2 import Environment, FileSystemLoader

from src.config.settings import get_settings
from src.services.email import _send_via_resend, _send_via_smtp
from src.services.plan_features import plan_has_feature
from src.services.secrets import decrypt_secret

logger = structlog.get_logger(__name__)
settings = get_settings()

_jinja_env = Environment(loader=FileSystemLoader('templates'))

# Mirrors email.py's _STATUS_COPY, but document_request.status uses plain
# strings ("pending"/"overdue"/"submitted"/"approved"), not an enum --
# only pending/overdue are ever passed here (submitted/approved documents
# never get automated reminders, same legal-guardrail reasoning as paid
# invoices never getting one).
_STATUS_COPY = {
    "pending": {
        "banner_text": "Document Requested",
        "banner_color": "#2563eb",
        "intro_line": "We're following up on a document we requested from you. Please upload it using the button below.",
    },
    "overdue": {
        "banner_text": "Document Overdue",
        "banner_color": "#dc2626",
        "intro_line": "The document below is now past its due date. Please upload it as soon as possible.",
    },
}
_DEFAULT_STATUS_COPY = _STATUS_COPY["pending"]


def render_document_request_email(doc_request: Any) -> str:
    """Render the document-request notification/reminder email.

    Pulls plain values out of the doc_request/client/user ORM chain
    before handing them to Jinja, mirroring email.py's render_template.
    """
    tmpl = _jinja_env.get_template('document_request_email.html')

    copy = _STATUS_COPY.get(doc_request.status, _DEFAULT_STATUS_COPY)
    company_name = doc_request.user.company_name or 'YourInboxHero'
    upload_url = f"{settings.frontend_url}/upload/{doc_request.upload_token}"

    return tmpl.render(
        company_name=company_name,
        client_name=doc_request.client.name,
        title=doc_request.title,
        description=doc_request.description or None,
        due_date=str(doc_request.due_date),
        upload_url=upload_url,
        banner_text=copy["banner_text"],
        banner_color=copy["banner_color"],
        intro_line=copy["intro_line"],
    )


def send_document_request_email(doc_request: Any) -> Dict[str, Any]:
    """Send the document-request email (initial notification or a
    reminder) via the owning user's configured provider.

    Mirrors send_reminder_email's custom-SMTP-first-then-Resend-fallback
    logic exactly, including the Growth+ custom_smtp re-check at send
    time (a downgraded Starter user may still have SMTP credentials
    saved -- see email.py's identical comment for the full rationale).
    """
    user = doc_request.client.user
    correlation_id = getattr(doc_request, 'correlation_id', 'unknown')

    logger.info(
        "preparing_document_request_email",
        doc_request_id=str(doc_request.id),
        client_email=doc_request.client.email,
        correlation_id=correlation_id,
    )

    has_custom_smtp = plan_has_feature(user.subscription_plan, "custom_smtp")
    subject_prefix = "Reminder: " if doc_request.status == "overdue" else ""
    subject = f'{subject_prefix}Document requested: {doc_request.title}'
    html_body = render_document_request_email(doc_request)

    smtp_password = decrypt_secret(user.smtp_password) if has_custom_smtp else None
    if has_custom_smtp and user.smtp_host and user.smtp_port and user.smtp_username and smtp_password:
        try:
            result = _send_via_smtp(
                host=user.smtp_host,
                port=int(user.smtp_port),
                username=user.smtp_username,
                password=smtp_password,
                from_email=user.smtp_from_email or user.smtp_username,
                to_email=doc_request.client.email,
                subject=subject,
                html_body=html_body,
            )
            logger.info(
                "document_request_email_sent_smtp",
                doc_request_id=str(doc_request.id),
                client_email=doc_request.client.email,
                correlation_id=correlation_id,
            )
            return result
        except Exception as e:
            logger.warning(
                "document_request_smtp_send_failed_falling_back_to_resend",
                doc_request_id=str(doc_request.id),
                error=str(e),
                correlation_id=correlation_id,
            )

    try:
        result = _send_via_resend(
            to_email=doc_request.client.email,
            subject=subject,
            html_body=html_body,
        )
        logger.info(
            "document_request_email_sent_resend",
            doc_request_id=str(doc_request.id),
            client_email=doc_request.client.email,
            correlation_id=correlation_id,
        )
        return result
    except Exception as e:
        logger.error(
            "document_request_email_failed_all_methods",
            doc_request_id=str(doc_request.id),
            client_email=doc_request.client.email,
            error=str(e),
            correlation_id=correlation_id,
        )
        raise
