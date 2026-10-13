"""Per-user voice-call calling-window check.

Each customer restricts which days/hours (in their own timezone) our
automated voice escalation is allowed to call debtors/clients. The sweep
that triggers voice calls runs hourly (see src/scheduler.py's
voice_calls_hourly job) and uses is_within_calling_window() to skip any
user whose local time currently falls outside their configured window.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from src.models.user import User

_DAY_CODES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def is_within_calling_window(user: User, now_utc: datetime = None) -> bool:
    """True if `now_utc` (default: current time) falls within this user's
    configured voice-calling window, evaluated in their own timezone."""
    now_utc = now_utc or datetime.now(timezone.utc)

    try:
        tz = ZoneInfo(user.voice_call_timezone or "America/New_York")
    except Exception:
        tz = ZoneInfo("America/New_York")

    local_now = now_utc.astimezone(tz)

    allowed_days = {d.strip().lower() for d in (user.voice_call_days or "").split(",") if d.strip()}
    today_code = _DAY_CODES[local_now.weekday()]
    if today_code not in allowed_days:
        return False

    start_hour = user.voice_call_start_hour if user.voice_call_start_hour is not None else 9
    end_hour = user.voice_call_end_hour if user.voice_call_end_hour is not None else 17

    return start_hour <= local_now.hour < end_hour
