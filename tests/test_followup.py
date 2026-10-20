"""The follow-up schedule (src/services/followup.py):

    Day -7, -1, 0, +7 email · +15, +20 text · +25 call · +26 owner handover

Every outbound sender is stubbed: the shared test DB holds invoices from
other test modules, and none of them may reach a real provider.
"""
import uuid
from contextlib import contextmanager
from datetime import date, timedelta
from unittest.mock import patch

from src.db import SessionLocal
from src.models.debtor import Debtor
from src.models.document_client import DocumentClient
from src.models.document_request import DocumentRequest
from src.models.email_template import EmailTemplate
from src.models.invoice import Invoice, InvoiceStatus
from src.models.reminder import ReminderLog
from src.models.user import User
from src.services.followup import (
    FINISHED, HOURLY_KINDS, SCHEDULE, current_step, run_document_followups, run_invoice_followups,
    _document_sms_message,
)

TODAY = date(2026, 6, 15)


class Outbox:
    def __init__(self):
        self.emails, self.doc_emails, self.sms, self.calls, self.handoffs = [], [], [], [], []


@contextmanager
def stubbed(call_window=True, sms_ok=True):
    box = Outbox()
    with patch("src.services.email.send_reminder_email", side_effect=lambda inv, stage=None: box.emails.append((inv.id, stage))), \
         patch("src.services.document_email.send_document_request_email", side_effect=lambda docs: box.doc_emails.append(sorted(d.id for d in docs))), \
         patch("src.services.ghl_service.send_sms", side_effect=lambda **kw: box.sms.append(kw) or sms_ok), \
         patch("src.services.ghl_service.trigger_voice_call", side_effect=lambda **kw: box.calls.append(kw) or True), \
         patch("src.services.account_notifications.send_followup_handoff_email", side_effect=lambda **kw: box.handoffs.append(
               {**kw, "contact_name": kw["contact"].name, "contact_email": kw["contact"].email})), \
         patch("src.services.call_window.is_within_calling_window", return_value=call_window):
        yield box


def _user(session, plan="scale", sub_status="active", limit=750, used=0):
    u = User(id=str(uuid.uuid4()), username=f"{uuid.uuid4().hex[:8]}@example.com", hashed_password="x",
             company_name="Follow Co", subscription_plan=plan, subscription_status=sub_status,
             chases_limit=limit, chases_used=used)
    session.add(u)
    session.flush()
    return u


def _invoice(session, user, due_in, phone="+15550001111", consent=True, status=InvoiceStatus.upcoming, step=0):
    d = Debtor(id=str(uuid.uuid4()), user_id=user.id, name="Northwind", email=f"{uuid.uuid4().hex[:8]}@example.com",
               phone=phone, voice_call_consent=consent, debtor_type="business")
    session.add(d)
    session.flush()
    inv = Invoice(id=str(uuid.uuid4()), user_id=user.id, debtor_id=d.id, invoice_number=f"INV-{uuid.uuid4().hex[:6]}",
                  amount=4200, due_date=TODAY + timedelta(days=due_in), status=status, followup_step=step)
    session.add(inv)
    session.flush()
    return inv


def _make(builder, *args, **kwargs):
    session = SessionLocal()
    try:
        obj = builder(session, *args, **kwargs)
        session.commit()
        return obj.id
    finally:
        session.close()


def _new_invoice(due_in, **kw):
    session = SessionLocal()
    try:
        u = _user(session, **{k: kw.pop(k) for k in list(kw) if k in ("plan", "sub_status", "limit", "used")})
        inv = _invoice(session, u, due_in, **kw)
        session.commit()
        return inv.id, u.id
    finally:
        session.close()


def _get(model, id_):
    session = SessionLocal()
    try:
        return session.get(model, id_)
    finally:
        session.close()


def _run(day_offset_from_due, due_in_at_creation, kinds=None):
    """Run the daily engine on the date that is `day_offset_from_due` days
    after an invoice created with due date TODAY+due_in_at_creation."""
    run_day = TODAY + timedelta(days=due_in_at_creation + day_offset_from_due)
    session = SessionLocal()
    try:
        if kinds is None:
            run_invoice_followups(session, today=run_day)
        else:
            run_invoice_followups(session, kinds, today=run_day)
    finally:
        session.close()


# ---------------------------------------------------------------- schedule

def test_schedule_matches_the_agreed_plan():
    assert [(s.kind, s.day) for s in SCHEDULE] == [
        ("email", -7), ("email", -1), ("email", 0), ("email", 7),
        ("sms", 15), ("sms", 20), ("voice", 25), ("handoff", 26)]
    assert [s.stage for s in SCHEDULE[:4]] == ["upcoming", "upcoming", "due", "overdue"]


