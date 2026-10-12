"""
azure_tts.py — free tier #2 (Section 6): Azure Neural TTS, tried if
Google Cloud TTS's free tier is exhausted for the day.

Plain REST call (no SDK) — simpler to install, same free allowance
(~500K chars/month). No word-boundary events on this path; timing is
estimated the same way Piper/gTTS are in the reference project (see
voice_engine.estimate_word_timings) — accurate to roughly 80ms/word,
fine for burned-in captions.
"""
import re
import subprocess

import requests

from engine.config import get

# One fixed persona voice (Section 7). Defaults to an Indian-English Neural
# voice — this channel's audience (Asia/Kolkata posting window, India-
# specific categories) is India-first, and a US-accented voice at a
# measured TTS pace reads as a "foreign AI voice" to that audience and
# hurts retention. en-IN-PrabhatNeural (male) is confirmed current as of
# this writing; en-IN-NeerjaNeural is the equivalent female voice if you'd
# rather have that persona. Override via AZURE_TTS_VOICE_NAME /
# AZURE_TTS_LANGUAGE_CODE in .env without touching this file.
HOST_VOICE_NAME = get("AZURE_TTS_VOICE_NAME", "en-IN-PrabhatNeural")
HOST_LANGUAGE_CODE = get("AZURE_TTS_LANGUAGE_CODE", "en-IN")


def available() -> bool:
    return bool(get("AZURE_TTS_KEY") and get("AZURE_TTS_REGION"))


def synthesize(text: str, output_path: str) -> dict:
    key, region = get("AZURE_TTS_KEY"), get("AZURE_TTS_REGION")
    if not (key and region):
        return None
    ssml = (
        f'<speak version="1.0" xml:lang="{HOST_LANGUAGE_CODE}">'
        f'<voice name="{HOST_VOICE_NAME}">{_escape(text)}</voice></speak>'
    )
    try:
        resp = requests.post(
            f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
            headers={
                "Ocp-Apim-Subscription-Key": key,
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": "audio-16khz-128kbitrate-mono-mp3",
            },
            data=ssml.encode("utf-8"), timeout=30,
        )
        if resp.status_code == 429:
            print("[azure_tts] Free-tier quota exhausted for today.")
            return None
        resp.raise_for_status()
        with open(output_path, "wb") as f:
            f.write(resp.content)
        duration = _probe_duration(output_path)
        print(f"[azure_tts] Synthesized {duration:.1f}s (timings estimated)")
        return {"duration_seconds": duration, "engine": "azure_tts"}
    except Exception as e:
        print(f"[azure_tts] Synthesis failed ({e}).")
        return None


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


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
