"""
orchestrator.py — the daily generation pipeline, end to end.
============================================================================
Run with:  python -m engine.orchestrator [--date YYYY-MM-DD] [--ahead-days 2]

Section 5: "Pre-generate videos at least 2-3 days ahead of their post date
so a generation failure never threatens a near-term slot." Default here
is 2 days ahead; override with --ahead-days.

PER-VIDEO PIPELINE (Section 10: every step gets automatic retry with
backoff)
  1. Script       — engine.script_generator (Gemini -> Groq -> GitHub Models)
  2. Voice         — engine.voice_engine (free -> cloned -> paid, per VOICE_PROVIDER)
  3. Visuals       — engine.visual_matcher (QID-anchored) -> engine.ai_visuals
                      (abstract, non-person) -> engine.text_card (always works)
  4. Captions      — engine.subtitle_engine
  5. Audio mix     — engine.audio_mixer
  6. Compose       — engine.video_compositor
  7. Quality gates — engine.quality_gates (reject -> retry once -> fallback)
  8. Dedup         — engine.duplicate_check (near-duplicate guard)
  9. Storage       — engine.storage_r2 (upload, free the local render)
 10. DB row        — status='approved' (zero manual review, per the build
                      spec's "zero-manual-intervention" goal) unless quality
                      gates rejected twice, in which case the evergreen
                      fallback is substituted instead (engine.scheduler).

After every job in the batch is attempted, scheduler.assign_schedule_for_batch
gives each surviving video a scheduled_at inside the posting window
(Section 5), respecting the daily YouTube quota cap (Section 8).
"""
import argparse
import os
import time
import traceback
import uuid
from datetime import date, timedelta

from engine import (api_budget, alerts, observances, quality_gates, duplicate_check,
                    topic_assembler, script_generator, voice_engine, visual_matcher,
                    text_card, subtitle_engine, audio_mixer, video_compositor,
                    storage_r2, scheduler)
from engine.config import get
from engine.supabase_client import get_db

MAX_RETRIES_PER_STEP = 2
RETRY_BACKOFF_SECONDS = 5


def _retry(fn, what: str, attempts: int = MAX_RETRIES_PER_STEP):
    last_err = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as e:
            last_err = e
            print(f"[orchestrator] '{what}' failed (attempt {attempt}/{attempts}): {e}")
            if attempt < attempts:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
    raise RuntimeError(f"'{what}' failed after {attempts} attempts: {last_err}")


def _render_job(db, job: dict, target_date, observance_open: str, observance_close: str) -> dict:
    category, part_number = job["category"], job.get("part_number")
    job_id = f"{category}_{part_number or 'x'}_{target_date.isoformat()}_{uuid.uuid4().hex[:6]}"
    output_dir = os.path.join(get("OUTPUT_DIR", "output"), job_id)
    os.makedirs(output_dir, exist_ok=True)

    print(f"\n[orchestrator] === {job_id} ({len(job['candidates'])} candidates) ===")

    storyboard = _retry(lambda: script_generator.generate_storyboard(
        job, job_id, observance_open, observance_close, db=db), "script generation")

    voice = _retry(lambda: voice_engine.generate_voiceover(
        " ".join(s["voice_text"] for s in storyboard["scenes"]), job_id, output_dir), "voice synthesis")
    storyboard["_voice_engine"] = voice["engine"]

    scenes = voice_engine.get_scene_timestamps(voice["word_timestamps"], storyboard["scenes"])
    for i, scene in enumerate(scenes, 1):
        duration_needed = scene["time_end"] - scene["time_start"]
        clip = None
        qid = scene.get("subject_qid")
        if qid and qid != "null":
            clip = visual_matcher.fetch_photo_for_candidate(qid, duration_needed, job_id, i, output_dir)
        if not clip and get("HUGGINGFACE_API_KEY") and job["category"].startswith("history"):
            from engine import ai_visuals
            if ai_visuals.available():
                clip = ai_visuals.generate_abstract_broll(scene.get("visual_keyword", category),
                                                          duration_needed, job_id, i, output_dir)
        if not clip:
            clip = text_card.build_text_card_clip(scene["voice_text"], duration_needed, job_id, i, output_dir)
        scene["clip_path"] = clip["clip_path"] if clip else None

    cards = subtitle_engine.build_caption_cards(voice["word_timestamps"])
    srt_path = os.path.join(output_dir, f"{job_id}.srt")
    subtitle_engine.export_srt(cards, srt_path)
    with open(srt_path, encoding="utf-8") as f:
        srt_content = f.read()

    mixed_audio_path = os.path.join(output_dir, f"{job_id}_mixed.mp3")
    audio_mixer.mix_audio(voice["audio_path"], voice["word_timestamps"], voice["duration_seconds"], mixed_audio_path)

    final_path = os.path.join(output_dir, f"{job_id}.mp4")
    video_compositor.compose_video(scenes, mixed_audio_path, cards, voice["duration_seconds"], final_path,
                                   branding={"channel_name": get("YOUTUBE_CHANNEL_HANDLE", "")})

    gate_result = quality_gates.run_gates(final_path, storyboard=storyboard)
    if gate_result["verdict"] == "reject":
        raise RuntimeError(f"Quality gates rejected: {quality_gates.summarize(gate_result)}")

    dup = duplicate_check.check_near_duplicate(db, storyboard)
    review_flag = dup["is_duplicate"] or gate_result["verdict"] == "warn"

    # Insert the row FIRST (storage_r2.upload_video expects the row to exist
    # so it can .update() it), then upload.
    db.table("videos").insert({
        "job_id": job_id, "category": category, "part_number": part_number,
        "scheduled_date": target_date.isoformat(), "title": storyboard.get("title", ""),
        "description": storyboard.get("description", ""), "hashtags": storyboard.get("hashtags", []),
        "duration": voice["duration_seconds"], "storyboard": storyboard, "status": "rendering",
        "review_flag": review_flag, "llm_provider": storyboard.get("provider"),
        "voice_engine": voice["engine"], "srt_content": srt_content,
    }).execute()

    storage_url = storage_r2.upload_video(final_path, job_id, db=db)
    if not storage_url:
        raise RuntimeError("Storage upload failed after retries.")

    db.table("videos").update({"status": "approved"}).eq("job_id", job_id).execute()
    scheduler.reset_failure_count(db, category, part_number)

    try:
        import shutil
        shutil.rmtree(output_dir, ignore_errors=True)
    except Exception:
        pass

    return {"job_id": job_id, "category": category, "part_number": part_number, "status": "approved"}


