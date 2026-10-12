"""
quality_gates.py — automated QC on the rendered file, before it's queued
for publish. Adapted from the reference project's gates (black frames,
audio silence/level, duration, resolution, frozen video) plus two checks
specific to this build:
  - closing_cta: Section 7 requires the LAST scene to end on a question /
    follow / tease — this is the mechanical back-check that the model
    actually complied, not just that the prompt asked nicely.
  - runtime_target: Section 2's ~45-60s target is a SOFT warn here (not a
    hard reject) since a thin day legitimately produces a shorter video.
"""
import json
import os
import subprocess

import numpy as np

BLACK_FRAME_MAX_RUN_SECONDS = 0.5
BLACK_LUMA_THRESHOLD = 12
MIN_MEAN_VOLUME_DB = -35.0
MAX_MEAN_VOLUME_DB = -12.0
MIN_DURATION_SECONDS = 12.0
MAX_DURATION_SECONDS = 175.0
TARGET_MIN_SECONDS, TARGET_MAX_SECONDS = 40.0, 65.0
EXPECTED_SIZE = (1080, 1920)
SAMPLE_FPS = 4


def _ffprobe_json(path: str) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
        capture_output=True, text=True, timeout=120,
    )
    if out.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {out.stderr.strip()[:300]}")
    return json.loads(out.stdout)


def _mean_volume_db(path: str):
    out = subprocess.run(["ffmpeg", "-i", path, "-af", "volumedetect", "-f", "null", "-"],
                        capture_output=True, text=True, timeout=180)
    mean = peak = None
    for line in out.stderr.splitlines():
        if "mean_volume:" in line:
            mean = float(line.split("mean_volume:")[1].strip().split()[0])
        elif "max_volume:" in line:
            peak = float(line.split("max_volume:")[1].strip().split()[0])
    return mean, peak


def _sample_luma(path: str, fps: int = SAMPLE_FPS):
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-vf", f"fps={fps},scale=32:32",
         "-pix_fmt", "gray", "-f", "rawvideo", "-"],
        capture_output=True, timeout=240,
    )
    raw = proc.stdout
    frame_size = 32 * 32
    n = len(raw) // frame_size
    if n == 0:
        return []
    arr = np.frombuffer(raw[: n * frame_size], dtype=np.uint8).reshape(n, frame_size)
    return arr.mean(axis=1).tolist()


def run_gates(video_path: str, storyboard: dict = None, expect_audio: bool = True) -> dict:
    result = {"verdict": "pass", "checks": [], "failures": [], "warnings": []}

    def add(name, ok, level, detail=""):
        result["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
        (result["failures"] if (not ok and level == "reject") else
         result["warnings"] if not ok else result["checks"]).__class__  # no-op, keep list typing happy
        if not ok:
            (result["failures"] if level == "reject" else result["warnings"]).append(f"{name}: {detail}")

    if not os.path.exists(video_path):
        result["verdict"] = "reject"
        result["failures"].append("file_missing: rendered file does not exist")
        return result

    try:
        meta = _ffprobe_json(video_path)
    except Exception as e:
        result["verdict"] = "warn"
        result["warnings"].append(f"probe_failed: {e}")
        return result

    vstream = next((s for s in meta.get("streams", []) if s.get("codec_type") == "video"), None)
    astream = next((s for s in meta.get("streams", []) if s.get("codec_type") == "audio"), None)
    duration = float(meta.get("format", {}).get("duration") or 0)

    add("duration", MIN_DURATION_SECONDS <= duration <= MAX_DURATION_SECONDS, "reject",
        f"{duration:.1f}s (hard limits {MIN_DURATION_SECONDS:.0f}-{MAX_DURATION_SECONDS:.0f}s)")
    add("runtime_target", TARGET_MIN_SECONDS <= duration <= TARGET_MAX_SECONDS, "warn",
        f"{duration:.1f}s (Section 2 target ~45-60s) — not a reject, a thin/big day can legitimately differ")

    if vstream:
        size = (int(vstream.get("width", 0)), int(vstream.get("height", 0)))
        add("resolution", size == EXPECTED_SIZE, "warn", f"{size[0]}x{size[1]}, expected 1080x1920")
    else:
        add("video_stream", False, "reject", "no video stream found")

    if expect_audio:
        add("audio_stream", astream is not None, "reject", "no audio stream — narration did not render")

    if astream:
        try:
            mean_db, _ = _mean_volume_db(video_path)
            if mean_db is None:
                add("audio_level", False, "warn", "could not measure volume")
            else:
                add("audio_level", MIN_MEAN_VOLUME_DB <= mean_db <= MAX_MEAN_VOLUME_DB, "warn",
                    f"mean {mean_db:.1f} dB")
                add("audio_silence", mean_db > -60.0, "reject", f"effectively silent ({mean_db:.1f} dB)")
        except Exception as e:
            add("audio_level", False, "warn", f"check failed: {e}")

    try:
        luma = _sample_luma(video_path)
        if luma:
            max_run, run = 0, 0
            for v in luma:
                run = run + 1 if v < BLACK_LUMA_THRESHOLD else 0
                max_run = max(max_run, run)
            black_seconds = max_run / SAMPLE_FPS
            add("black_frames", black_seconds <= BLACK_FRAME_MAX_RUN_SECONDS, "reject",
                f"{black_seconds:.1f}s of solid black")
            spread = float(np.std(luma))
            add("frozen_video", spread > 0.35, "warn", f"brightness barely changes (sigma={spread:.2f})")
        else:
            add("black_frames", False, "warn", "could not sample frames")
    except Exception as e:
        add("black_frames", False, "warn", f"check failed: {e}")

    if storyboard:
        scenes = storyboard.get("scenes") or []
        longest = max((len(s.get("voice_text", "")) for s in scenes), default=0)
        add("caption_length", longest <= 240, "warn", f"longest scene is {longest} characters")

        voice_engine_used = storyboard.get("_voice_engine")
        if voice_engine_used and voice_engine_used not in ("google_tts",):
            add("caption_timing", False, "warn",
                f"voiced by '{voice_engine_used}', not an exact-timing engine — captions may drift slightly")

        if scenes:
            last_text = (scenes[-1].get("voice_text") or "").strip().lower()
            cta_markers = ("?", "follow", "subscribe", "comment", "share", "part 2", "next time", "miss it")
            add("closing_cta", any(m in last_text for m in cta_markers), "warn",
                "final scene doesn't end with a question/follow/share/part-2 line (Section 7)")

    if result["failures"]:
        result["verdict"] = "reject"
    elif result["warnings"]:
        result["verdict"] = "warn"
    return result


def summarize(result: dict) -> str:
    if result["verdict"] == "pass":
        return "All quality checks passed."
    parts = []
    if result["failures"]:
        parts.append("Rejected: " + "; ".join(result["failures"]))
    if result["warnings"]:
        parts.append("Warnings: " + "; ".join(result["warnings"]))
    return " | ".join(parts)
