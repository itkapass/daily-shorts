"""
api_budget.py — two independent daily budgets, tracked the same way.
======================================================================
Adapted from the reference project's engine/api_budget.py (same reasoning:
reserve before starting, one quota error stops the whole run for THAT
budget, persist the count across runs so a restart doesn't reset it).

This project needs TWO budgets, not one, because they come from two
unrelated services with two different daily resets:

  LLM_BUDGET      — Gemini's free-tier generate_content calls/day.
                    Resets midnight PACIFIC (daycycle.quota_day()).
  YOUTUBE_BUDGET   — YouTube Data API units/day (Section 8): default
                    10,000 units, ~1,600/upload + ~50/thumbnail + ~50 per
                    playlist call. Resets midnight PACIFIC too (that is
                    when Google's quota actually resets, confirmed in the
                    reference project's own docs — not midnight in the
                    channel's local time).

Both are Settings-table rows keyed by day, exactly like the reference
project's single budget was.
"""
from engine import daycycle

DEFAULT_LLM_DAILY_BUDGET = 20          # Gemini free tier, per reference project
LLM_RESERVE_HEADROOM = 2

DEFAULT_YOUTUBE_DAILY_UNITS = 10_000
YOUTUBE_UPLOAD_COST = 1_600
YOUTUBE_THUMBNAIL_COST = 50
YOUTUBE_PLAYLIST_CALL_COST = 50        # playlists.insert / playlistItems.insert, each
YOUTUBE_RESERVE_UNITS = 300            # headroom for a retry + health check


class QuotaExhausted(Exception):
    """Raised when a daily budget is gone. Callers should stop issuing more
    work against THIS budget, not retry the next item and hit it again."""


class BudgetTracker:
    """A single named daily counter, persisted in the `settings` table."""

    def __init__(self, db, name: str, daily_budget: int, reserve: int = 0):
        self.db = db
        self.name = name
        self.daily_budget = int(daily_budget)
        self.reserve = int(reserve)
        self.spent = 0
        self._loaded = False
        self._hard_stopped = False

    def _key(self) -> str:
        return f"budget_{self.name}_{daycycle.quota_day()}"

    def load(self):
        if self._loaded:
            return
        try:
            rows = (self.db.table("settings").select("key, value")
                    .eq("key", self._key()).execute().data) or []
            self.spent = int(rows[0]["value"]) if rows else 0
        except Exception as e:
            print(f"[api_budget] Could not read '{self.name}' usage ({e}); assuming 0.")
            self.spent = 0
        self._loaded = True
        print(f"[api_budget] {self.name}: {self.spent}/{self.daily_budget} used today.")

    def _persist(self):
        try:
            key = self._key()
            existing = self.db.table("settings").select("key").eq("key", key).execute().data
            if existing:
                self.db.table("settings").update({"value": str(self.spent)}).eq("key", key).execute()
            else:
                self.db.table("settings").insert({"key": key, "value": str(self.spent)}).execute()
        except Exception as e:
            print(f"[api_budget] Could not save '{self.name}' usage: {e}")

    @property
    def remaining(self) -> int:
        return max(0, self.daily_budget - self.reserve - self.spent)

    def can_afford(self, amount: int) -> bool:
        self.load()
        return not self._hard_stopped and self.remaining >= amount

    def require(self, amount: int, what: str = "this step"):
        self.load()
        if self._hard_stopped or self.remaining < amount:
            raise QuotaExhausted(
                f"'{self.name}' budget exhausted for today: needs {amount}, "
                f"{self.remaining} remaining of {self.daily_budget}. "
                f"Refills in about {daycycle.humanize_until_reset()} (midnight Pacific)."
            )

    def spend(self, amount: int = 1):
        self.load()
        self.spent += amount
        self._persist()

    def hard_stop(self, reason: str = ""):
        self._hard_stopped = True
        self.spent = self.daily_budget
        self._persist()
        print(f"[api_budget] HARD STOP on '{self.name}'. {reason}")

    @property
    def stopped(self) -> bool:
        return self._hard_stopped


def llm_budget(db) -> BudgetTracker:
    return BudgetTracker(db, "llm_calls", DEFAULT_LLM_DAILY_BUDGET, LLM_RESERVE_HEADROOM)


def youtube_budget(db) -> BudgetTracker:
    return BudgetTracker(db, "youtube_units", DEFAULT_YOUTUBE_DAILY_UNITS, YOUTUBE_RESERVE_UNITS)


def max_uploads_today(db) -> int:
    """How many more uploads the YouTube budget can afford right now,
    including this run's share of playlist calls (Section 8's
    hard-cap-of-~6-uploads/day rule, computed rather than hardcoded so it
    stays correct if Google changes per-call costs)."""
    yb = youtube_budget(db)
    yb.load()
    per_video_cost = YOUTUBE_UPLOAD_COST + YOUTUBE_THUMBNAIL_COST + (2 * YOUTUBE_PLAYLIST_CALL_COST)
    return max(0, yb.remaining // per_video_cost)


def is_rate_limit_error(exc) -> bool:
    text = str(exc)
    return "RESOURCE_EXHAUSTED" in text or "429" in text or "quota" in text.lower()


def is_per_minute_limit(exc) -> bool:
    text = str(exc)
    if "PerDay" in text:
        return False
    return "PerMinute" in text or "RequestsPerMinute" in text


def is_quota_error(exc) -> bool:
    return is_rate_limit_error(exc) and not is_per_minute_limit(exc)


def retry_delay_seconds(exc, default: int = 35) -> int:
    import re
    m = re.search(r"retryDelay['\"]?\s*:\s*['\"]?(\d+)s", str(exc))
    if m:
        return min(int(m.group(1)) + 5, 120)
    return default
