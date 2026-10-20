"""Daily sweep scheduler.

Previously used a Postgres advisory lock to guard against overlapping runs
across multiple instances. There is currently only one Hetzner instance
(Dockerfile runs uvicorn with --workers 1), so the lock added real risk —
see run_daily_sweep's history: db.commit() calls inside the locked steps
can return the connection to the pool, meaning the unlock could execute on
a *different* pooled connection than the one that acquired the lock,
leaving it held indefinitely and silently skipping every future sweep
(daily_sweep_lock_not_acquired). Removed rather than fixed properly, since
there's no multi-instance deployment to protect yet; re-add it (correctly,
on a connection not shared with any commit) if/when this scales beyond one
instance.
"""
import structlog
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from src.db import SessionLocal
from src.models.user import User  # noqa: F401
from src.models.debtor import Debtor  # noqa: F401
from src.models.invoice import Invoice, InvoiceStatus  # noqa: F401
from src.models.reminder import ReminderLog, Channel, ReminderStatus
from src.models.email_template import EmailTemplate  # noqa: F401
from src.models.document_request import DocumentRequest  # noqa: F401
from src.models.document_client import DocumentClient  # noqa: F401
from src.services.overdue_service import transition_overdue
from src.services.reminder_service import process_due_reminders
from src.services.document_overdue_service import transition_overdue as transition_overdue_documents
from src.services.document_reminder_service import process_due_document_reminders
from src.config.settings import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()

scheduler = BackgroundScheduler()


