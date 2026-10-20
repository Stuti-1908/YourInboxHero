"""The follow-up schedule: what goes out, and when, for an unpaid invoice or
an outstanding document request.

Day 0 is the due date.

    Day -7   email  "coming up"
    Day -1   email  "due tomorrow" (upcoming wording)
    Day  0   email  "due today"
    Day +7   email  "overdue"
    Day +15  text
    Day +20  text
    Day +25  AI voice call
    Day +26  email to the account owner: everything we tried, who we
             contacted, what's still outstanding. Automatic contact stops.

Each item remembers how far it has got (followup_step). One step goes out
per run. A step whose day has long passed is skipped rather than sent late,
so an invoice added 3 days before its due date starts at the Day -1 email
instead of getting three emails at once. A step that can't apply (no phone
number, no consent, plan without calls) is skipped too. The owner handover
never expires, so every item that runs out of steps unpaid ends with it.

Nothing is sent for paid, paused or manual invoices, approved or submitted
documents, inactive subscriptions, or once the monthly allowance is used up.
While paused like that, a step waits out its grace period; if the pause
lasts longer, that step is dropped and the schedule resumes at the next one
(a "due tomorrow" email a week late would only confuse the client). The
owner handover never expires and is free: it isn't a message to a client.

Each step is claimed in the database (followup_step moved forward only if
it still holds the value we read) before anything is sent, so overlapping
runs can never send the same step twice, and a crash after sending can't
cause a resend. A step that didn't go out is released for a later run.
"""
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Iterable, List, Optional

import structlog
from sqlalchemy.orm import Session

from src.config.settings import get_settings
from src.models.document_request import DocumentRequest
from src.models.email_template import EmailTemplate
from src.models.invoice import Invoice, InvoiceStatus
from src.models.reminder import Channel, ReminderLog, ReminderStatus
from src.services.plan_features import plan_has_feature
from src.services.usage_limits import can_send_chase, record_chase_used

logger = structlog.get_logger(__name__)
settings = get_settings()


@dataclass(frozen=True)
class Step:
    kind: str                    # "email" | "sms" | "voice" | "handoff"
    day: int                     # days after the due date (negative = before)
    stage: Optional[str] = None  # email wording: upcoming / due / overdue
    grace: Optional[int] = 2     # days a missed step may still go out; None = never expires


SCHEDULE = (
    Step("email", -7, "upcoming"),
    Step("email", -1, "upcoming"),
    Step("email", 0, "due"),
    Step("email", 7, "overdue"),
    Step("sms", 15),
    Step("sms", 20),
    # Calls wait for the customer's calling window, so they get longer to land.
    Step("voice", 25, grace=4),
    Step("handoff", 26, grace=None),
)
FINISHED = len(SCHEDULE)
DAILY_KINDS = frozenset({"email", "sms", "handoff"})
HOURLY_KINDS = frozenset({"voice"})

OPEN_INVOICE_STATUSES = (InvoiceStatus.upcoming, InvoiceStatus.due, InvoiceStatus.overdue)
OPEN_DOCUMENT_STATUSES = ("pending", "overdue")


def _join_titles(titles):
    quoted = [f'"{t}"' for t in titles]
    if len(quoted) <= 2:
        return " and ".join(quoted)
    return ", ".join(quoted[:-1]) + f" and {quoted[-1]}"


def _document_sms_message(client_name, company_name, reqs):
    if len(reqs) == 1:
        req = reqs[0]
        return (
            f"Hi {client_name}, the document \"{req.title}\" requested by {company_name} is OVERDUE. "
            f"Please upload it here: {settings.frontend_url}/upload/{req.upload_token}"
        )
    # Several links would make one text cost several SMS segments; the
    # client already has every upload link in their email, so point there
    # and include the most overdue one for a one-tap start.
    return (
        f"Hi {client_name}, {len(reqs)} documents requested by {company_name} are OVERDUE. "
        f"All upload links are in our email. First: {settings.frontend_url}/upload/{reqs[0].upload_token}"
    )