def test_current_step_skips_steps_that_are_long_past():
    assert current_step(0, -7) == (0, SCHEDULE[0])
    assert current_step(0, -3)[0] == 1          # the Day -7 email has expired
    assert current_step(0, 0)[0] == 2           # Day -1 and Day 0 both due: only "due today"
    assert current_step(0, 40)[0] == 7          # everything but the handover expired
    assert current_step(6, 26)[0] == 6          # a pending call isn't dropped for the handover
    assert current_step(6, 30)[0] == 7          # ...until its grace period runs out
    assert current_step(7, 400) == (7, SCHEDULE[7])  # the handover never expires
    assert current_step(FINISHED, 0) == (FINISHED, None)


def test_full_run_sends_each_step_exactly_once_on_its_day():
    inv_id, _ = _new_invoice(due_in=10)
    with stubbed() as box:
        for day in range(-10, 30):
            _run(day, 10)
            run_day = TODAY + timedelta(days=10 + day)
            s = SessionLocal()
            try:
                run_invoice_followups(s, HOURLY_KINDS, today=run_day)
            finally:
                s.close()
    mine = [stage for i, stage in box.emails if i == inv_id]
    assert mine == ["upcoming", "upcoming", "due", "overdue"]
    assert len([c for c in box.sms if c["contact_name"] == "Northwind" and c["message"]]) >= 2
    assert len([h for h in box.handoffs if h["what"].startswith("invoice ")]) >= 1
    inv = _get(Invoice, inv_id)
    assert inv.followup_step == FINISHED
    assert inv.sms_sent_count == 2 and inv.voice_call_count == 1


def test_emails_land_on_the_right_days():
    inv_id, _ = _new_invoice(due_in=10)
    sent_on = []
    with stubbed() as box:
        for day in range(-10, 10):
            before = len([e for e in box.emails if e[0] == inv_id])
            _run(day, 10)
            if len([e for e in box.emails if e[0] == inv_id]) > before:
                sent_on.append(day)
    assert sent_on == [-7, -1, 0, 7]


def test_invoice_added_late_starts_at_the_next_step_instead_of_catching_up():
    inv_id, _ = _new_invoice(due_in=3)
    with stubbed() as box:
        _run(-3, 3)      # Day -3: the Day -7 email has expired, nothing due yet
        _run(-1, 3)      # Day -1: the next email
    assert [stage for i, stage in box.emails if i == inv_id] == ["upcoming"]
    assert _get(Invoice, inv_id).followup_step == 2


def test_one_step_per_day_even_if_run_twice():
    inv_id, _ = _new_invoice(due_in=0)
    with stubbed() as box:
        _run(0, 0)
        _run(0, 0)
    assert [stage for i, stage in box.emails if i == inv_id] == ["due"]


# ---------------------------------------------------------------- stopping

def test_paid_and_paused_invoices_get_nothing():
    paid_id, _ = _new_invoice(due_in=0, status=InvoiceStatus.paid)
    paused_id, _ = _new_invoice(due_in=0, status=InvoiceStatus.paused)
    with stubbed() as box:
        _run(0, 0)
    assert not [e for e in box.emails if e[0] in (paid_id, paused_id)]


def test_inactive_subscription_gets_nothing():
    session = SessionLocal()
    try:
        u = _user(session, sub_status="cancelled")
        inv = _invoice(session, u, 0)
        session.commit()
        inv_id = inv.id
    finally:
        session.close()
    with stubbed() as box:
        _run(0, 0)
    assert not [e for e in box.emails if e[0] == inv_id]
    assert _get(Invoice, inv_id).followup_step == 0


def test_used_up_allowance_waits_without_skipping():
    session = SessionLocal()
    try:
        u = _user(session, limit=10, used=10)
        inv = _invoice(session, u, 0)
        session.commit()
        inv_id, user_id = inv.id, u.id
    finally:
        session.close()
    with stubbed() as box:
        _run(0, 0)
    assert not [e for e in box.emails if e[0] == inv_id]
    assert _get(Invoice, inv_id).followup_step == 2  # the "due today" email is still owed

    session = SessionLocal()
    try:
        session.get(User, user_id).chases_used = 0
        session.commit()
    finally:
        session.close()
    with stubbed() as box:
        _run(1, 0)  # within the step's grace period
    assert [stage for i, stage in box.emails if i == inv_id] == ["due"]


# ---------------------------------------------------------------- texts and calls

