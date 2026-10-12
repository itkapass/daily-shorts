"""
audio_mixer.py — voiceover + optional ducked background music.
Adapted from the reference project, simplified: this project ships with
no bundled music tracks (nothing royalty-cleared to include by default),
so mixing degrades gracefully to voice-only until you drop .mp3 files
into assets/music/ yourself (see docs/START_HERE.md's optional-polish
note). The ducking math itself (smoothed envelope, not a hard step) is
unchanged from the reference project.
"""
import os
import random
from pathlib import Path

import numpy as np
from moviepy.editor import AudioFileClip, CompositeAudioClip

from engine.config import get

MUSIC_VOLUME_UNDER_VOICE = 0.12
MUSIC_VOLUME_DURING_PAUSE = 0.32
FADE_DURATION = 0.25


def mix_audio(voiceover_path: str, word_timestamps: list, total_duration: float, output_path: str) -> str:
    voice = AudioFileClip(voiceover_path)
    music_clip = _load_music_track(total_duration)
    layers = [voice]
    if music_clip:
        layers.append(_apply_ducking(music_clip, word_timestamps, total_duration))

    final_audio = CompositeAudioClip(layers).set_duration(total_duration)
    final_audio = final_audio.audio_fadein(0.3).audio_fadeout(0.5)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    final_audio.write_audiofile(output_path, fps=44100, nbytes=2, logger=None)

    voice.close()
    if music_clip:
        music_clip.close()
    final_audio.close()
    print(f"[audio_mixer] Mixed audio saved: {output_path}")
    return output_path


def _load_music_track(duration: float):
    music_dir = os.path.join(get("ASSETS_DIR", "assets"), "music")
    if not os.path.isdir(music_dir):
        return None
    tracks = list(Path(music_dir).glob("*.mp3")) + list(Path(music_dir).glob("*.wav"))
    if not tracks:
        return None
    try:
        music = AudioFileClip(str(random.choice(tracks)))
        if music.duration < duration:
            from moviepy.audio.fx.audio_loop import audio_loop
            music = audio_loop(music, nloops=int(np.ceil(duration / music.duration)))
        return music.subclip(0, duration)
    except Exception as e:
        print(f"[audio_mixer] Could not load music track ({e}); continuing with voice only.")
        return None


def _apply_ducking(music, word_timestamps: list, total_duration: float):
    if not word_timestamps:
        return music.volumex(MUSIC_VOLUME_UNDER_VOICE)

    speaking_ranges = [(w["start"], w["end"]) for w in word_timestamps]
    dt = 0.02
    n_samples = max(int(total_duration / dt) + 2, 2)
    times = np.linspace(0, total_duration, n_samples)
    raw = np.zeros(n_samples)
    for start, end in speaking_ranges:
        raw[(times >= start - 0.05) & (times <= end + 0.05)] = 1.0

    kernel_half = max(int(FADE_DURATION / dt), 1)
    kernel = np.hanning(kernel_half * 2 + 1)
    kernel = kernel / kernel.sum()
    smoothed = np.clip(np.convolve(raw, kernel, mode="same"), 0.0, 1.0)
    envelope = MUSIC_VOLUME_DURING_PAUSE + (MUSIC_VOLUME_UNDER_VOICE - MUSIC_VOLUME_DURING_PAUSE) * smoothed

    def volume_at(t_scalar):
        idx = int(np.clip(t_scalar / dt, 0, n_samples - 1))
        return envelope[idx]

    def make_volume_array(get_frame, t):
        frame = get_frame(t)
        if np.isscalar(t):
            return frame * volume_at(t)
        vols = np.array([volume_at(tt) for tt in t])
        if frame.ndim == 2:
            vols = vols[:, None]
        return frame * vols

    return music.fl(make_volume_array, keep_duration=True)
