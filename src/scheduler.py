"""Daily sweep scheduler with distributed locking for multi-instance safety."""
import logging
import structlog
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import text
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
from contextlib import contextmanager

from src.db import SessionLocal
from src.models.user import User  # noqa: F401
from src.models.debtor import Debtor  # noqa: F401
from src.models.invoice import Invoice, InvoiceStatus  # noqa: F401
from src.models.reminder import ReminderLog  # noqa: F401
from src.models.email_template import EmailTemplate  # noqa: F401
from src.services.overdue_service import transition_overdue
from src.services.reminder_service import process_due_reminders
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

# PostgreSQL advisory lock key for daily sweep (arbitrary but consistent)
SWEEP_LOCK_KEY = 1234567890


@contextmanager
def sweep_lock(db: Session):
    """
    PostgreSQL advisory lock to ensure only one instance runs the daily sweep.
    
    Returns True if lock acquired, False otherwise.
    """
    # Try to acquire lock (non-blocking)
    result = db.execute(text("SELECT pg_try_advisory_lock(:lock_key)"), {"lock_key": SWEEP_LOCK_KEY})
    acquired = result.scalar()
    
    if not acquired:
        logger.warning("daily_sweep_lock_not_acquired", lock_key=SWEEP_LOCK_KEY)
        yield False
        return
    
    logger.info("daily_sweep_lock_acquired", lock_key=SWEEP_LOCK_KEY)
    try:
        yield True
    finally:
        # Release lock
        db.execute(text("SELECT pg_advisory_unlock(:lock_key)"), {"lock_key": SWEEP_LOCK_KEY})
        db.commit()
        logger.info("daily_sweep_lock_released", lock_key=SWEEP_LOCK_KEY)


def run_escalation_sweep(db: Session):
    """Check all overdue invoices and escalate them through tiers."""
    now = datetime.now(timezone.utc)
    
    overdue_invoices = db.query(Invoice).filter(
        Invoice.status == InvoiceStatus.overdue,
        Invoice.escalation_tier.in_(["email", "sms"])
    ).all()
    
    for inv in overdue_invoices:
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
                EmailTemplate.template_type == "overdue"
            ).first()

        if sms_template:
            message = sms_template.body
        else:
            message = f"Hi {debtor.name}, Invoice #{inv.invoice_number} for ${inv.amount:.2f} is OVERDUE. Please pay now: {inv.payment_link or 'contact us'} - {company_name}"
        
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

    db.commit()


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
        company_name = user.company_name or "YourInboxHero"
        message = f"This is an automated call from {company_name}. Invoice number {inv.invoice_number} for ${inv.amount:.2f} is overdue. Please make your payment immediately."

        success = trigger_voice_call(
            phone=debtor.phone,
            message=message,
            contact_name=debtor.name,
            contact_email=debtor.email
        )

        if success:
            inv.voice_call_count = (inv.voice_call_count or 0) + 1
            inv.last_reminder_sent = datetime.now(timezone.utc)
            record_chase_used(user, db, channel='voice', invoice_id=str(inv.id))
            logger.info("voice_call_triggered",
                       invoice_id=str(inv.id),
                       invoice_number=inv.invoice_number,
                       debtor_phone=debtor.phone)

    db.commit()


def run_daily_sweep():
    """Main daily sweep job with distributed lock."""
    logger.info("daily_sweep_started")
    
    db: Session = SessionLocal()
    try:
        with sweep_lock(db) as acquired:
            if not acquired:
                logger.info("daily_sweep_skipped_another_instance_running")
                return
            
            # Each step is isolated: a failure in one (e.g. email provider
            # outage) must not prevent the others from running, since they
            # cover different invoices/channels.
            steps = [
                ("overdue_transition", lambda: transition_overdue(db)),
                ("pre_due_reminders", lambda: process_due_reminders() if settings.reminders_enabled
                    else logger.info("reminders_disabled_via_settings")),
                ("escalation_sweep", lambda: run_escalation_sweep(db)),
                ("sms_reminders", lambda: run_sms_reminders(db)),
                ("voice_calls", lambda: run_voice_calls(db)),
            ]
            for step_name, step_fn in steps:
                try:
                    result = step_fn()
                    if step_name == "overdue_transition":
                        logger.info("overdue_transition_completed", count=result)
                except Exception as e:
                    logger.error(f"daily_sweep_step_failed", step=step_name, error=str(e), exc_info=True)
            
    except Exception as e:
        logger.error("daily_sweep_failed", error=str(e), exc_info=True)
    finally:
        db.close()
    
    logger.info("daily_sweep_completed")


def start_scheduler():
    """Start the APScheduler with daily sweep job."""
    scheduler.add_job(
        run_daily_sweep,
        trigger=CronTrigger(hour=8, minute=0, timezone="UTC"),
        id="daily_sweep_job",
        name="Daily Invoice Sweep",
        replace_existing=True,
        max_instances=1,  # Prevent overlapping runs
        coalesce=True,    # Combine missed runs
    )
    scheduler.start()
    logger.info("scheduler_started", job_id="daily_sweep_job")


def shutdown_scheduler():
    """Gracefully shut down the scheduler."""
    scheduler.shutdown(wait=True)
    logger.info("scheduler_shutdown")