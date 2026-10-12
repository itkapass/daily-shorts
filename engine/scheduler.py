"""
scheduler.py — Section 5 (posting window/spacing) + Section 8 (quota cap,
queue overflow) + Section 10 (evergreen fallback substitution).
============================================================================
"Posting window: 11:00 PM to 5:00 AM the next calendar day. Order
ascending, spaced at least 20-30 minutes apart. Pre-generate at least
2-3 days ahead. Budget for a hard cap of ~6 uploads/day on free quota —
queue overflow videos to the next available slot rather than failing
silently."
"""
from datetime import datetime, timezone

from engine import daycycle, api_budget, alerts
from engine.supabase_client import get_db


def assign_schedule_for_batch(db, jobs_with_job_ids: list, target_date):
    """`jobs_with_job_ids` is [(job_id, category, part_number), ...] for
    videos just generated for `target_date`. Writes scheduled_at for each,
    inside tonight's posting window, ascending, >= MIN_SLOT_GAP_MINUTES
    apart. If there are more jobs than the day's YouTube quota can afford,
    the overflow is scheduled into the FOLLOWING night's window instead of
    dropped (Section 8's "queue overflow ... to the next available slot").
    """
    max_today = api_budget.max_uploads_today(db)
    tonight = daycycle.build_slot_schedule(min(len(jobs_with_job_ids), max_today) or 0)
    remaining = jobs_with_job_ids[len(tonight):]
    tomorrow_start = daycycle.next_window_start(
        after=daycycle.local_now().replace(hour=23, minute=59) if remaining else None
    )
    overflow = daycycle.build_slot_schedule(len(remaining), start_at=tomorrow_start) if remaining else []

    all_slots = tonight + overflow
    for (job_id, category, part_number), slot in zip(jobs_with_job_ids, all_slots):
        try:
            db.table("videos").update({"scheduled_at": slot.isoformat()}).eq("job_id", job_id).execute()
        except Exception as e:
            print(f"[scheduler] Could not write scheduled_at for {job_id}: {e}")

    if remaining:
        alerts.daily_quota_reached(len(tonight), max_today)
        print(f"[scheduler] {len(remaining)} video(s) queued to the next window — daily quota cap.")
    return {"scheduled_tonight": len(tonight), "queued_overflow": len(remaining)}


def due_for_publish(db, now=None) -> list:
    """Videos whose scheduled_at has passed, status='approved', ordered
    ascending — exactly what publish_queue.py asks for each hourly run."""
    now = now or daycycle.utc_now()
    try:
        rows = (db.table("videos").select("*")
                .eq("status", "approved")
                .lte("scheduled_at", now.isoformat())
                .order("scheduled_at", desc=False)
                .execute().data) or []
        return rows
    except Exception as e:
        print(f"[scheduler] Could not query due videos: {e}")
        return []


# ─── Evergreen fallback substitution (Section 10) ───────────────────────────

CONSECUTIVE_FAILURE_THRESHOLD = 2


def record_generation_failure(db, category: str, part_number, date_str: str) -> int:
    """Increments and returns the consecutive-failure count for this
    category/part slot, persisted so it survives across separate runs
    (a retry an hour later still remembers yesterday's failure)."""
    key = f"consecutive_failures_{category}_{part_number or 'single'}"
    try:
        rows = db.table("settings").select("value").eq("key", key).execute().data or []
        count = int(rows[0]["value"]) + 1 if rows else 1
        if rows:
            db.table("settings").update({"value": str(count)}).eq("key", key).execute()
        else:
            db.table("settings").insert({"key": key, "value": str(count)}).execute()
        return count
    except Exception as e:
        print(f"[scheduler] Could not persist failure count ({e}); assuming 1.")
        return 1


def reset_failure_count(db, category: str, part_number):
    key = f"consecutive_failures_{category}_{part_number or 'single'}"
    try:
        db.table("settings").update({"value": "0"}).eq("key", key).execute()
    except Exception:
        pass


def maybe_substitute_fallback(db, category: str, part_number, date_str: str) -> dict:
    """Called when generation has just failed for this slot. If this is
    the SECOND consecutive failure, substitutes the category's evergreen
    fallback video instead of leaving the slot empty, and alerts. Returns
    {"substituted": bool, "job_id": str|None}."""
    count = record_generation_failure(db, category, part_number, date_str)
    if count < CONSECUTIVE_FAILURE_THRESHOLD:
        return {"substituted": False, "job_id": None}

    try:
        q = db.table("fallback_videos").select("*").eq("category", category)
        q = q.is_("part_number", "null") if part_number is None else q.eq("part_number", part_number)
        rows = q.execute().data or []
        if not rows:
            # Fall back to any generic fallback not tied to a specific category.
            rows = db.table("fallback_videos").select("*").eq("is_generic", True).execute().data or []
        if not rows:
            print(f"[scheduler] No fallback video available for '{category}' — slot stays empty.")
            return {"substituted": False, "job_id": None}

        fb = rows[0]
        job_id = f"{category}_{part_number or 'x'}_{date_str}_fallback"
        db.table("videos").insert({
            "job_id": job_id, "category": category, "part_number": part_number,
            "scheduled_date": date_str, "title": fb["title"], "description": fb.get("description", ""),
            "storage_url": fb["storage_url"], "status": "approved", "review_flag": True,
            "error_log": "Substituted evergreen fallback after 2 consecutive generation failures.",
        }).execute()
        alerts.empty_slot_substituted(category, part_number)
        reset_failure_count(db, category, part_number)
        return {"substituted": True, "job_id": job_id}
    except Exception as e:
        print(f"[scheduler] Fallback substitution failed: {e}")
        return {"substituted": False, "job_id": None}
