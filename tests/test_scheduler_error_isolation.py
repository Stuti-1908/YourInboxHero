"""Tests for scheduler hardening: a failing step never stops the rest of
the daily sweep, and the daily-sweep-ran-today tracking used by the startup
catch-up check. (Per-item send isolation is covered in test_followup.py.)
"""
from datetime import datetime, timezone
from unittest.mock import patch

from src.db import SessionLocal
from src.models.sweep_run import SweepRun
from src.scheduler import (
    _mark_sweep_run_today, SWEEP_RUN_ID,
    run_daily_sweep, run_catch_up_sweep_if_needed,
)


def test_mark_sweep_run_today_is_idempotent():
    session = SessionLocal()
    try:
        _mark_sweep_run_today(session)
        _mark_sweep_run_today(session)  # must not raise on the second call
        row = session.query(SweepRun).filter(SweepRun.id == SWEEP_RUN_ID).first()
        assert row is not None
        assert row.last_run_date == datetime.now(timezone.utc).date()
    finally:
        session.close()


def test_run_daily_sweep_marks_sweep_run_even_if_a_step_raises():
    """H4: one step (e.g. overdue_transition) raising must not prevent
    later steps from running, and must not prevent _mark_sweep_run_today
    from recording that the sweep happened -- otherwise a single bad step
    would make the startup catch-up check re-run the whole sweep forever."""
    session = SessionLocal()
    try:
        session.query(SweepRun).filter(SweepRun.id == SWEEP_RUN_ID).delete()
        session.commit()
    finally:
        session.close()

    with patch('src.scheduler.transition_overdue', side_effect=RuntimeError("boom")):
        run_daily_sweep()  # must not raise

    session = SessionLocal()
    try:
        row = session.query(SweepRun).filter(SweepRun.id == SWEEP_RUN_ID).first()
        assert row is not None
        assert row.last_run_date == datetime.now(timezone.utc).date()
    finally:
        session.close()


def test_run_catch_up_sweep_skips_when_already_run_today():
    """If today's scheduled sweep already ran, the startup catch-up check
    must not trigger a second run."""
    session = SessionLocal()
    try:
        _mark_sweep_run_today(session)
    finally:
        session.close()

    with patch('src.scheduler.run_daily_sweep') as mock_sweep:
        run_catch_up_sweep_if_needed()
        mock_sweep.assert_not_called()


def test_run_catch_up_sweep_runs_when_not_yet_run_today():
    """If no sweep has run today (e.g. container was down at 08:00 UTC),
    the startup catch-up check must trigger one immediately."""
    session = SessionLocal()
    try:
        session.query(SweepRun).filter(SweepRun.id == SWEEP_RUN_ID).delete()
        session.commit()
    finally:
        session.close()

    with patch('src.scheduler.run_daily_sweep') as mock_sweep:
        run_catch_up_sweep_if_needed()
        mock_sweep.assert_called_once()
