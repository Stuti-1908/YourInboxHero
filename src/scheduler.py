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
from src.models.email_template import EmailTemplate  # noqa: F401
from src.models.document_request import DocumentRequest  # noqa: F401
from src.models.document_client import DocumentClient  # noqa: F401
from src.services.overdue_service import transition_overdue
from src.services.document_overdue_service import transition_overdue as transition_overdue_documents
from src.config.settings import get_settings
from src.services.followup import DAILY_KINDS, HOURLY_KINDS, run_document_followups, run_invoice_followups

logger = structlog.get_logger(__name__)
settings = get_settings()

scheduler = BackgroundScheduler()


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

        follow_ups_on = settings.reminders_enabled
        steps = [
            # Status labels first, so the dashboard shows "overdue" correctly.
            ("overdue_transition", lambda: transition_overdue(db)),
            ("document_overdue_transition", lambda: transition_overdue_documents(db)),
            # The follow-up schedule (src/services/followup.py). Calls run
            # from the hourly job instead, inside each customer's calling hours.
            ("invoice_followups", lambda: run_invoice_followups(db, DAILY_KINDS) if follow_ups_on
                else logger.info("reminders_disabled_via_settings")),
            ("document_followups", lambda: run_document_followups(db, DAILY_KINDS) if follow_ups_on
                else logger.info("document_reminders_disabled_via_settings")),
            ("admin_invite_usage_reset", lambda: reset_admin_invite_usage(db)),
        ]
        for step_name, step_fn in steps:
            try:
                result = step_fn()
                if step_name in ("overdue_transition", "document_overdue_transition",
                                 "invoice_followups", "document_followups"):
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
        if not settings.reminders_enabled:
            return
        for step_name, step_fn in (
            ("invoice_voice_followups", lambda: run_invoice_followups(db, HOURLY_KINDS)),
            ("document_voice_followups", lambda: run_document_followups(db, HOURLY_KINDS)),
        ):
            try:
                step_fn()
            except Exception as e:
                logger.error("voice_calls_hourly_step_failed", step=step_name, error=str(e), exc_info=True)
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
        # Half past, so it never starts alongside the 08:00 daily run.
        trigger=CronTrigger(minute=30, timezone="UTC"),
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
