"""
daycycle.py — one definition of "today", matching the API that actually
counts, and one definition of "tonight's posting window" for scheduling.
==============================================================================
Adapted from the reference project's hard-won fix (see its own module
docstring): daily quota counters must be keyed in the SAME timezone the
provider resets in, not UTC, or a few hours of drift silently pins a
counter to "exhausted" for a day whose quota is actually untouched.

This project adds a second clock: the POSTING WINDOW from the build spec
(Section 5) is "11:00 PM to 5:00 AM the next calendar day" in the
channel's own local time — a deliberately different concept from Gemini's
reset clock, so the two must never share a key.
"""
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    _QUOTA_TZ = ZoneInfo("America/Los_Angeles")   # Gemini free-tier resets at midnight Pacific
except Exception:  # pragma: no cover — only if tzdata is missing entirely
    _QUOTA_TZ = timezone(timedelta(hours=-8))

# The channel's own local day — used for the posting window and the
# YouTube daily-upload cap. Change this to your audience's timezone.
DEFAULT_LOCAL_TZ = "Asia/Kolkata"


def quota_now() -> datetime:
    return datetime.now(_QUOTA_TZ)


def quota_day() -> str:
    """Keys LLM daily-quota counters (api_budget.py). e.g. '2026_10_12'."""
    return quota_now().strftime("%Y_%m_%d")


def seconds_until_quota_reset() -> int:
    now = quota_now()
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(0, int((tomorrow - now).total_seconds()))


def humanize_until_reset() -> str:
    secs = seconds_until_quota_reset()
    hours, rem = divmod(secs, 3600)
    mins = rem // 60
    return f"{hours}h {mins}m" if hours else f"{mins}m"


def local_tz(name: str = None):
    try:
        return ZoneInfo(name or DEFAULT_LOCAL_TZ)
    except Exception:
        return timezone.utc


def local_now(tz_name: str = None) -> datetime:
    return datetime.now(local_tz(tz_name))


def local_day(tz_name: str = None) -> str:
    """Keys the YouTube daily-upload cap (api_budget.py) and the posting
    window below — the channel's own day, not Google's or Gemini's."""
    return local_now(tz_name).strftime("%Y_%m_%d")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ── Posting window: 11:00 PM -> 5:00 AM next calendar day (Section 5) ───────

POSTING_WINDOW_START_HOUR = 23   # 11 PM local
POSTING_WINDOW_END_HOUR = 5      # 5 AM local, next calendar day
MIN_SLOT_GAP_MINUTES = 25        # mid-point of the spec's "20-30 minutes apart"


def in_posting_window(dt: datetime = None, tz_name: str = None) -> bool:
    dt = dt or local_now(tz_name)
    h = dt.hour
    return h >= POSTING_WINDOW_START_HOUR or h < POSTING_WINDOW_END_HOUR


def next_window_start(after: datetime = None, tz_name: str = None) -> datetime:
    """The next moment the posting window opens, at or after `after`."""
    tz = local_tz(tz_name)
    after = after or local_now(tz_name)
    candidate = after.replace(hour=POSTING_WINDOW_START_HOUR, minute=0, second=0, microsecond=0)
    if after.hour < POSTING_WINDOW_END_HOUR:
        # already inside tonight's window (post-midnight half)
        return after
    if after >= candidate:
        candidate += timedelta(days=1)
    return candidate


def build_slot_schedule(n_slots: int, start_at: datetime = None, tz_name: str = None) -> list:
    """Returns `n_slots` datetimes inside one posting window, each at least
    MIN_SLOT_GAP_MINUTES apart and in ascending order — Section 5's
    "order them ascending ... spaced at least 20-30 minutes apart" rule.
    """
    start_at = start_at or next_window_start(tz_name=tz_name)
    return [start_at + timedelta(minutes=MIN_SLOT_GAP_MINUTES * i) for i in range(n_slots)]