def current_step(step_index: int, offset: int):
    """Return (index, step) for the step owed now, or (index, None) once the
    schedule is finished. Skips steps whose grace period has run out, and
    when several email/text steps are all due, keeps only the latest, so a
    late start never sends two messages for the same day. A pending call is
    never dropped in favour of the owner handover while it can still land."""
    idx = step_index or 0
    while idx < FINISHED:
        s = SCHEDULE[idx]
        if s.grace is not None and offset > s.day + s.grace:
            idx += 1
            continue
        nxt = SCHEDULE[idx + 1] if idx + 1 < FINISHED else None
        if nxt is not None and nxt.day <= offset and s.kind in ("email", "sms"):
            idx += 1
            continue
        return idx, s
    return idx, None


def _now():
    return datetime.now(timezone.utc)


def _log(db: Session, channel: Channel, ok: bool, payload: dict, invoice_id=None, document_request_id=None):
    db.add(ReminderLog(
        invoice_id=invoice_id, document_request_id=document_request_id,
        sent_at=_now(), channel=channel, payload=payload,
        status=ReminderStatus.sent if ok else ReminderStatus.failed,
    ))


# Set the instant a message is handed to a provider. If a step raises after
# this, the message may be out, so its claim is kept (never a resend); if it
# raises before, nothing went out and the claim is released for a retry.
_message_left = ContextVar("followup_message_left", default=False)


def _provider_call(fn, **kwargs) -> bool:
    """Texts, calls and the owner handover: a provider error counts as a
    failed attempt (logged and retried later). Senders that return nothing
    on success (the handover email) count as delivered."""
    try:
        _message_left.set(True)
        result = fn(**kwargs)
        return True if result is None else bool(result)
    except Exception as exc:
        logger.error("followup_provider_call_failed", provider=getattr(fn, "__name__", "?"), error=str(exc))
        return False


def _contact_ok_for_phone(contact) -> Optional[str]:
    """None if texts/calls are allowed, otherwise the reason they're not."""
    if not contact.phone:
        return "no phone number on file"
    if not contact.voice_call_consent:
        return "no consent to texts and calls"
    return None


# --------------------------------------------------------------------------
# Invoices
# --------------------------------------------------------------------------

def _invoice_sms_text(db: Session, inv: Invoice) -> str:
    debtor, user = inv.debtor, inv.debtor.user
    company = user.company_name or "YourInboxHero"
    body = None
    if plan_has_feature(user.subscription_plan, "custom_templates"):
        tmpl = db.query(EmailTemplate).filter(
            EmailTemplate.user_id == user.id, EmailTemplate.template_type == "sms_overdue").first()
        body = tmpl.body if tmpl else None
    if body is None:
        body = (f"Hi {debtor.name}, Invoice #{inv.invoice_number} for ${inv.amount:.2f} is OVERDUE. "
                f"Please pay now: {inv.payment_link or 'contact us'} - {company}")
    for key, val in {
        "{{debtor_name}}": debtor.name, "{{amount_due}}": f"${inv.amount:.2f}",
        "{{invoice_number}}": inv.invoice_number, "{{due_date}}": str(inv.due_date),
        "{{company_name}}": company, "{{payment_link}}": inv.payment_link or "",
    }.items():
        body = body.replace(key, val)
    return body


