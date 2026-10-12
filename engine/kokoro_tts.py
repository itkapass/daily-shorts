"""
kokoro_tts.py — offline neural TTS, the reliable rung under the free-tier
cloud engines (Google Cloud TTS / Azure) in voice_engine.py's fallback
chain. Adapted from the reference project: MIT-licensed, no network call
once its model files are cached, so it never goes down the day a cloud
quota or endpoint has a bad day.
"""
import os
import subprocess
import urllib.request

from engine.config import get

_MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
_VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"

_CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "kokoro_tts")
MODEL_PATH = os.path.join(_CACHE_DIR, "kokoro-v1.0.onnx")
VOICES_PATH = os.path.join(_CACHE_DIR, "voices-v1.0.bin")

# One fixed voice — Section 7 wants ONE consistent host persona across the
# whole channel, not a tone-dependent voice picker.
#
# HONEST LIMITATION: Kokoro's bundled voicepack (as of this writing) only
# ships American and British English voices (af_*/am_* = US, bf_*/bm_* =
# UK) — there is no Indian-English option to default to here, unlike
# Google/Azure TTS below. For an India-first audience, Kokoro should be
# treated as the "something posts rather than nothing" offline safety net,
# not the primary voice — get GOOGLE_TTS_API_KEY or AZURE_TTS_KEY set up
# (docs/03) so real runs use the en-IN voice in google_tts.py/azure_tts.py
# instead of falling through to this tier. If a future Kokoro release adds
# an Indian voice, override it here without code changes via
# KOKORO_VOICE_ID / KOKORO_VOICE_LANG in .env.
HOST_VOICE_ID = get("KOKORO_VOICE_ID", "bm_george")
HOST_VOICE_LANG = get("KOKORO_VOICE_LANG", "en-gb")

_instance = None


def _ensure_models() -> bool:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    try:
        if not os.path.exists(MODEL_PATH) or os.path.getsize(MODEL_PATH) < 10_000_000:
            print("[kokoro_tts] Downloading the Kokoro voice model (~320MB, one-time)...")
            urllib.request.urlretrieve(_MODEL_URL, MODEL_PATH)
        if not os.path.exists(VOICES_PATH) or os.path.getsize(VOICES_PATH) < 1_000_000:
            print("[kokoro_tts] Downloading the Kokoro voices file (~27MB, one-time)...")
            urllib.request.urlretrieve(_VOICES_URL, VOICES_PATH)
        return True
    except Exception as e:
        print(f"[kokoro_tts] Could not download model files ({e}).")
        return False


def _get_model():
    global _instance
    if _instance is not None:
        return _instance
    if not _ensure_models():
        return None
    try:
        from kokoro_onnx import Kokoro
        _instance = Kokoro(MODEL_PATH, VOICES_PATH)
        return _instance
    except Exception as e:
        print(f"[kokoro_tts] Could not load the Kokoro model ({e}).")
        return None


def available() -> bool:
    try:
        import kokoro_onnx  # noqa: F401
        return True
    except ImportError:
        return False


def synthesize(text: str, output_path: str) -> dict:
    model = _get_model()
    if model is None:
        return None
    try:
        import soundfile as sf
        audio, sample_rate = model.create(text, voice=HOST_VOICE_ID, speed=1.0, lang=HOST_VOICE_LANG)
        wav_path = output_path.replace(".mp3", ".wav")
        sf.write(wav_path, audio, sample_rate)
        subprocess.run(
            ["ffmpeg", "-y", "-i", wav_path, "-codec:a", "libmp3lame", "-q:a", "2", output_path],
            check=True, capture_output=True, timeout=120,
        )
        os.remove(wav_path)
        duration = len(audio) / sample_rate
        print(f"[kokoro_tts] Synthesized {duration:.1f}s (timings estimated)")
        return {"duration_seconds": duration, "engine": "kokoro"}
    except Exception as e:
        print(f"[kokoro_tts] Synthesis failed ({e}).")
        return None
