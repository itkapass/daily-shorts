"""
config.py — loads and validates environment variables for every module.
=========================================================================
Same pattern the reference cricket_shorts_studio project uses, and for the
same reason: get(key) ALWAYS falls through to a raw os.getenv() for
anything not in the curated _env dict below. That dict exists purely as a
readable "these are the keys this project knows about" reference — it is
never allowed to be the reason a real, correctly-set environment variable
(a local .env value, or a GitHub Actions secret) goes unseen by the code
that needs it. That exact bug (a key missing from a hand-maintained dict,
silently killing a whole feature) hit the reference project three times;
get()'s fallback closes the whole class of bug here from day one.

Each module calls require([...]) with ONLY the keys it needs, so a missing
key only ever breaks the one feature that needed it, not the whole run.
"""
import os
from dotenv import load_dotenv

load_dotenv()

_env = {
    # ── LLM / script generation ─────────────────────────────────────
    "GEMINI_API_KEY":          os.getenv("GEMINI_API_KEY"),
    "GEMINI_MODEL":            os.getenv("GEMINI_MODEL"),
    "GEMINI_TEMPERATURE":      os.getenv("GEMINI_TEMPERATURE"),
    "GROQ_API_KEY":            os.getenv("GROQ_API_KEY"),
    "GROQ_MODEL":              os.getenv("GROQ_MODEL"),
    "GITHUB_MODELS_TOKEN":     os.getenv("GITHUB_MODELS_TOKEN"),

    # ── Database / storage ───────────────────────────────────────────
    "SUPABASE_URL":            os.getenv("SUPABASE_URL"),
    "SUPABASE_ANON_KEY":       os.getenv("SUPABASE_ANON_KEY"),
    "SUPABASE_SERVICE_KEY":    os.getenv("SUPABASE_SERVICE_KEY"),
    "R2_ACCOUNT_ID":           os.getenv("R2_ACCOUNT_ID"),
    "R2_ACCESS_KEY_ID":        os.getenv("R2_ACCESS_KEY_ID"),
    "R2_SECRET_ACCESS_KEY":    os.getenv("R2_SECRET_ACCESS_KEY"),
    "R2_PUBLIC_BASE":          os.getenv("R2_PUBLIC_BASE"),
    "STORAGE_BUCKET":          os.getenv("STORAGE_BUCKET", "daily-history-shorts"),

    # ── YouTube publishing ───────────────────────────────────────────
    "YOUTUBE_CLIENT_ID":       os.getenv("YOUTUBE_CLIENT_ID"),
    "YOUTUBE_CLIENT_SECRET":   os.getenv("YOUTUBE_CLIENT_SECRET"),
    "YOUTUBE_REFRESH_TOKEN":   os.getenv("YOUTUBE_REFRESH_TOKEN"),
    "YOUTUBE_CHANNEL_HANDLE":  os.getenv("YOUTUBE_CHANNEL_HANDLE"),

    # ── Voice pipeline (VOICE_PROVIDER = free | cloned | paid) ───────
    "VOICE_PROVIDER":          os.getenv("VOICE_PROVIDER", "free"),
    "GOOGLE_TTS_API_KEY":      os.getenv("GOOGLE_TTS_API_KEY"),
    "AZURE_TTS_KEY":           os.getenv("AZURE_TTS_KEY"),
    "AZURE_TTS_REGION":        os.getenv("AZURE_TTS_REGION"),
    "PIPER_MODEL_PATH":        os.getenv("PIPER_MODEL_PATH"),
    "XTTS_SPEAKER_WAV_PATH":   os.getenv("XTTS_SPEAKER_WAV_PATH"),
    "ELEVENLABS_API_KEY":      os.getenv("ELEVENLABS_API_KEY"),
    "ELEVENLABS_VOICE_ID":     os.getenv("ELEVENLABS_VOICE_ID"),

    # ── Voice/accent overrides — all default to Indian English (en-IN)
    #    since this channel is India-first; override any of these in .env
    #    to change the host voice/accent without touching code ──────────
    "GOOGLE_TTS_VOICE_NAME":   os.getenv("GOOGLE_TTS_VOICE_NAME"),
    "GOOGLE_TTS_LANGUAGE_CODE": os.getenv("GOOGLE_TTS_LANGUAGE_CODE"),
    "AZURE_TTS_VOICE_NAME":    os.getenv("AZURE_TTS_VOICE_NAME"),
    "AZURE_TTS_LANGUAGE_CODE": os.getenv("AZURE_TTS_LANGUAGE_CODE"),
    "KOKORO_VOICE_ID":         os.getenv("KOKORO_VOICE_ID"),
    "KOKORO_VOICE_LANG":       os.getenv("KOKORO_VOICE_LANG"),
    "GTTS_TLD":                os.getenv("GTTS_TLD"),

    # ── Festival / observance calendar refresh ───────────────────────
    "CALENDARIFIC_API_KEY":    os.getenv("CALENDARIFIC_API_KEY"),

    # ── Alerts ────────────────────────────────────────────────────────
    "TELEGRAM_BOT_TOKEN":      os.getenv("TELEGRAM_BOT_TOKEN"),
    "TELEGRAM_CHAT_ID":        os.getenv("TELEGRAM_CHAT_ID"),
    "SMTP_HOST":               os.getenv("SMTP_HOST"),
    "SMTP_PORT":               os.getenv("SMTP_PORT"),
    "SMTP_USER":               os.getenv("SMTP_USER"),
    "SMTP_PASSWORD":           os.getenv("SMTP_PASSWORD"),
    "ALERT_EMAIL_TO":          os.getenv("ALERT_EMAIL_TO"),

    # ── Pipeline settings ─────────────────────────────────────────────
    "OUTPUT_DIR":              os.getenv("OUTPUT_DIR", "output"),
    "ASSETS_DIR":              os.getenv("ASSETS_DIR", "assets"),
    "TARGET_RUNTIME_SECONDS":  os.getenv("TARGET_RUNTIME_SECONDS", "52"),
    "MAX_UPLOADS_PER_DAY":     os.getenv("MAX_UPLOADS_PER_DAY", "6"),
}


def require(keys: list) -> dict:
    """Call at the top of a module with exactly the keys IT needs. Raises
    only if one of THOSE is missing — never the whole project's env list."""
    result, missing = {}, []
    for key in keys:
        val = _env.get(key) or os.getenv(key)
        if not val:
            missing.append(key)
        else:
            result[key] = val
    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            f"Check your .env file (see docs/START_HERE.md)."
        )
    return result


def get(key: str, default=None):
    """Optional lookup — never crashes. Falls through to a raw os.getenv()
    for anything not in the curated dict above (see module docstring)."""
    return _env.get(key) or os.getenv(key) or default


def get_bool(key: str, default: bool = False) -> bool:
    val = get(key)
    if val is None:
        return default
    return str(val).strip().lower() in ("1", "true", "yes", "on")
