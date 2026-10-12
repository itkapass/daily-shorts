"""
storage_r2.py — video file storage, on Cloudflare R2 or Supabase.
=================================================================
Adapted directly from the reference project (same reasoning: R2's free
tier is 10 GB with zero egress fees, vs Supabase Storage's 1 GB — and this
pipeline downloads every video again at publish time, which R2 makes
free). Backend selection is automatic: configure R2 credentials and R2 is
used; leave them unset and it falls back to Supabase Storage, unchanged.
"""
import os
import time

from engine.config import get

BUCKET_DEFAULT = "daily-history-shorts"
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2

R2_FREE_LIMIT_MB = 10 * 1024
SUPABASE_FREE_LIMIT_MB = 1024
PAUSE_RENDERS_ABOVE_PCT = 90


def backend_name() -> str:
    if get("R2_ACCOUNT_ID") and get("R2_ACCESS_KEY_ID") and get("R2_SECRET_ACCESS_KEY"):
        return "r2"
    return "supabase"


def storage_limit_mb() -> int:
    return R2_FREE_LIMIT_MB if backend_name() == "r2" else SUPABASE_FREE_LIMIT_MB


# ── R2 (S3-compatible) ───────────────────────────────────────────────────────

def _r2_client():
    import boto3
    from botocore.config import Config
    account = get("R2_ACCOUNT_ID")
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
        aws_access_key_id=get("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=get("R2_SECRET_ACCESS_KEY"),
        region_name="auto",
        config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
    )


def _r2_public_url(key: str) -> str:
    base = (get("R2_PUBLIC_BASE") or "").rstrip("/")
    if not base:
        raise RuntimeError(
            "R2_PUBLIC_BASE is not set. Cloudflare dashboard -> your bucket -> "
            "Settings -> Public access -> 'R2.dev subdomain' -> Allow, then copy "
            "the https://pub-....r2.dev URL into R2_PUBLIC_BASE. See docs/02."
        )
    return f"{base}/{key}"


def _r2_upload(local_path: str, key: str, bucket: str) -> str:
    client = _r2_client()
    with open(local_path, "rb") as f:
        client.put_object(Bucket=bucket, Key=key, Body=f, ContentType="video/mp4")
    return _r2_public_url(key)


def _r2_delete(key: str, bucket: str) -> bool:
    _r2_client().delete_object(Bucket=bucket, Key=key)
    return True


def _r2_usage_mb(bucket: str) -> float:
    client = _r2_client()
    total, token = 0, None
    while True:
        kwargs = {"Bucket": bucket, "MaxKeys": 1000}
        if token:
            kwargs["ContinuationToken"] = token
        resp = client.list_objects_v2(**kwargs)
        for obj in resp.get("Contents", []):
            total += obj.get("Size", 0)
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
    return total / (1024 * 1024)


# ── Supabase Storage (fallback) ──────────────────────────────────────────────

def _sb_upload(local_path: str, key: str, bucket: str, db) -> str:
    with open(local_path, "rb") as f:
        db.storage.from_(bucket).upload(key, f, file_options={"content-type": "video/mp4", "upsert": "true"})
    return db.storage.from_(bucket).get_public_url(key)


def _sb_delete(key: str, bucket: str, db) -> bool:
    db.storage.from_(bucket).remove([key])
    return True


def _sb_usage_mb(bucket: str, db) -> float:
    total = 0
    for f in db.storage.from_(bucket).list() or []:
        total += (f.get("metadata") or {}).get("size", 0) or 0
    return total / (1024 * 1024)


# ── Public API ───────────────────────────────────────────────────────────────

def upload_video(local_path: str, job_id: str, db=None) -> str:
    from engine.supabase_client import get_db
    db = db or get_db()
    bucket = get("STORAGE_BUCKET", BUCKET_DEFAULT)
    key = f"{job_id}.mp4"
    backend = backend_name()

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            url = _r2_upload(local_path, key, bucket) if backend == "r2" else _sb_upload(local_path, key, bucket, db)
            db.table("videos").update({"storage_url": url, "storage_backend": backend}).eq("job_id", job_id).execute()
            size_mb = os.path.getsize(local_path) / (1024 * 1024)
            print(f"[storage] Uploaded {job_id} ({size_mb:.1f} MB) to {backend} -> {url}")
            return url
        except Exception as e:
            last_error = e
            print(f"[storage] Upload attempt {attempt}/{MAX_RETRIES} failed for {job_id}: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)

    try:
        db.table("videos").update({
            "status": "failed",
            "error_log": f"Storage upload failed after {MAX_RETRIES} attempts: {last_error}",
        }).eq("job_id", job_id).execute()
    except Exception as log_error:
        print(f"[storage] Could not even record the upload failure: {log_error}")
    return None


def delete_video(job_id: str, db=None) -> bool:
    from engine.supabase_client import get_db
    db = db or get_db()
    bucket = get("STORAGE_BUCKET", BUCKET_DEFAULT)
    key = f"{job_id}.mp4"
    backend = backend_name()
    try:
        _r2_delete(key, bucket) if backend == "r2" else _sb_delete(key, bucket, db)
        try:
            db.table("videos").update({"storage_url": None}).eq("job_id", job_id).execute()
        except Exception:
            pass
        print(f"[storage] Freed storage for {job_id}")
        return True
    except Exception as e:
        print(f"[storage] Could not delete {job_id}: {e}")
        return False


def usage_mb() -> float:
    from engine.supabase_client import get_db
    bucket = get("STORAGE_BUCKET", BUCKET_DEFAULT)
    try:
        return _r2_usage_mb(bucket) if backend_name() == "r2" else _sb_usage_mb(bucket, get_db())
    except Exception as e:
        print(f"[storage] Could not measure usage: {e}")
        return 0.0


def check_storage_pressure() -> dict:
    used, limit = usage_mb(), storage_limit_mb()
    pct = (used / limit * 100) if limit else 0
    return {
        "used_mb": round(used, 1), "limit_mb": limit, "percent": round(pct, 1),
        "backend": backend_name(), "should_pause_renders": pct >= PAUSE_RENDERS_ABOVE_PCT,
    }


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Storage utilities")
    p.add_argument("--usage", action="store_true")
    p.add_argument("--upload")
    p.add_argument("--job-id")
    p.add_argument("--delete", action="store_true")
    a = p.parse_args()
    if a.usage:
        print(check_storage_pressure())
    elif a.upload and a.job_id:
        print(upload_video(a.upload, a.job_id))
    elif a.delete and a.job_id:
        print(delete_video(a.job_id))
    else:
        p.print_help()