def _as_aware_utc(dt):
    """Treat a naive datetime as UTC rather than crashing on comparison.

    The DB columns are declared TIMESTAMP(timezone=True), but not every
    driver (notably SQLite, used in tests/local dev) actually returns an
    aware datetime back on read even when one was stored — and a bare
    TIMESTAMP column from before the e1a2b3c4d5f6 migration would also come
    back naive on an unmigrated database. Every datetime written into these
    columns by this app is already UTC (see datetime.now(timezone.utc)
    throughout), so attaching the UTC tzinfo to a naive value is always
    correct, never a guess.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# Escalation timing (days) - from settings
EMAIL_TO_SMS_DAYS = settings.email_to_sms_days
SMS_TO_VOICE_DAYS = settings.sms_to_voice_days


def _log_reminder(db: Session, channel: Channel, success: bool, payload: dict, invoice_id=None, document_request_id=None):
    """Record an SMS/voice send attempt for the History page's audit trail.
    Exactly one of invoice_id/document_request_id must be set (see
    ReminderLog's check constraint). Pre-due invoice emails already log via
    reminder_worker.handle_invoice_reminder -- this covers the sends that
    previously had none: invoice SMS/voice, and all document-request sends."""
    db.add(ReminderLog(
        invoice_id=invoice_id,
        document_request_id=document_request_id,
        sent_at=datetime.now(timezone.utc),
        channel=channel,
        payload=payload,
        status=ReminderStatus.sent if success else ReminderStatus.failed,
    ))


def run_escalation_sweep(db: Session):
    """Check all overdue invoices and escalate them through tiers."""
    now = datetime.now(timezone.utc)

    overdue_invoices = db.query(Invoice).filter(
        Invoice.status == InvoiceStatus.overdue,
        Invoice.escalation_tier.in_(["email", "sms"])
    ).all()

    for inv in overdue_invoices:
        try:
            # Initialize escalation_started_at if not set
            if not inv.escalation_started_at:
                inv.escalation_started_at = now
                db.commit()
                continue

            days_in_tier = (now - _as_aware_utc(inv.escalation_started_at)).days

            # TIER 1 → TIER 2: Email to SMS
            if inv.escalation_tier == "email" and days_in_tier >= EMAIL_TO_SMS_DAYS:
                inv.escalation_tier = "sms"
                inv.escalation_started_at = now
                logger.info("invoice_escalated",
                            invoice_id=str(inv.id),
                            invoice_number=inv.invoice_number,
                            from_tier="email", to_tier="sms",
                            days_in_tier=days_in_tier)
                db.commit()

            # TIER 2 → TIER 3: SMS to Voice
            elif inv.escalation_tier == "sms" and days_in_tier >= SMS_TO_VOICE_DAYS:
                inv.escalation_tier = "voice"
                inv.escalation_started_at = now
                logger.info("invoice_escalated",
                            invoice_id=str(inv.id),
                            invoice_number=inv.invoice_number,
                            from_tier="sms", to_tier="voice",
                            days_in_tier=days_in_tier)
                db.commit()
        except Exception as e:
            db.rollback()
            logger.error("escalation_step_failed", invoice_id=str(inv.id), error=str(e), exc_info=True)


def run_sms_reminders(db: Session):
    """Send SMS reminders for invoices in the SMS escalation tier."""
    from src.services.ghl_service import send_sms
    from src.services.usage_limits import can_send_chase, record_chase_used
    from src.services.plan_features import plan_has_feature

    sms_invoices = db.query(Invoice).filter(
        Invoice.status == InvoiceStatus.overdue,
        Invoice.escalation_tier == "sms"
    ).all()

    today_start = datetime.combine(datetime.now(timezone.utc).date(), datetime.min.time(), tzinfo=timezone.utc)

    for inv in sms_invoices:
        # Skip if already sent today
        if inv.last_reminder_sent and _as_aware_utc(inv.last_reminder_sent) >= today_start:
            continue

        debtor = inv.debtor
        if not debtor.phone:
            logger.warning("sms_skipped_no_phone",
                           invoice_id=str(inv.id),
                           debtor_name=debtor.name)
            continue

        user = debtor.user
        if not can_send_chase(user):
            logger.warning("sms_skipped_cannot_send_chase",
                           invoice_id=str(inv.id),
                           user_id=user.id,
                           subscription_status=user.subscription_status,
                           chases_used=user.chases_used,
                           chases_limit=user.chases_limit)
            continue
        company_name = user.company_name or "YourInboxHero"

        # Build SMS message from template (Growth+ only) or default
        sms_template = None
        if plan_has_feature(user.subscription_plan, "custom_templates"):
            sms_template = db.query(EmailTemplate).filter(
                EmailTemplate.user_id == user.id,
                EmailTemplate.template_type == "sms_overdue"
            ).first()

        if sms_template:
            message = sms_template.body
        else:
            message = (
                f"Hi {debtor.name}, Invoice #{inv.invoice_number} for ${inv.amount:.2f} is OVERDUE. "
                f"Please pay now: {inv.payment_link or 'contact us'} - {company_name}"
            )

        # Replace variables
        replacements = {
            "{{debtor_name}}": debtor.name,
            "{{amount_due}}": f"${inv.amount:.2f}",
            "{{invoice_number}}": inv.invoice_number,
            "{{due_date}}": str(inv.due_date),
            "{{company_name}}": company_name,
            "{{payment_link}}": inv.payment_link or ""
        }
        for key, val in replacements.items():
            message = message.replace(key, val)

        try:
            success = send_sms(
                phone=debtor.phone,
                message=message,
                contact_name=debtor.name,
                contact_email=debtor.email
            )

            if success:
                inv.sms_sent_count = (inv.sms_sent_count or 0) + 1
                inv.last_reminder_sent = datetime.now(timezone.utc)
                record_chase_used(user, db, channel='sms', invoice_id=str(inv.id))
                logger.info("sms_sent",
                            invoice_id=str(inv.id),
                            invoice_number=inv.invoice_number,
                            debtor_phone=debtor.phone)
            _log_reminder(
                db, Channel.sms, success,
                payload={"invoice_number": inv.invoice_number, "debtor_phone": debtor.phone},
                invoice_id=inv.id,
            )
            # Commit per-invoice: a later invoice in this loop throwing must
            # not roll back an earlier invoice's already-successful send,
            # which would otherwise cause it to be sent again next run (and
            # not count against the user's quota the first time either).
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error("sms_send_failed", invoice_id=str(inv.id), error=str(e), exc_info=True)


def run_voice_calls(db: Session):
    """Trigger voice calls for invoices in the voice escalation tier.

    Voice is a Growth+/Scale feature per the pricing page — Starter only
    promises email + SMS. A Starter invoice that somehow reaches the voice
    tier (e.g. after a downgrade) is left in place rather than erroring;
    it just never gets called while the plan doesn't cover it.
    """
    from src.services.ghl_service import trigger_voice_call
    from src.services.usage_limits import can_send_chase, record_chase_used
    from src.services.plan_features import plan_has_feature
    from src.services.call_window import is_within_calling_window

    voice_invoices = db.query(Invoice).filter(
        Invoice.status == InvoiceStatus.overdue,
        Invoice.escalation_tier == "voice"
    ).all()

    for inv in voice_invoices:
        # Only call once every 3 days max
        if inv.last_reminder_sent and (datetime.now(timezone.utc) - _as_aware_utc(inv.last_reminder_sent)).days < 3:
            continue

        debtor = inv.debtor

        if not debtor.phone:
            logger.warning("voice_call_skipped_no_phone",
                           invoice_id=str(inv.id),
                           debtor_name=debtor.name)
            continue

        if not debtor.voice_call_consent:
            logger.info("voice_call_skipped_no_consent",
                        invoice_id=str(inv.id),
                        debtor_id=debtor.id)
            continue

        user = debtor.user
        if not plan_has_feature(user.subscription_plan, "voice_escalation"):
            logger.info("voice_call_skipped_plan_tier",
                        invoice_id=str(inv.id),
                        user_id=user.id,
                        plan=user.subscription_plan)
            continue
        if not can_send_chase(user):
            logger.warning("voice_call_skipped_cannot_send_chase",
                           invoice_id=str(inv.id),
                           user_id=user.id,
                           subscription_status=user.subscription_status,
                           chases_used=user.chases_used,
                           chases_limit=user.chases_limit)
            continue
        if not is_within_calling_window(user):
            logger.info("voice_call_skipped_outside_calling_window",
                        invoice_id=str(inv.id),
                        user_id=user.id)
            continue
        company_name = user.company_name or "YourInboxHero"
        message = (
            f"This is an automated call from {company_name}. Invoice number {inv.invoice_number} "
            f"for ${inv.amount:.2f} is overdue. Please make your payment immediately."
        )

        try:
            success = trigger_voice_call(
                phone=debtor.phone,
                message=message,
                contact_name=debtor.name,
                contact_email=debtor.email,
                company_name=company_name,
                reason="invoice",
                item_description=inv.invoice_number,
                amount=f"{inv.amount:.2f}",
                due_date=inv.due_date.isoformat(),
            )

            if success:
                inv.voice_call_count = (inv.voice_call_count or 0) + 1
                inv.last_reminder_sent = datetime.now(timezone.utc)
                record_chase_used(user, db, channel='voice', invoice_id=str(inv.id))
                logger.info("voice_call_triggered",
                            invoice_id=str(inv.id),
                            invoice_number=inv.invoice_number,
                            debtor_phone=debtor.phone)
            _log_reminder(
                db, Channel.voice, success,
                payload={"invoice_number": inv.invoice_number, "debtor_phone": debtor.phone},
                invoice_id=inv.id,
            )
            # Commit per-invoice — see the matching comment in run_sms_reminders.
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error("voice_call_failed", invoice_id=str(inv.id), error=str(e), exc_info=True)


def run_document_escalation_sweep(db: Session):
    """Check all overdue document requests and escalate them through
    tiers. Mirrors run_escalation_sweep exactly, for DocumentRequest
    instead of Invoice."""
    now = datetime.now(timezone.utc)

    overdue_requests = db.query(DocumentRequest).filter(
        DocumentRequest.status == "overdue",
        DocumentRequest.escalation_tier.in_(["email", "sms"])
    ).all()

    for req in overdue_requests:
        try:
            if not req.escalation_started_at:
                req.escalation_started_at = now
                db.commit()
                continue

            days_in_tier = (now - _as_aware_utc(req.escalation_started_at)).days

            if req.escalation_tier == "email" and days_in_tier >= EMAIL_TO_SMS_DAYS:
                req.escalation_tier = "sms"
                req.escalation_started_at = now
                logger.info("document_request_escalated",
                            doc_request_id=str(req.id), title=req.title,
                            from_tier="email", to_tier="sms",
                            days_in_tier=days_in_tier)
                db.commit()

            elif req.escalation_tier == "sms" and days_in_tier >= SMS_TO_VOICE_DAYS:
                req.escalation_tier = "voice"
                req.escalation_started_at = now
                logger.info("document_request_escalated",
                            doc_request_id=str(req.id), title=req.title,
                            from_tier="sms", to_tier="voice",
                            days_in_tier=days_in_tier)
                db.commit()
        except Exception as e:
            db.rollback()
            logger.error("document_escalation_step_failed", doc_request_id=str(req.id), error=str(e), exc_info=True)


def _group_by_client(requests):
    """Group document requests by client, preserving query order, so each
    client gets one SMS/call covering every document they owe."""
    groups = {}
    for req in requests:
        groups.setdefault(req.client_id, []).append(req)
    return list(groups.values())


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


def run_document_sms_reminders(db: Session):
    """Send SMS reminders for document requests in the SMS escalation
    tier. Mirrors run_sms_reminders, except a client who owes several
    documents gets one text listing them (one chase) rather than one text
    per document."""
    from src.services.ghl_service import send_sms
    from src.services.usage_limits import can_send_chase, record_chase_used

    sms_requests = db.query(DocumentRequest).filter(
        DocumentRequest.status == "overdue",
        DocumentRequest.escalation_tier == "sms"
    ).order_by(DocumentRequest.due_date, DocumentRequest.title).all()

    today_start = datetime.combine(datetime.now(timezone.utc).date(), datetime.min.time(), tzinfo=timezone.utc)
    due_today = [
        r for r in sms_requests
        if not (r.last_reminder_sent and _as_aware_utc(r.last_reminder_sent) >= today_start)
    ]

    for reqs in _group_by_client(due_today):
        client = reqs[0].client
        req_ids = [str(r.id) for r in reqs]
        if not client.phone:
            logger.warning("document_sms_skipped_no_phone", doc_request_ids=req_ids, client_name=client.name)
            continue

        user = client.user
        if not can_send_chase(user):
            logger.warning("document_sms_skipped_cannot_send_chase",
                           doc_request_ids=req_ids, user_id=user.id,
                           subscription_status=user.subscription_status,
                           chases_used=user.chases_used, chases_limit=user.chases_limit)
            continue

        company_name = user.company_name or "YourInboxHero"
        message = _document_sms_message(client.name, company_name, reqs)

        try:
            success = send_sms(phone=client.phone, message=message, contact_name=client.name, contact_email=client.email)

            now = datetime.now(timezone.utc)
            for req in reqs:
                if success:
                    req.sms_sent_count = (req.sms_sent_count or 0) + 1
                    req.last_reminder_sent = now
                _log_reminder(
                    db, Channel.sms, success,
                    payload={"title": req.title, "client_phone": client.phone},
                    document_request_id=req.id,
                )
            if success:
                record_chase_used(user, db, channel='sms', invoice_id=req_ids[0])
                logger.info("document_sms_sent", doc_request_ids=req_ids, client_phone=client.phone)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error("document_sms_send_failed", doc_request_ids=req_ids, error=str(e), exc_info=True)


def run_document_voice_calls(db: Session):
    """Trigger voice calls for document requests in the voice escalation
    tier. Mirrors run_voice_calls, including the same
    plan-tier/consent/quota gates, except a client who owes several
    documents gets one call that mentions all of them."""
    from src.services.ghl_service import trigger_voice_call
    from src.services.usage_limits import can_send_chase, record_chase_used
    from src.services.plan_features import plan_has_feature
    from src.services.call_window import is_within_calling_window

    voice_requests = db.query(DocumentRequest).filter(
        DocumentRequest.status == "overdue",
        DocumentRequest.escalation_tier == "voice"
    ).order_by(DocumentRequest.due_date, DocumentRequest.title).all()

    due_now = [
        r for r in voice_requests
        if not (r.last_reminder_sent and (datetime.now(timezone.utc) - _as_aware_utc(r.last_reminder_sent)).days < 3)
    ]

    for reqs in _group_by_client(due_now):
        client = reqs[0].client
        req_ids = [str(r.id) for r in reqs]

        if not client.phone:
            logger.warning("document_voice_call_skipped_no_phone", doc_request_ids=req_ids, client_name=client.name)
            continue

        if not client.voice_call_consent:
            logger.info("document_voice_call_skipped_no_consent", doc_request_ids=req_ids, client_id=client.id)
            continue

        user = client.user
        if not plan_has_feature(user.subscription_plan, "voice_escalation"):
            logger.info("document_voice_call_skipped_plan_tier", doc_request_ids=req_ids, user_id=user.id, plan=user.subscription_plan)
            continue
        if not can_send_chase(user):
            logger.warning("document_voice_call_skipped_cannot_send_chase",
                           doc_request_ids=req_ids, user_id=user.id,
                           subscription_status=user.subscription_status,
                           chases_used=user.chases_used, chases_limit=user.chases_limit)
            continue
        if not is_within_calling_window(user):
            logger.info("document_voice_call_skipped_outside_calling_window", doc_request_ids=req_ids, user_id=user.id)
            continue

        company_name = user.company_name or "YourInboxHero"
        single = len(reqs) == 1
        titles = _join_titles([r.title for r in reqs])
        message = (
            f"This is an automated call from {company_name}. The {'document' if single else 'documents'} {titles} "
            f"we requested {'is' if single else 'are'} overdue. Please upload {'it' if single else 'them'} as soon as possible."
        )

        try:
            success = trigger_voice_call(
                phone=client.phone,
                message=message,
                contact_name=client.name,
                contact_email=client.email,
                company_name=company_name,
                reason="document",
                item_description=titles.replace('"', ''),
                amount="",
                due_date=reqs[0].due_date.isoformat(),
            )

            now = datetime.now(timezone.utc)
            for req in reqs:
                if success:
                    req.voice_call_count = (req.voice_call_count or 0) + 1
                    req.last_reminder_sent = now
                _log_reminder(
                    db, Channel.voice, success,
                    payload={"title": req.title, "client_phone": client.phone},
                    document_request_id=req.id,
                )
            if success:
                record_chase_used(user, db, channel='voice', invoice_id=req_ids[0])
                logger.info("document_voice_call_triggered", doc_request_ids=req_ids, client_phone=client.phone)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error("document_voice_call_failed", doc_request_ids=req_ids, error=str(e), exc_info=True)


SWEEP_RUN_ID = "daily_sweep"


def _mark_sweep_run_today(db: Session) -> None:
    """Upsert today's date into sweep_run, so the startup catch-up check
    (run_catch_up_sweep_if_needed) knows this already happened."""
    from src.models.sweep_run import SweepRun

    today = datetime.now(timezone.utc).date()
    row = db.query(SweepRun).filter(SweepRun.id == SWEEP_RUN_ID).first()
    if row:
        row.last_run_date = today
    else:
        db.add(SweepRun(id=SWEEP_RUN_ID, last_run_date=today))
    db.commit()


def run_daily_sweep():
    """Main daily sweep job."""
    logger.info("daily_sweep_started")

    db: Session = SessionLocal()
    try:
        # Each step is isolated: a failure in one (e.g. email provider
        # outage) must not prevent the others from running, since they
        # cover different invoices/channels.
        from src.services.account_notifications import reset_admin_invite_usage

        steps = [
            ("overdue_transition", lambda: transition_overdue(db)),
            ("pre_due_reminders", lambda: process_due_reminders() if settings.reminders_enabled
                else logger.info("reminders_disabled_via_settings")),
            ("escalation_sweep", lambda: run_escalation_sweep(db)),
            ("sms_reminders", lambda: run_sms_reminders(db)),
            ("document_overdue_transition", lambda: transition_overdue_documents(db)),
            ("document_pre_due_reminders", lambda: process_due_document_reminders() if settings.reminders_enabled
                else logger.info("document_reminders_disabled_via_settings")),
            ("document_escalation_sweep", lambda: run_document_escalation_sweep(db)),
            ("document_sms_reminders", lambda: run_document_sms_reminders(db)),
            ("admin_invite_usage_reset", lambda: reset_admin_invite_usage(db)),
        ]
        for step_name, step_fn in steps:
            try:
                result = step_fn()
                if step_name in ("overdue_transition", "document_overdue_transition"):
                    logger.info(f"{step_name}_completed", count=result)
                elif step_name == "admin_invite_usage_reset" and result:
                    logger.info("admin_invite_usage_reset_completed", count=result)
            except Exception as e:
                logger.error("daily_sweep_step_failed", step=step_name, error=str(e), exc_info=True)

        _mark_sweep_run_today(db)

    except Exception as e:
        logger.error("daily_sweep_failed", error=str(e), exc_info=True)
    finally:
        db.close()

    logger.info("daily_sweep_completed")


def run_voice_calls_hourly():
    """Separate from the once-daily 08:00 UTC sweep, since a single run
    that early (~3-4am America/New_York) can never fall inside any
    customer's business-hours calling window. Runs every hour; each
    user's own voice_call_days/start_hour/end_hour/timezone (checked via
    is_within_calling_window) decides whether this hour's run actually
    places calls for them."""
    logger.info("voice_calls_hourly_started")
    db: Session = SessionLocal()
    try:
        try:
            run_voice_calls(db)
        except Exception as e:
            logger.error("voice_calls_hourly_step_failed", step="voice_calls", error=str(e), exc_info=True)
        try:
            run_document_voice_calls(db)
        except Exception as e:
            logger.error("voice_calls_hourly_step_failed", step="document_voice_calls", error=str(e), exc_info=True)
    except Exception as e:
        logger.error("voice_calls_hourly_failed", error=str(e), exc_info=True)
    finally:
        db.close()
    logger.info("voice_calls_hourly_completed")


def run_catch_up_sweep_if_needed():
    """Called once at app startup. If today's scheduled 08:00 UTC sweep
    hasn't run yet (e.g. the container was down at that time, or this is
    the first deploy of the day), run it immediately instead of silently
    waiting until tomorrow's cron fire."""
    from src.models.sweep_run import SweepRun

    db: Session = SessionLocal()
    try:
        row = db.query(SweepRun).filter(SweepRun.id == SWEEP_RUN_ID).first()
        today = datetime.now(timezone.utc).date()
        already_ran_today = row is not None and row.last_run_date == today
    finally:
        db.close()

    if already_ran_today:
        logger.info("daily_sweep_catch_up_not_needed")
        return

    logger.info("daily_sweep_catch_up_running")
    run_daily_sweep()


def start_scheduler():
    """Start the APScheduler with daily sweep job, plus an immediate
    catch-up run if today's scheduled sweep hasn't happened yet."""
    scheduler.add_job(
        run_daily_sweep,
        trigger=CronTrigger(hour=8, minute=0, timezone="UTC"),
        id="daily_sweep_job",
        name="Daily Invoice Sweep",
        replace_existing=True,
        max_instances=1,  # Prevent overlapping runs
        coalesce=True,    # Combine missed runs
    )
    scheduler.add_job(
        run_voice_calls_hourly,
        trigger=CronTrigger(minute=0, timezone="UTC"),
        id="voice_calls_hourly_job",
        name="Hourly Voice Call Window Check",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info("scheduler_started", job_id="daily_sweep_job")

    run_catch_up_sweep_if_needed()


def shutdown_scheduler():
    """Gracefully shut down the scheduler."""
    scheduler.shutdown(wait=True)
    logger.info("scheduler_shutdown")
