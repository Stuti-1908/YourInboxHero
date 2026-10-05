"""Tracks when the daily sweep last completed, so a startup catch-up check
(see src/scheduler.py's run_catch_up_sweep_if_needed) can tell whether
today's 08:00 UTC run was missed (e.g. the container was down at that
time) and needs to run immediately instead of waiting until tomorrow.
"""
from sqlalchemy import Column, String, Date
from .base import Base


class SweepRun(Base):
    __tablename__ = "sweep_run"
    # Single-row table: always upserted at id='daily_sweep'. A real table
    # (not just a settings/cache value) so it survives container restarts.
    id = Column(String, primary_key=True)
    last_run_date = Column(Date, nullable=False)
