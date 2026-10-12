"""
alerts.py — tells you when something needs your attention.
==========================================================
Adapted directly from the reference project's module (see its docstring
for the full reasoning: an unattended pipeline with no alerting is not
automated, it is only unattended). Same two channels, same severity model.

CHANNELS
  Telegram — recommended. Free, arrives on your phone, ~5 minutes to set up.
  Email    — via SMTP (Gmail app password works).
Both optional and independent. With neither configured, alerts just print
to the workflow log.

SEVERITY
  info     — routine, only sent with force=True (daily digest)
  warn     — something will break soon, or a safety cap was hit
  critical — something IS broken right now
"""
import smtplib
import ssl
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.message import EmailMessage

from engine.config import get

SEVERITY_ICON = {"info": "i", "warn": "⚠", "critical": "\U0001f6a8"}


def _telegram_configured():
    return bool(get("TELEGRAM_BOT_TOKEN") and get("TELEGRAM_CHAT_ID"))


def _email_configured():
    return bool(get("SMTP_HOST") and get("SMTP_USER") and get("SMTP_PASSWORD") and get("ALERT_EMAIL_TO"))


def send_telegram(subject: str, body: str, severity: str = "info") -> bool:
    if not _telegram_configured():
        return False
    token, chat_id = get("TELEGRAM_BOT_TOKEN"), get("TELEGRAM_CHAT_ID")
    icon = SEVERITY_ICON.get(severity, "")
    text = f"{icon} *{subject}*\n\n{body}"
    try:
        payload = urllib.parse.urlencode({
            "chat_id": chat_id, "text": text[:4000],
            "parse_mode": "Markdown", "disable_web_page_preview": "true",
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status == 200
    except Exception as e:
        print(f"[alerts] Telegram send failed: {e}")
        return False


def send_email(subject: str, body: str, severity: str = "info") -> bool:
    if not _email_configured():
        return False
    try:
        msg = EmailMessage()
        msg["Subject"] = f"[Daily History Shorts] {SEVERITY_ICON.get(severity, '')} {subject}"
        msg["From"] = get("SMTP_USER")
        msg["To"] = get("ALERT_EMAIL_TO")
        msg.set_content(body)
        host, port = get("SMTP_HOST"), int(get("SMTP_PORT", "587"))
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=20) as s:
                s.login(get("SMTP_USER"), get("SMTP_PASSWORD"))
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=20) as s:
                s.starttls(context=ssl.create_default_context())
                s.login(get("SMTP_USER"), get("SMTP_PASSWORD"))
                s.send_message(msg)
        return True
    except Exception as e:
        print(f"[alerts] Email send failed: {e}")
        return False


def alert(subject: str, body: str, severity: str = "info", force: bool = False) -> dict:
    """Never raises — an alerting system that can crash the thing it
    monitors is worse than no alerting system."""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    full = f"{body}\n\n---\n{stamp}"
    print(f"[alerts] [{severity.upper()}] {subject}\n{body}")
    if severity == "info" and not force:
        return {"telegram": False, "email": False, "logged": True}
    return {
        "telegram": send_telegram(subject, full, severity),
        "email": send_email(subject, full, severity),
        "logged": True,
    }


# ── Prebuilt alerts for this project's known failure modes ──────────────────

def daily_quota_reached(published_today: int, cap: int):
    return alert(
        "Daily upload cap reached",
        f"Published {published_today} of {cap} allowed today.\n\n"
        f"This is the safety cap derived from YouTube's 10,000-unit daily API "
        f"budget (~1,600 units/upload, ~6 uploads/day ceiling per project). "
        f"Overflow videos stay queued and publish automatically once quota "
        f"resets at midnight Pacific. See docs/05.",
        severity="warn",
    )


def youtube_auth_broken(detail: str):
    return alert(
        "YouTube publishing is BROKEN",
        f"Publishing has stopped and will not resume on its own.\n\n{detail}\n\n"
        f"Most likely cause: the OAuth refresh token expired. If your Google "
        f"Cloud consent screen is still in 'Testing' status, Google kills "
        f"refresh tokens after 7 days — set it to 'In production' (docs/04).",
        severity="critical",
    )


def playlist_setup_failed(category: str, part_number, detail: str):
    label = category if part_number is None else f"{category} part {part_number}"
    return alert(
        f"Could not set up the '{label}' playlist",
        f"{detail}\n\nThe video itself may still have uploaded — only the "
        f"auto playlist create/insert step failed. Check the OAuth scope "
        f"includes https://www.googleapis.com/auth/youtube (not just "
        f".youtube.upload) — see docs/04.",
        severity="warn",
    )


def storage_pressure(used_mb: float, limit_mb: float):
    pct = (used_mb / limit_mb * 100) if limit_mb else 0
    return alert(
        "Storage is filling up",
        f"Using {used_mb:.0f} MB of {limit_mb:.0f} MB ({pct:.0f}%). Rendering "
        f"pauses automatically at 90%. Published/rejected videos should be "
        f"deleted automatically after upload — if usage keeps climbing, "
        f"check recent runs for upload failures that skipped cleanup.",
        severity="warn",
    )


def generation_failed(failed: int, attempted: int, errors: list):
    sample = "\n".join(f"- {e}" for e in errors[:5])
    return alert(
        f"Video generation failing ({failed}/{attempted} failed)",
        f"Today's batch had {failed} failures out of {attempted} attempts.\n\n{sample}",
        severity="critical" if failed == attempted else "warn",
    )


def empty_slot_substituted(category: str, part_number):
    label = category if part_number is None else f"{category} part {part_number}"
    return alert(
        f"Used the evergreen fallback for '{label}'",
        "Same-day generation failed twice in a row for this slot, so the "
        "scheduler substituted the evergreen fallback video instead of "
        "leaving the slot empty. Worth checking why generation failed "
        "(see the most recent workflow run log).",
        severity="warn",
    )


def daily_digest(summary: dict):
    lines = [
        f"Generated:  {summary.get('generated', 0)}",
        f"Published:  {summary.get('published', 0)}",
        f"Pending review: {summary.get('pending', 0)}",
        f"Rejected by quality gates: {summary.get('gate_rejected', 0)}",
        f"Routed to review (source disagreement): {summary.get('review_flagged', 0)}",
        f"Storage used: {summary.get('storage_mb', 0):.0f} MB",
    ]
    return alert("Daily digest", "\n".join(lines), severity="info", force=True)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Test your alert setup")
    p.add_argument("--test", action="store_true")
    args = p.parse_args()
    if not args.test:
        p.print_help()
        raise SystemExit(0)

    tg, em = _telegram_configured(), _email_configured()
    print(f"  Telegram: {'configured' if tg else 'NOT configured'}")
    print(f"  Email:    {'configured' if em else 'NOT configured'}")
    if not (tg or em):
        print("\n  Neither is set up yet — that's fine, alerts are optional. See docs/START_HERE.md.")
        raise SystemExit(0)

    result = alert("Test alert", "If you are reading this, your alerts are working.", severity="warn")
    sent = [k for k, v in result.items() if v and k != "logged"]
    if sent:
        print(f"  Sent via: {', '.join(sent)}")
        raise SystemExit(0)
    print("  Sending FAILED — double check the token/chat id or SMTP credentials.")
    raise SystemExit(1)
