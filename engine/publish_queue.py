"""
publish_queue.py — uploads due, approved videos to YouTube.
============================================================================
Run with:  python -m engine.publish_queue
Called hourly by .github/workflows/publish.yml. Only uploads videos whose
scheduled_at has passed (engine.scheduler.due_for_publish), ascending, so
Section 5's ordering/spacing is honoured even though this runs far more
often than it actually uploads.
"""
from datetime import datetime, timezone

from engine import api_budget, alerts, publisher, scheduler, storage_r2
from engine.config import get
from engine.supabase_client import get_db

DOWNLOAD_RETRY_ATTEMPTS = 3


def _download_to_local(storage_url: str, job_id: str) -> str:
    import os
    import requests
    local_path = os.path.join(get("OUTPUT_DIR", "output"), f"{job_id}_download.mp4")
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    resp = requests.get(storage_url, timeout=120, stream=True)
    resp.raise_for_status()
    with open(local_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1024 * 1024):
            f.write(chunk)
    return local_path


def publish_due_videos() -> dict:
    db = get_db()
    due = scheduler.due_for_publish(db)
    if not due:
        print("[publish_queue] Nothing due right now.")
        return {"published": 0, "skipped": 0, "failed": 0}

    yb = api_budget.youtube_budget(db)
    yb.load()

    published, failed = 0, 0
    for row in due:
        job_id = row["job_id"]
        per_video_units = (api_budget.YOUTUBE_UPLOAD_COST + api_budget.YOUTUBE_THUMBNAIL_COST
                           + 2 * api_budget.YOUTUBE_PLAYLIST_CALL_COST)
        if not yb.can_afford(per_video_units):
            alerts.daily_quota_reached(published, get("MAX_UPLOADS_PER_DAY", "6"))
            print("[publish_queue] Daily YouTube quota exhausted — remaining videos stay queued for tomorrow.")
            break

        try:
            local_path = _download_to_local(row["storage_url"], job_id)
            result = publisher.upload_video(
                local_path, row["title"], row.get("description", ""), row.get("hashtags") or [],
                category=row["category"], part_number=row.get("part_number"),
                captions_srt=row.get("srt_content"), db=db,
            )
            yb.spend(per_video_units)

            db.table("videos").update({
                "status": "published", "youtube_id": result["video_id"], "youtube_url": result["url"],
                "published_at": datetime.now(timezone.utc).isoformat(),
            }).eq("job_id", job_id).execute()

            storage_r2.delete_video(job_id, db=db)
            try:
                import os
                os.remove(local_path)
            except OSError:
                pass

            published += 1
            print(f"[publish_queue] Published {job_id} -> {result['url']}")

        except Exception as e:
            failed += 1
            msg = str(e)
            print(f"[publish_queue] Failed to publish {job_id}: {msg}")
            try:
                db.table("videos").update({"error_log": msg[:2000]}).eq("job_id", job_id).execute()
            except Exception:
                pass
            if "invalid_grant" in msg.lower() or "refresh token" in msg.lower():
                alerts.youtube_auth_broken(msg)
                break  # auth is broken for every remaining video too — stop this run

    return {"published": published, "skipped": len(due) - published - failed, "failed": failed}


if __name__ == "__main__":
    result = publish_due_videos()
    print(f"[publish_queue] Done: {result}")
