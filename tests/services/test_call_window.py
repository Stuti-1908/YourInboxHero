"""Tests for the per-user voice-call calling-window check."""
from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.services.call_window import is_within_calling_window


def _user(days="mon,tue,wed,thu,fri", start=9, end=17, tz="America/New_York"):
    u = MagicMock()
    u.voice_call_days = days
    u.voice_call_start_hour = start
    u.voice_call_end_hour = end
    u.voice_call_timezone = tz
    return u


def test_within_window_on_weekday_during_hours():
    # 2026-10-13 is a Tuesday. 15:00 UTC = 11:00 America/New_York (EDT, UTC-4).
    now = datetime(2026, 10, 13, 15, 0, tzinfo=timezone.utc)
    assert is_within_calling_window(_user(), now_utc=now) is True


def test_outside_window_before_start_hour():
    # 11:00 UTC = 07:00 America/New_York -- before the 9am default start.
    now = datetime(2026, 10, 13, 11, 0, tzinfo=timezone.utc)
    assert is_within_calling_window(_user(), now_utc=now) is False


def test_outside_window_after_end_hour():
    # 22:00 UTC = 18:00 America/New_York -- after the 5pm default end.
    now = datetime(2026, 10, 13, 22, 0, tzinfo=timezone.utc)
    assert is_within_calling_window(_user(), now_utc=now) is False


def test_outside_window_on_weekend():
    # 2026-10-17 is a Saturday, 15:00 UTC = 11:00 America/New_York.
    now = datetime(2026, 10, 17, 15, 0, tzinfo=timezone.utc)
    assert is_within_calling_window(_user(), now_utc=now) is False


def test_end_hour_is_exclusive():
    # Exactly 17:00 America/New_York local time -- window is [start, end).
    now = datetime(2026, 10, 13, 21, 0, tzinfo=timezone.utc)
    assert is_within_calling_window(_user(), now_utc=now) is False


def test_respects_custom_days_and_hours():
    # Only Saturdays, 10am-12pm America/New_York.
    u = _user(days="sat", start=10, end=12)
    saturday_within = datetime(2026, 10, 17, 15, 0, tzinfo=timezone.utc)  # 11:00 NY
    tuesday_outside = datetime(2026, 10, 13, 15, 0, tzinfo=timezone.utc)  # Tue, not Sat
    assert is_within_calling_window(u, now_utc=saturday_within) is True
    assert is_within_calling_window(u, now_utc=tuesday_outside) is False


def test_respects_custom_timezone():
    # 9am-5pm UTC directly -- no DST conversion needed.
    u = _user(start=9, end=17, tz="UTC")
    now_within = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
    now_outside = datetime(2026, 10, 13, 20, 0, tzinfo=timezone.utc)
    assert is_within_calling_window(u, now_utc=now_within) is True
    assert is_within_calling_window(u, now_utc=now_outside) is False


def test_falls_back_to_america_new_york_on_invalid_timezone():
    u = _user(tz="Not/A_Real_Zone")
    now = datetime(2026, 10, 13, 15, 0, tzinfo=timezone.utc)  # 11:00 America/New_York
    assert is_within_calling_window(u, now_utc=now) is True


def test_falls_back_to_defaults_on_empty_days():
    u = _user(days="")
    now = datetime(2026, 10, 13, 15, 0, tzinfo=timezone.utc)
    assert is_within_calling_window(u, now_utc=now) is False