def test_texts_and_call_are_skipped_without_consent_but_owner_still_hears():
    inv_id, _ = _new_invoice(due_in=-15, consent=False, status=InvoiceStatus.overdue, step=4)
    debtor_email = _get(Debtor, _get(Invoice, inv_id).debtor_id).email
    with stubbed() as box:
        for day in (15, 20, 25, 26):
            _run(day, -15)
            _run(day, -15, kinds=HOURLY_KINDS)
    assert not [c for c in box.sms + box.calls if c["contact_email"] == debtor_email]
    handoff = [h for h in box.handoffs if h["contact_email"] == debtor_email]
    assert len(handoff) == 1
    assert "no consent" in handoff[0]["skipped"]
    assert _get(Invoice, inv_id).followup_step == FINISHED


def test_starter_plan_skips_the_call():
    inv_id, _ = _new_invoice(due_in=-25, plan="starter", status=InvoiceStatus.overdue, step=6)
    with stubbed():
        _run(25, -25, kinds=HOURLY_KINDS)
    assert _get(Invoice, inv_id).followup_step == 7
    assert _get(Invoice, inv_id).voice_call_count == 0


def test_call_waits_for_the_calling_window_then_goes_out():
    inv_id, _ = _new_invoice(due_in=-25, status=InvoiceStatus.overdue, step=6)
    with stubbed(call_window=False):
        _run(25, -25, kinds=HOURLY_KINDS)
    assert _get(Invoice, inv_id).followup_step == 6
    with stubbed(call_window=True):
        _run(26, -25, kinds=HOURLY_KINDS)
    assert _get(Invoice, inv_id).followup_step == 7
    assert _get(Invoice, inv_id).voice_call_count == 1


def test_daily_run_never_places_calls():
    inv_id, _ = _new_invoice(due_in=-25, status=InvoiceStatus.overdue, step=6)
    with stubbed():
        _run(25, -25)
    assert _get(Invoice, inv_id).voice_call_count == 0


def test_text_uses_the_sms_template_not_the_email_template():
    session = SessionLocal()
    try:
        u = _user(session)
        inv = _invoice(session, u, -15, status=InvoiceStatus.overdue, step=4)
        session.add(EmailTemplate(user_id=u.id, template_type="overdue", subject="s", body="LONG EMAIL BODY"))
        session.add(EmailTemplate(user_id=u.id, template_type="sms_overdue", subject="", body="SMS MARKER {{invoice_number}}"))
        session.commit()
        number = inv.invoice_number
    finally:
        session.close()
    with stubbed() as box:
        _run(15, -15)
    mine = [c["message"] for c in box.sms if number in c["message"] or "LONG EMAIL" in c["message"]]
    assert mine == [f"SMS MARKER {number}"]


def test_failed_text_is_retried_next_day_and_logged():
    inv_id, _ = _new_invoice(due_in=-15, status=InvoiceStatus.overdue, step=4)
    with stubbed(sms_ok=False):
        _run(15, -15)
    assert _get(Invoice, inv_id).followup_step == 4
    with stubbed(sms_ok=True):
        _run(16, -15)
    assert _get(Invoice, inv_id).followup_step == 5
    session = SessionLocal()
    try:
        statuses = [l.status.value for l in session.query(ReminderLog).filter(ReminderLog.invoice_id == inv_id).order_by(ReminderLog.sent_at)]
    finally:
        session.close()
    assert statuses == ["failed", "sent"]


def test_one_failing_send_does_not_block_other_invoices():
    a_id, _ = _new_invoice(due_in=-15, phone="+15550000001", status=InvoiceStatus.overdue, step=4)
    b_id, _ = _new_invoice(due_in=-15, phone="+15550000002", status=InvoiceStatus.overdue, step=4)

    def flaky(**kw):
        if kw["phone"] == "+15550000001":
            raise RuntimeError("simulated outage")
        return True
    with stubbed(), patch("src.services.ghl_service.send_sms", side_effect=flaky):
        _run(15, -15)
    assert _get(Invoice, a_id).followup_step == 4
    assert _get(Invoice, b_id).followup_step == 5


def test_each_message_counts_one_reminder_and_handover_counts_none():
    inv_id, user_id = _new_invoice(due_in=-25, status=InvoiceStatus.overdue, step=6)
    with stubbed():
        _run(25, -25, kinds=HOURLY_KINDS)
        _run(26, -25)
    assert _get(User, user_id).chases_used == 1
    assert _get(Invoice, inv_id).followup_step == FINISHED


# ---------------------------------------------------------------- documents