def _send_invoice_step(db: Session, inv: Invoice, idx: int, step: Step) -> bool:
    """Attempt one step. True means the step is finished (sent or skipped)
    and the invoice moves on; False means try again on a later run."""
    debtor, user = inv.debtor, inv.debtor.user
    payload = {"invoice_number": inv.invoice_number, "step": idx + 1}

    if step.kind == "handoff":
        from src.services.account_notifications import send_followup_handoff_email
        return _provider_call(
            send_followup_handoff_email,
            user=user,
            what=f"invoice {inv.invoice_number}",
            outstanding_word="unpaid",
            items=[{"label": f"Invoice {inv.invoice_number}", "detail": f"${inv.amount:.2f}, due {inv.due_date}"}],
            contact=debtor,
            history=_history(db, invoice_ids=[inv.id]),
            skipped=_skipped_reasons(debtor, user),
            dashboard_path="/dashboard/invoices",
        )

    if step.kind in ("sms", "voice"):
        reason = _contact_ok_for_phone(debtor)
        if step.kind == "voice" and not reason and not plan_has_feature(user.subscription_plan, "voice_escalation"):
            reason = "calls aren't included in this plan"
        if reason:
            logger.info("followup_step_skipped", invoice_id=inv.id, step=idx + 1, kind=step.kind, reason=reason)
            return True

    if not can_send_chase(user):
        return False  # wait for allowance / an active subscription

    if step.kind == "voice":
        from src.services.call_window import is_within_calling_window
        if not is_within_calling_window(user):
            return False

    if step.kind == "email":
        from src.services.email import send_reminder_email
        try:
            _message_left.set(True)
            send_reminder_email(inv, stage=step.stage)
            ok = True
        except Exception as exc:
            logger.error("followup_email_failed", invoice_id=inv.id, error=str(exc))
            ok = False
        _log(db, Channel.email, ok, {**payload, "debtor_email": debtor.email}, invoice_id=inv.id)
    elif step.kind == "sms":
        from src.services.ghl_service import send_sms
        ok = _provider_call(send_sms, phone=debtor.phone, message=_invoice_sms_text(db, inv),
                            contact_name=debtor.name, contact_email=debtor.email)
        _log(db, Channel.sms, ok, {**payload, "debtor_phone": debtor.phone}, invoice_id=inv.id)
        if ok:
            inv.sms_sent_count = (inv.sms_sent_count or 0) + 1
    else:
        from src.services.ghl_service import trigger_voice_call
        company = user.company_name or "YourInboxHero"
        ok = _provider_call(
            trigger_voice_call,
            phone=debtor.phone,
            message=(f"This is an automated call from {company}. Invoice number {inv.invoice_number} "
                     f"for ${inv.amount:.2f} is overdue. Please make your payment as soon as possible."),
            contact_name=debtor.name, contact_email=debtor.email, company_name=company,
            reason="invoice", item_description=inv.invoice_number,
            amount=f"{inv.amount:.2f}", due_date=inv.due_date.isoformat(),
        )
        _log(db, Channel.voice, ok, {**payload, "debtor_phone": debtor.phone}, invoice_id=inv.id)
        if ok:
            inv.voice_call_count = (inv.voice_call_count or 0) + 1

    if ok:
        inv.last_reminder_sent = _now()
        inv.escalation_tier = step.kind
        record_chase_used(user, db, channel=step.kind, invoice_id=str(inv.id))
    return ok


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def _claim(db: Session, model, ids_and_steps, new_step: int) -> list:
    """Move items to new_step only if nobody else moved them first. This is
    what stops the daily and hourly runs (or two overlapping runs) from
    both sending the same step: the step is claimed in the database before
    anything goes out. Returns the ids that were claimed."""
    claimed = []
    for item_id, old_step in ids_and_steps:
        n = db.query(model).filter(model.id == item_id, model.followup_step == old_step).update(
            {model.followup_step: new_step}, synchronize_session=False)
        if n:
            claimed.append(item_id)
    db.commit()
    return claimed


def _release(db: Session, model, ids, claimed_step: int, back_to: int) -> None:
    """Undo a claim when the step didn't go out (send failed, or it has to
    wait for the calling window or allowance), so a later run retries it."""
    db.query(model).filter(model.id.in_(ids), model.followup_step == claimed_step).update(
        {model.followup_step: back_to}, synchronize_session=False)
    db.commit()


