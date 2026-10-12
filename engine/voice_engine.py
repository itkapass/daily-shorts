"""
voice_engine.py — the VOICE_PROVIDER dispatcher (Section 6).
============================================================================
"Build a voice abstraction layer with a single config flag
(VOICE_PROVIDER=free|cloned|paid) so switching providers later requires
zero code changes and zero manual steps — just an env var + API key."

TIER "free" (ship first):
    Google Cloud TTS -> Azure TTS -> Kokoro (offline) -> gTTS (last resort)
TIER "cloned" (self-hosted XTTS, zero cost, more setup):
    XTTS clone -> falls through to the SAME "free" chain above on failure
TIER "paid" (ElevenLabs, OFF unless explicitly selected):
    ElevenLabs -> falls through to the SAME "free" chain above on failure

Falling through to "free" on failure (rather than hard-failing) is a
deliberate design choice beyond what the spec requires: it means a
misconfigured paid/cloned tier degrades to a working video instead of a
failed one, and engine/quality_gates.py's caption_timing check already
flags whenever a fallback engine without exact timing was used, so this
is never a SILENT quality drop — it is visible in the review queue.
"""
import json
import os
import re
import shutil
import subprocess

from engine.config import get

_VOWEL_GROUPS = re.compile(r"[aeiouy]+", re.I)


def _require_ffmpeg():
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "ffmpeg was not found on your PATH. Install it (see docs/START_HERE.md) "
            "or run this pipeline on GitHub Actions, which already has it."
        )


def _syllables(word: str) -> int:
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 1
    n = len(_VOWEL_GROUPS.findall(w))
    if w.endswith("e") and n > 1:
        n -= 1
    return max(n, 1)


def estimate_word_timings(text: str, total_duration: float) -> list:
    words = text.split()
    if not words or total_duration <= 0:
        return []
    weights = [_syllables(w) + (0.6 if re.search(r"[.,!?;:]$", w) else 0) for w in words]
    total_w = sum(weights) or 1
    out, t = [], 0.0
    for w, weight in zip(words, weights):
        span = total_duration * (weight / total_w)
        out.append({"word": w.strip(".,!?;:\"'"), "start": round(t, 3), "end": round(t + span * 0.92, 3)})
        t += span
    return out


def _try_gtts(text, output_path):
    try:
        from gtts import gTTS
        # tld="co.in" picks the Indian-accented Google Translate voice
        # instead of the US-accented default (tld="com") — free, zero
        # setup, and the one easy win available even at this last-resort
        # tier. Override with GTTS_TLD in .env if this channel ever isn't
        # India-first.
        tld = get("GTTS_TLD", "co.in")
        gTTS(text=text, lang="en", tld=tld, slow=False).save(output_path)
        duration = _probe_duration(output_path)
        print(f"[voice_engine] gTTS fallback (tld={tld}), {duration:.1f}s (timings estimated)")
        return {"duration_seconds": duration}
    except Exception as e:
        print(f"[voice_engine] gTTS failed ({e}).")
        return None


def _probe_duration(path: str) -> float:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=60,
        )
        return float(out.stdout.strip())
    except Exception:
        return 0.0


def _free_chain(text, output_path):
    from engine import google_tts, azure_tts, kokoro_tts
    if google_tts.available():
        r = google_tts.synthesize(text, output_path)
        if r:
            return r, "google_tts"
    if azure_tts.available():
        r = azure_tts.synthesize(text, output_path)
        if r:
            return r, "azure_tts"
    if kokoro_tts.available():
        r = kokoro_tts.synthesize(text, output_path)
        if r:
            return r, "kokoro"
    r = _try_gtts(text, output_path)
    if r:
        try:
            from engine import alerts
            alerts.alert(
                "A video used the last-resort gTTS voice",
                "Google Cloud TTS, Azure TTS and Kokoro all failed or are unconfigured, "
                "so this video's narration used gTTS. Check your free-tier TTS setup "
                "(docs/03) — this should be rare.",
                severity="warn",
            )
        except Exception:
            pass
        return r, "gtts"
    return None, None


def generate_voiceover(full_script: str, job_id: str, output_dir: str = None) -> dict:
    """Returns {"audio_path", "duration_seconds", "word_timestamps", "engine"}."""
    output_dir = output_dir or get("OUTPUT_DIR", "output")
    _require_ffmpeg()
    os.makedirs(output_dir, exist_ok=True)
    audio_path = os.path.join(output_dir, f"{job_id}_voice.mp3")

    provider = get("VOICE_PROVIDER", "free").strip().lower()
    result, engine_used = None, None

    if provider == "cloned":
        from engine import xtts_clone
        if xtts_clone.available():
            result = xtts_clone.synthesize(full_script, audio_path)
            engine_used = "xtts_clone"
    elif provider == "paid":
        from engine import elevenlabs_tts
        if elevenlabs_tts.available():
            result = elevenlabs_tts.synthesize(full_script, audio_path)
            engine_used = "elevenlabs"

    if result is None:
        result, engine_used = _free_chain(full_script, audio_path)

    if result is None:
        raise RuntimeError(
            "Every TTS engine failed. Set up at least one free-tier provider "
            "(Google Cloud TTS or Azure) or let Kokoro download its offline model — "
            "see docs/03_FREE_LLM_AND_TTS_KEYS.md."
        )

    duration = result.get("duration_seconds") or _probe_duration(audio_path)
    word_timestamps = result.get("word_timestamps") or estimate_word_timings(full_script, duration)

    ts_path = os.path.join(output_dir, f"{job_id}_timestamps.json")
    with open(ts_path, "w", encoding="utf-8") as f:
        json.dump(word_timestamps, f, indent=2, ensure_ascii=False)

    print(f"[voice_engine] {len(word_timestamps)} words, {duration:.1f}s total (engine={engine_used})")
    return {"audio_path": audio_path, "duration_seconds": round(duration, 2),
            "word_timestamps": word_timestamps, "engine": engine_used}


def get_scene_timestamps(word_timestamps: list, scenes: list) -> list:
    """Assigns each scene a start/end time on the global timeline from a
    straight cumulative word count, then forces perfect contiguity so no
    instant of the timeline is uncovered by a background clip (adapted
    from the reference project's fix for the exact same black-frame bug)."""
    if not word_timestamps or not scenes:
        return scenes
    total = len(word_timestamps)
    out, cursor = [], 0
    for scene in scenes:
        count = len(str(scene.get("voice_text", "")).split())
        start_i = min(cursor, total - 1)
        end_i = min(cursor + max(count - 1, 0), total - 1)
        out.append({**scene, "time_start": word_timestamps[start_i]["start"],
                    "time_end": word_timestamps[end_i]["end"], "_words": word_timestamps[start_i:end_i + 1]})
        cursor += count
    for i in range(len(out) - 1):
        out[i]["time_end"] = out[i + 1]["time_start"]
    if out:
        out[0]["time_start"] = 0.0
        out[-1]["time_end"] = max(out[-1]["time_end"], word_timestamps[-1]["end"])
    return out
