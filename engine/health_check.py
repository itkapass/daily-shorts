"""
health_check.py — finds the silent failures every morning, before they
cost you a week. Adapted from the reference project's module (same
reasoning: every failure mode here is quiet, so this checks each one on
purpose and alerts only on what's actually broken).

Always exits 0 (the alert is the signal, not the workflow's red X).
"""
import sys
from datetime import datetime, timedelta, timezone

from engine.config import get


def _line(ok, name, detail=""):
    print(f"  {'OK ' if ok else 'FAIL'} {name}{': ' + detail if detail else ''}")
    return {"name": name, "ok": ok, "detail": detail}


def check_database():
    try:
        from engine.supabase_client import get_db
        db = get_db()
        db.table("settings").select("key").limit(1).execute()
        return _line(True, "Database reachable"), db
    except Exception as e:
        return _line(False, "Database reachable", str(e)[:160]), None


def check_recent_activity(db):
    try:
        since = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        rows = db.table("videos").select("id").gte("created_at", since).execute().data or []
        return _line(bool(rows), "Recent generation", f"{len(rows)} video(s) in the last 3 days"
                    + ("" if rows else " — the daily generate workflow may have stopped"))
    except Exception as e:
        return _line(False, "Recent generation", str(e)[:160])

def check_review_queue(db):
    try:
        rows = db.table("review_queue").select("id").eq("status", "pending").execute().data or []
        n = len(rows)
        return _line(n < 20, "Review queue (verification conflicts)", f"{n} pending")
    except Exception as e:
        return _line(False, "Review queue", str(e)[:160])


def check_youtube_auth():
    try:
        from engine.publisher import _credentials_from_env
        _credentials_from_env()
        return _line(True, "YouTube auth", "token refreshed OK")
    except Exception as e:
        return _line(False, "YouTube auth", str(e)[:200])


def check_storage():
    try:
        from engine import storage_r2
        p = storage_r2.check_storage_pressure()
        return _line(not p["should_pause_renders"], "Storage headroom",
                    f"{p['used_mb']:.0f}/{p['limit_mb']} MB ({p['percent']}%) on {p['backend']}")
    except Exception as e:
        return _line(False, "Storage headroom", str(e)[:160])


def check_lunar_festivals(db):
    """Catches the specific failure Section 3 warns against: the lunar
    festival table silently going stale because the yearly refresh never
    ran. Warns (not fails) if the CURRENT year has zero rows."""
    try:
        year = datetime.now(timezone.utc).year
        rows = db.table("observances_lunar").select("id").eq("year", year).execute().data or []
        return _line(bool(rows), "Lunar festival calendar refreshed for this year",
                    f"{len(rows)} row(s) for {year}" + ("" if rows else
                    " — run festival-refresh.yml or add CALENDARIFIC_API_KEY (docs/07)"))
    except Exception as e:
        return _line(False, "Lunar festival calendar", str(e)[:160])


def check_alerting():
    tg = bool(get("TELEGRAM_BOT_TOKEN") and get("TELEGRAM_CHAT_ID"))
    em = bool(get("SMTP_HOST") and get("ALERT_EMAIL_TO"))
    return _line(tg or em, "Alerting configured", f"telegram={'yes' if tg else 'no'}, email={'yes' if em else 'no'}")


def main():
    print("\n" + "=" * 62)
    print(f"HEALTH CHECK — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 62)

    results = []
    db_result, db = check_database()
    results.append(db_result)
    if db:
        results.append(check_recent_activity(db))
        results.append(check_review_queue(db))
        results.append(check_lunar_festivals(db))
    results.append(check_youtube_auth())
    results.append(check_storage())
    results.append(check_alerting())

    failures = [r for r in results if not r["ok"]]
    print("=" * 62)
    print(f"{len(results) - len(failures)}/{len(results)} checks passed.")
    print("=" * 62 + "\n")

    if failures:
        from engine import alerts
        body = "\n".join(f"- {f['name']}: {f['detail']}" for f in failures)
        alerts.alert(f"Health check found {len(failures)} problem(s)", body + "\n\nSee docs/08_TROUBLESHOOTING.md.",
                    severity="critical" if any("auth" in f["name"].lower() or "Database" in f["name"] for f in failures) else "warn")
    return 0


if __name__ == "__main__":
    sys.exit(main())
