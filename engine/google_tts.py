"""
google_tts.py — free tier #1 (Section 6): Google Cloud TTS Neural2/Chirp.
============================================================================
Uses the plain REST endpoint with an API key (texttospeech.googleapis.com),
NOT the google-cloud-texttospeech client library, specifically so setup is
"paste one API key" rather than "create and download a service-account
JSON" — much friendlier for a beginner (see docs/03).

EXACT WORD TIMING VIA SSML <mark> TAGS
Cloud TTS supports `enableTimePointing: ["SSML_MARK"]`: wrap every word in
an SSML <mark name="w0"/> and the response includes a timepoints array
mapping each mark to the exact second it was reached in the audio — the
same "ground truth from the synthesiser" idea the reference project's
edge-tts integration relies on, just via marks instead of WordBoundary
events. Falls back to proportional estimation only if the free tier's
quota is hit or the call fails for any other reason.
"""
import base64
import html
import re
import subprocess

import requests

from engine.config import get

ENDPOINT = "https://texttospeech.googleapis.com/v1/text:synthesize"
TIMEOUT_SECONDS = 30

# One fixed persona voice (Section 7). Neural2 voices are on the free tier
# (first 1M characters/month). Defaults to an Indian-English voice since
# this channel's audience (Asia/Kolkata posting window, India-specific
# categories) is India-first — a US/UK accent at a measured TTS pace reads
# as noticeably "foreign AI voice" to that audience and hurts retention.
# VERIFY this exact voice name is still current before relying on it —
# Google occasionally renames/retires specific Neural2 names; the full
# current list is at https://cloud.google.com/text-to-speech/docs/voices
# (filter language = "Indian English"). Override either value with
# GOOGLE_TTS_VOICE_NAME / GOOGLE_TTS_LANGUAGE_CODE in .env without touching
# this file if you want a different voice (e.g. a Chirp3-HD en-IN name).
HOST_VOICE_NAME = get("GOOGLE_TTS_VOICE_NAME", "en-IN-Neural2-B")
HOST_LANGUAGE_CODE = get("GOOGLE_TTS_LANGUAGE_CODE", "en-IN")


def available() -> bool:
    return bool(get("GOOGLE_TTS_API_KEY"))


def _build_ssml(text: str) -> tuple:
    words = text.split()
    parts = []
    for i, w in enumerate(words):
        parts.append(f'<mark name="w{i}"/>{html.escape(w)}')
    return f"<speak>{' '.join(parts)}</speak>", words


def synthesize(text: str, output_path: str) -> dict:
    api_key = get("GOOGLE_TTS_API_KEY")
    if not api_key:
        return None
    ssml, words = _build_ssml(text)
    try:
        resp = requests.post(
            ENDPOINT, params={"key": api_key},
            json={
                "input": {"ssml": ssml},
                "voice": {"languageCode": HOST_LANGUAGE_CODE, "name": HOST_VOICE_NAME},
                "audioConfig": {"audioEncoding": "LINEAR16"},
                "enableTimePointing": ["SSML_MARK"],
            },
            timeout=TIMEOUT_SECONDS,
        )
        if resp.status_code == 429 or "RESOURCE_EXHAUSTED" in resp.text:
            print("[google_tts] Free-tier quota exhausted for today.")
            return None
        resp.raise_for_status()
        data = resp.json()

        wav_path = output_path.replace(".mp3", ".wav")
        with open(wav_path, "wb") as f:
            f.write(base64.b64decode(data["audioContent"]))
        subprocess.run(
            ["ffmpeg", "-y", "-i", wav_path, "-codec:a", "libmp3lame", "-q:a", "2", output_path],
            check=True, capture_output=True, timeout=120,
        )
        duration = _probe_duration(output_path)

        timepoints = {tp["markName"]: tp["timeSeconds"] for tp in data.get("timepoints", [])}
        word_timestamps = []
        for i, w in enumerate(words):
            start = timepoints.get(f"w{i}")
            end = timepoints.get(f"w{i + 1}", duration)
            if start is None:
                continue
            word_timestamps.append({"word": w.strip(".,!?;:\"'"), "start": round(start, 3), "end": round(end, 3)})

        import os
        os.remove(wav_path)
        print(f"[google_tts] Synthesized {duration:.1f}s, {len(word_timestamps)} exact word timings")
        return {"duration_seconds": duration, "word_timestamps": word_timestamps, "engine": "google_tts"}
    except Exception as e:
        print(f"[google_tts] Synthesis failed ({e}).")
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
