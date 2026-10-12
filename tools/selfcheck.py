"""
tools/selfcheck.py — run this FIRST, before your first real generation.
============================================================================
python -m tools.selfcheck

Checks every piece this project depends on, in the order a beginner would
actually set them up, and tells you exactly what's missing instead of
letting the orchestrator fail three steps deep with a confusing error.
Safe to run as many times as you want — it makes no YouTube uploads and
writes nothing except one line to the `settings` table (and removes it).
"""
import os
import shutil
import sys


def _ok(label, detail=""):
    print(f"  OK   {label}{': ' + detail if detail else ''}")


def _fail(label, detail=""):
    print(f"  FAIL {label}{': ' + detail if detail else ''}")
    return False


def check_ffmpeg():
    print("\n[1/7] FFmpeg")
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        _ok("ffmpeg + ffprobe on PATH")
        return True
    return _fail("ffmpeg not found", "Install it — see docs/START_HERE.md step 1")


def check_python_packages():
    print("\n[2/7] Python packages")
    required = ["google.genai", "supabase", "moviepy", "PIL", "numpy", "requests",
               "googleapiclient", "boto3", "dotenv", "sklearn", "kokoro_onnx"]
    all_ok = True
    for mod in required:
        try:
            __import__(mod)
        except ImportError as e:
            all_ok = _fail(f"import {mod}", str(e))
    if all_ok:
        _ok("all required packages import cleanly")
    return all_ok


def check_env_core():
    print("\n[3/7] Core .env values")
    from engine.config import get
    all_ok = True
    for key in ("GEMINI_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_KEY"):
        if get(key):
            _ok(key)
        else:
            all_ok = _fail(key, "missing — see docs/START_HERE.md")
    return all_ok


def check_supabase():
    print("\n[4/7] Supabase connection + schema")
    try:
        from engine.supabase_client import get_db
        db = get_db()
        db.table("settings").select("key").limit(1).execute()
        _ok("Connected to Supabase")
        for table in ("videos", "playlists", "observances_lunar", "review_queue", "fallback_videos"):
            try:
                db.table(table).select("*").limit(1).execute()
                _ok(f"table '{table}' exists")
            except Exception as e:
                _fail(f"table '{table}'", f"did you run supabase/schema.sql? ({e})")
                return False
        return True
    except Exception as e:
        return _fail("Supabase connection", str(e))


def check_gemini():
    print("\n[5/7] Gemini (script generation)")
    try:
        from engine.config import get
        from google import genai
        client = genai.Client(api_key=get("GEMINI_API_KEY"))
        resp = client.models.generate_content(
            model=get("GEMINI_MODEL") or "gemini-2.5-flash", contents="Say the word OK."
        )
        _ok("Gemini responded", resp.text.strip()[:40])
        return True
    except Exception as e:
        return _fail("Gemini call", str(e)[:200])


def check_tts():
    print("\n[6/7] Voice pipeline")
    from engine import google_tts, azure_tts, kokoro_tts
    from engine.config import get
    found_one = False
    if google_tts.available():
        _ok("Google Cloud TTS key present")
        found_one = True
    if azure_tts.available():
        _ok("Azure TTS key present")
        found_one = True
    if kokoro_tts.available():
        _ok("Kokoro (offline) package installed — always-available fallback")
        found_one = True
    else:
        print("       Kokoro not installed — pip install kokoro-onnx soundfile")
    if not found_one:
        return _fail("No TTS engine available", "at minimum, pip install kokoro-onnx soundfile")
    return True


def check_youtube():
    print("\n[7/7] YouTube OAuth (optional at this stage)")
    from engine.config import get
    if not (get("YOUTUBE_CLIENT_ID") and get("YOUTUBE_CLIENT_SECRET") and get("YOUTUBE_REFRESH_TOKEN")):
        print("       Not set up yet — fine for now. Run this once you're ready to publish:")
        print("       python -m engine.publisher --setup")
        return True
    try:
        from engine.publisher import _credentials_from_env
        _credentials_from_env()
        _ok("YouTube token refreshed successfully")
        return True
    except Exception as e:
        return _fail("YouTube token", str(e)[:200])


def main():
    results = [check_ffmpeg(), check_python_packages(), check_env_core(),
              check_supabase(), check_gemini(), check_tts(), check_youtube()]
    print("\n" + "=" * 60)
    if all(results):
        print("All checks passed. You're ready to run:")
        print("  python -m engine.orchestrator --ahead-days 2")
    else:
        print("Some checks failed — fix the FAIL lines above, then run this again.")
    print("=" * 60 + "\n")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