def _client_with_docs(titles, due_in, consent=True, step=0, status="pending"):
    session = SessionLocal()
    try:
        u = _user(session)
        c = DocumentClient(id=str(uuid.uuid4()), user_id=u.id, name="Jane Docs", email=f"{uuid.uuid4().hex[:8]}@example.com",
                           phone="+15550002222", voice_call_consent=consent)
        session.add(c)
        session.flush()
        ids = []
        for t in titles:
            d = DocumentRequest(id=str(uuid.uuid4()), user_id=u.id, client_id=c.id, title=t, status=status,
                                due_date=TODAY + timedelta(days=due_in), followup_step=step)
            session.add(d)
            ids.append(d.id)
        session.commit()
        return ids, u.id
    finally:
        session.close()


def _run_docs(run_day, kinds=None):
    session = SessionLocal()
    try:
        return run_document_followups(session, kinds, today=run_day) if kinds else run_document_followups(session, today=run_day)
    finally:
        session.close()


def test_documents_for_one_client_share_one_email_per_step():
    ids, user_id = _client_with_docs(["W-9", "Lease"], due_in=7)
    with stubbed() as box:
        _run_docs(TODAY)  # Day -7
    assert sorted(ids) in box.doc_emails
    assert _get(User, user_id).chases_used == 1
    assert all(_get(DocumentRequest, i).followup_step == 1 for i in ids)


def test_document_text_and_handover_cover_all_documents():
    ids, _ = _client_with_docs(["W-9", "Lease", "ID"], due_in=-15, step=4, status="overdue")
    with stubbed() as box:
        _run_docs(TODAY)
        text = [c for c in box.sms if c["contact_name"] == "Jane Docs" and "3 documents" in c["message"]]
        assert len(text) == 1
        session = SessionLocal()
        try:
            for i in ids:
                session.get(DocumentRequest, i).followup_step = 7
            session.commit()
        finally:
            session.close()
        _run_docs(TODAY + timedelta(days=11))
    handoff = [h for h in box.handoffs if h["contact_name"] == "Jane Docs" and len(h["items"]) == 3]
    assert len(handoff) == 1
    assert handoff[0]["outstanding_word"] == "not received"


def test_submitted_documents_get_nothing():
    ids, _ = _client_with_docs(["W-9"], due_in=0, status="submitted")
    with stubbed() as box:
        _run_docs(TODAY)
    assert not [e for e in box.doc_emails if ids[0] in e]


def test_grouped_document_sms_stays_short_whatever_the_document_count():
    from types import SimpleNamespace as NS
    reqs = [NS(title=f"Very long document title number {i} for tax year 2026", upload_token=f"doc_{i:012d}") for i in range(10)]
    msg = _document_sms_message("Jane Smith", "Acme Bookkeeping LLC", reqs)
    assert "10 documents" in msg and "doc_000000000000" in msg
    assert len(msg) <= 306


# ---------------------------------------------------------------- owner handover email

def test_handover_email_lists_history_contact_and_amount():
    inv_id, user_id = _new_invoice(due_in=-26, status=InvoiceStatus.overdue, step=7)
    session = SessionLocal()
    try:
        from src.models.reminder import Channel, ReminderStatus
        from datetime import datetime, timezone
        session.add(ReminderLog(invoice_id=inv_id, sent_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
                                channel=Channel.email, payload={}, status=ReminderStatus.sent))
        session.add(ReminderLog(invoice_id=inv_id, sent_at=datetime(2026, 5, 16, tzinfo=timezone.utc),
                                channel=Channel.sms, payload={}, status=ReminderStatus.failed))
        session.commit()
    finally:
        session.close()
    with patch("src.services.account_notifications._send_via_resend") as mock_send, stubbed_no_handoff():
        _run(26, -26)
    mine = [c for c in mock_send.call_args_list if "Northwind" in c.kwargs["subject"] and _get(User, user_id).username == c.kwargs["to_email"]]
    assert len(mine) == 1
    html = mine[0].kwargs["html_body"]
    assert "Still unpaid after every reminder" in mine[0].kwargs["subject"]
    assert "$4200.00" in html and "+15550001111" in html and "Text message" in html and "Failed" in html
    assert _get(Invoice, inv_id).followup_step == FINISHED


@contextmanager
def stubbed_no_handoff():
    with patch("src.services.email.send_reminder_email"), \
         patch("src.services.document_email.send_document_request_email"), \
         patch("src.services.ghl_service.send_sms", return_value=True), \
         patch("src.services.ghl_service.trigger_voice_call", return_value=True):
        yield
