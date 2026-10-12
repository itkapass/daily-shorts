"""
xtts_clone.py — VOICE_PROVIDER=cloned (Section 6, option 2): self-hosted
voice cloning with Coqui XTTS, zero recurring cost.

SETUP (see docs/06_PAID_UPGRADES_LATER.md)
  1. pip install TTS   (NOT in requirements.txt by default — heavy, ~2GB
     of model weights on first run; install it only if you want this tier)
  2. Record a clean ~10-20 second sample of the voice to clone (yours, or
     another CONSENTING speaker's — never clone a voice without
     ownership/consent, see the note in docs/06) and save it as a .wav.
  3. Set VOICE_PROVIDER=cloned and XTTS_SPEAKER_WAV_PATH=path/to/sample.wav

GitHub Actions' free runners are CPU-only, so this tier renders slower
than the cloud TTS tiers — accepted per the build spec ("render time is
not a constraint").
"""
import subprocess

from engine.config import get

_model = None


def available() -> bool:
    try:
        import TTS  # noqa: F401
    except ImportError:
        return False
    return bool(get("XTTS_SPEAKER_WAV_PATH"))


def _get_model():
    global _model
    if _model is not None:
        return _model
    from TTS.api import TTS as CoquiTTS
    _model = CoquiTTS("tts_models/multilingual/multi-dataset/xtts_v2")
    return _model


def synthesize(text: str, output_path: str) -> dict:
    speaker_wav = get("XTTS_SPEAKER_WAV_PATH")
    if not speaker_wav:
        return None
    try:
        model = _get_model()
        wav_path = output_path.replace(".mp3", ".wav")
        model.tts_to_file(text=text, speaker_wav=speaker_wav, language="en", file_path=wav_path)
        subprocess.run(
            ["ffmpeg", "-y", "-i", wav_path, "-codec:a", "libmp3lame", "-q:a", "2", output_path],
            check=True, capture_output=True, timeout=180,
        )
        duration = _probe_duration(output_path)
        print(f"[xtts_clone] Synthesized {duration:.1f}s with the cloned voice (timings estimated)")
        return {"duration_seconds": duration, "engine": "xtts_clone"}
    except Exception as e:
        print(f"[xtts_clone] Synthesis failed ({e}).")
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