def run_invoice_followups(db: Session, kinds: Iterable[str] = DAILY_KINDS, today: Optional[date] = None) -> int:
    """Run whatever step each open invoice is owed today (UTC). Returns the
    number of steps sent or skipped."""
    kinds = frozenset(kinds)
    persist_skips = "email" in kinds  # only the daily run records skipped steps
    today = today or _utc_today()
    done = 0
    invoices = db.query(Invoice).filter(
        Invoice.status.in_(OPEN_INVOICE_STATUSES),
        Invoice.followup_step < FINISHED,
    ).all()
    for inv in invoices:
        inv_id, stored = inv.id, inv.followup_step
        try:
            if inv.debtor.user.subscription_status != "active":
                continue
            offset = (today - inv.due_date).days
            idx, step = current_step(stored, offset)
            due_now = step is not None and step.day <= offset and step.kind in kinds
            if not due_now:
                if persist_skips and idx != stored:
                    _claim(db, Invoice, [(inv_id, stored)], idx)
                continue
            if not _claim(db, Invoice, [(inv_id, stored)], idx + 1):
                continue  # another run got here first
            _message_left.set(False)
            try:
                sent = _send_invoice_step(db, inv, idx, step)
                db.commit()
            except Exception:
                db.rollback()
                if not _message_left.get():
                    _release(db, Invoice, [inv_id], idx + 1, idx)
                raise
            if sent:
                done += 1
            else:
                _release(db, Invoice, [inv_id], idx + 1, idx)
        except Exception as exc:
            db.rollback()
            logger.error("invoice_followup_failed", invoice_id=inv_id, error=str(exc), exc_info=True)
    return done


# --------------------------------------------------------------------------
# Document requests: one message per client covers every document that is
# at the same step, matching the grouped request email.
# --------------------------------------------------------------------------

def _send_document_group(db: Session, docs: List[DocumentRequest], idx: int, step: Step) -> bool:
    client, user = docs[0].client, docs[0].client.user
    titles = [d.title for d in docs]
    payload_base = {"step": idx + 1}

    if step.kind == "handoff":
        from src.services.account_notifications import send_followup_handoff_email
        return _provider_call(
            send_followup_handoff_email,
            user=user,
            what=(f'"{titles[0]}"' if len(docs) == 1 else f"{len(docs)} documents from {client.name}"),
            outstanding_word="not received",
            items=[{"label": d.title, "detail": f"due {d.due_date}"} for d in docs],
            contact=client,
            history=_history(db, document_ids=[d.id for d in docs]),
            skipped=_skipped_reasons(client, user),
            dashboard_path="/documents",
        )

    if step.kind in ("sms", "voice"):
        reason = _contact_ok_for_phone(client)
        if step.kind == "voice" and not reason and not plan_has_feature(user.subscription_plan, "voice_escalation"):
            reason = "calls aren't included in this plan"
        if reason:
            logger.info("followup_step_skipped", client_id=client.id, step=idx + 1, kind=step.kind, reason=reason)
            return True

    if not can_send_chase(user):
        return False

    if step.kind == "voice":
        from src.services.call_window import is_within_calling_window
        if not is_within_calling_window(user):
            return False

    if step.kind == "email":
        from src.services.document_email import send_document_request_email
        try:
            _message_left.set(True)
            send_document_request_email(docs)
            ok = True
        except Exception as exc:
            logger.error("followup_document_email_failed", client_id=client.id, error=str(exc))
            ok = False
        channel = Channel.email
    elif step.kind == "sms":
        from src.services.ghl_service import send_sms
        company = user.company_name or "YourInboxHero"
        ok = _provider_call(send_sms, phone=client.phone, message=_document_sms_message(client.name, company, docs),
                            contact_name=client.name, contact_email=client.email)
        channel = Channel.sms
    else:
        from src.services.ghl_service import trigger_voice_call
        company = user.company_name or "YourInboxHero"
        joined = _join_titles(titles)
        single = len(docs) == 1
        ok = _provider_call(
            trigger_voice_call,
            phone=client.phone,
            message=(f"This is an automated call from {company}. The {'document' if single else 'documents'} {joined} "
                     f"we requested {'is' if single else 'are'} overdue. Please upload {'it' if single else 'them'} as soon as possible."),
            contact_name=client.name, contact_email=client.email, company_name=company,
            reason="document", item_description=joined.replace('"', ''),
            amount="", due_date=docs[0].due_date.isoformat(),
        )
        channel = Channel.voice

    now = _now()
    for d in docs:
        _log(db, channel, ok, {**payload_base, "title": d.title}, document_request_id=d.id)
        if ok:
            d.last_reminder_sent = now
            d.escalation_tier = step.kind
            if step.kind == "sms":
                d.sms_sent_count = (d.sms_sent_count or 0) + 1
            elif step.kind == "voice":
                d.voice_call_count = (d.voice_call_count or 0) + 1
    if ok:
        record_chase_used(user, db, channel=step.kind, invoice_id=docs[0].id)
    return ok


