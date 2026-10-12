"""
elevenlabs_tts.py — VOICE_PROVIDER=paid (Section 6, option 3): the one
paid hook in the voice pipeline. Built now, OFF by default — only used
when VOICE_PROVIDER=paid AND ELEVENLABS_API_KEY is set. Fully API-driven,
no manual dashboard step beyond generating the key and (optionally) an
instant-cloned voice id.
"""
import subprocess

import requests

from engine.config import get

ENDPOINT = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"   # ElevenLabs' public default voice ("Rachel")


def available() -> bool:
    return bool(get("ELEVENLABS_API_KEY"))


def synthesize(text: str, output_path: str) -> dict:
    api_key = get("ELEVENLABS_API_KEY")
    if not api_key:
        return None
    voice_id = get("ELEVENLABS_VOICE_ID", DEFAULT_VOICE_ID)
    try:
        resp = requests.post(
            ENDPOINT.format(voice_id=voice_id),
            headers={"xi-api-key": api_key, "Content-Type": "application/json"},
            json={"text": text, "model_id": "eleven_multilingual_v2",
                  "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}},
            timeout=60,
        )
        if resp.status_code == 429:
            print("[elevenlabs_tts] Quota/rate limit hit.")
            return None
        resp.raise_for_status()
        with open(output_path, "wb") as f:
            f.write(resp.content)
        duration = _probe_duration(output_path)
        print(f"[elevenlabs_tts] Synthesized {duration:.1f}s (timings estimated)")
        return {"duration_seconds": duration, "engine": "elevenlabs"}
    except Exception as e:
        print(f"[elevenlabs_tts] Synthesis failed ({e}).")
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