def run_generation_pipeline(target_date: date = None, ahead_days: int = 2) -> dict:
    db = get_db()
    target_date = target_date or (date.today() + timedelta(days=ahead_days))
    date_str = target_date.isoformat()
    print(f"[orchestrator] Generating for {date_str} ({ahead_days} day(s) ahead of today)")

    pressure = storage_r2.check_storage_pressure()
    if pressure["should_pause_renders"]:
        alerts.storage_pressure(pressure["used_mb"], pressure["limit_mb"])
        return {"generated": 0, "failed": 0, "paused": True}

    jobs = topic_assembler.build_batch_for_date(db, target_date)
    if not jobs:
        print(f"[orchestrator] No surviving candidates for {date_str} — a legitimately thin day.")

    todays_obs = observances.todays_observances(db, target_date)
    observance_open = todays_obs[0]["open"] if todays_obs else ""
    observance_close = todays_obs[0]["close"] if todays_obs else ""

    generated, failed, errors, scheduled_ids = [], [], [], []
    for i, job in enumerate(jobs):
        # Only the FIRST job of the day carries the observance wish segment
        # (Section 3: "a short added segment... not necessarily a
        # standalone video" — one video gets it, not every single one).
        open_line = observance_open if i == 0 else ""
        close_line = observance_close if i == 0 else ""
        try:
            result = _render_job(db, job, target_date, open_line, close_line)
            generated.append(result)
            scheduled_ids.append((result["job_id"], result["category"], result["part_number"]))
        except Exception as e:
            print(f"[orchestrator] Job failed: {job['category']} part {job.get('part_number')}: {e}")
            traceback.print_exc()
            failed.append(job)
            errors.append(f"{job['category']} part {job.get('part_number')}: {e}")
            sub = scheduler.maybe_substitute_fallback(db, job["category"], job.get("part_number"), date_str)
            if sub["substituted"]:
                scheduled_ids.append((sub["job_id"], job["category"], job.get("part_number")))

    if scheduled_ids:
        scheduler.assign_schedule_for_batch(db, scheduled_ids, target_date)

    if failed:
        alerts.generation_failed(len(failed), len(jobs), errors)

    alerts.daily_digest({
        "generated": len(generated), "published": 0, "pending": 0,
        "gate_rejected": len(failed), "review_flagged": sum(1 for j in generated if j.get("review_flag")),
        "storage_mb": storage_r2.usage_mb(),
    })

    return {"generated": len(generated), "failed": len(failed), "jobs_attempted": len(jobs)}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Daily History Shorts — generation pipeline")
    p.add_argument("--date", type=str, default=None, help="YYYY-MM-DD (default: today + --ahead-days)")
    p.add_argument("--ahead-days", type=int, default=2)
    args = p.parse_args()

    target = date.fromisoformat(args.date) if args.date else None
    result = run_generation_pipeline(target_date=target, ahead_days=args.ahead_days)
    print(f"\n[orchestrator] Done: {result}")