def run_document_followups(db: Session, kinds: Iterable[str] = DAILY_KINDS, today: Optional[date] = None) -> int:
    kinds = frozenset(kinds)
    persist_skips = "email" in kinds
    today = today or _utc_today()
    groups = {}
    docs = db.query(DocumentRequest).filter(
        DocumentRequest.status.in_(OPEN_DOCUMENT_STATUSES),
        DocumentRequest.followup_step < FINISHED,
    ).order_by(DocumentRequest.due_date, DocumentRequest.title).all()
    skips = {}
    for d in docs:
        if d.client.user.subscription_status != "active":
            continue
        offset = (today - d.due_date).days
        idx, step = current_step(d.followup_step, offset)
        if step is not None and step.day <= offset and step.kind in kinds:
            groups.setdefault((d.client_id, idx), []).append((d, d.followup_step))
        elif persist_skips and idx != d.followup_step:
            skips.setdefault(idx, []).append((d.id, d.followup_step))
    for idx, pairs in skips.items():
        _claim(db, DocumentRequest, pairs, idx)

    done = 0
    for (client_id, idx), members in groups.items():
        try:
            claimed = set(_claim(db, DocumentRequest, [(d.id, old) for d, old in members], idx + 1))
            group = [d for d, _ in members if d.id in claimed]
            if not group:
                continue
            for d in group:
                db.refresh(d)
            _message_left.set(False)
            try:
                sent = _send_document_group(db, group, idx, SCHEDULE[idx])
                db.commit()
            except Exception:
                db.rollback()
                if not _message_left.get():
                    _release(db, DocumentRequest, list(claimed), idx + 1, idx)
                raise
            if sent:
                done += 1
            else:
                _release(db, DocumentRequest, list(claimed), idx + 1, idx)
        except Exception as exc:
            db.rollback()
            logger.error("document_followup_failed", client_id=client_id, error=str(exc), exc_info=True)
    return done


# --------------------------------------------------------------------------
# Owner handover helpers
# --------------------------------------------------------------------------

_CHANNEL_LABEL = {"email": "Email", "sms": "Text message", "voice": "Phone call"}


def _history(db: Session, invoice_ids=None, document_ids=None) -> List[dict]:
    q = db.query(ReminderLog)
    q = q.filter(ReminderLog.invoice_id.in_(invoice_ids)) if invoice_ids else q.filter(ReminderLog.document_request_id.in_(document_ids))
    seen, rows = set(), []
    for log in q.order_by(ReminderLog.sent_at).all():
        channel = log.channel.value if hasattr(log.channel, "value") else str(log.channel)
        ok = (log.status.value if hasattr(log.status, "value") else str(log.status)) == "sent"
        day = log.sent_at.date().isoformat() if log.sent_at else ""
        key = (day, channel, ok)  # a grouped document send logs once per document
        if key in seen:
            continue
        seen.add(key)
        rows.append({"date": day, "channel": _CHANNEL_LABEL.get(channel, channel), "ok": ok})
    return rows


def _skipped_reasons(contact, user) -> Optional[str]:
    reason = _contact_ok_for_phone(contact)
    if reason:
        return f"texts and the call ({reason})"
    if not plan_has_feature(user.subscription_plan, "voice_escalation"):
        return "the call (calls aren't included in this plan)"
    return None
