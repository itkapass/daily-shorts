"""
video_compositor.py — final assembly: background clips + captions +
branding + mixed audio -> one 1080x1920 MP4. Adapted and simplified from
the reference project's module (same spec, same crossfade-between-scenes
approach, same PIL-based caption/branding rendering so there's no
ImageMagick dependency to manage on a free CI runner).
"""
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import ImageClip, AudioFileClip, CompositeVideoClip, VideoFileClip, ColorClip

from engine.subtitle_engine import CaptionCard, CaptionStyle, get_active_card

if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.LANCZOS

VIDEO_WIDTH, VIDEO_HEIGHT, FPS = 1080, 1920, 30
CODEC, AUDIO_CODEC, VIDEO_BITRATE = "libx264", "aac", "4000k"
CROSSFADE_DURATION = 0.4
_FALLBACK_COLOR = (12, 12, 20)


def compose_video(scenes_with_clips: list, mixed_audio_path: str, caption_cards: list,
                   total_duration: float, output_path: str, caption_style: CaptionStyle = None,
                   branding: dict = None) -> str:
    caption_style = caption_style or CaptionStyle()
    print(f"[video_compositor] Composing {total_duration:.1f}s video, {len(scenes_with_clips)} scenes")

    base = ColorClip(size=(VIDEO_WIDTH, VIDEO_HEIGHT), color=_FALLBACK_COLOR, duration=total_duration)
    bg_clips = [base]
    for scene in scenes_with_clips:
        clip_path = scene.get("clip_path")
        start, end = scene["time_start"], scene["time_end"]
        if not clip_path or not os.path.exists(clip_path):
            continue
        try:
            clip = (VideoFileClip(clip_path)
                    .without_audio()
                    .set_start(start)
                    .set_duration(max(end - start, 0.1))
                    .resize((VIDEO_WIDTH, VIDEO_HEIGHT))
                    .crossfadein(min(CROSSFADE_DURATION, max(end - start, 0.1) / 2)))
            bg_clips.append(clip)
        except Exception as e:
            print(f"[video_compositor] Could not load clip '{clip_path}' ({e}); base layer shows through.")

    caption_clips = _build_caption_clips(caption_cards, caption_style, total_duration)
    branding_clips = _build_branding(branding, total_duration) if branding else []

    final = CompositeVideoClip(bg_clips + caption_clips + branding_clips,
                               size=(VIDEO_WIDTH, VIDEO_HEIGHT)).set_duration(total_duration)
    audio = AudioFileClip(mixed_audio_path)
    final = final.set_audio(audio)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    final.write_videofile(output_path, fps=FPS, codec=CODEC, audio_codec=AUDIO_CODEC,
                          bitrate=VIDEO_BITRATE, logger=None)

    for c in bg_clips + caption_clips + branding_clips:
        try:
            c.close()
        except Exception:
            pass
    audio.close()
    final.close()
    print(f"[video_compositor] Rendered: {output_path}")
    return output_path


def _load_font(size: int):
    try:
        return ImageFont.truetype("assets/fonts/Montserrat-Variable.ttf", size)
    except Exception:
        return ImageFont.load_default()


def _hex_to_rgba(hex_color: str, alpha: int = 255) -> tuple:
    h = hex_color.lstrip("#")
    if len(h) == 8:
        r, g, b, a = (int(h[i:i + 2], 16) for i in (0, 2, 4, 6))
        return (r, g, b, a)
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return (r, g, b, alpha)


def _render_text_card(words: list, active_index: int, style: CaptionStyle, size: tuple) -> np.ndarray:
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = _load_font(style.font_size)

    full_text = " ".join(words)
    bbox = draw.textbbox((0, 0), full_text, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (size[0] - text_w) // 2
    y = int(size[1] * style.position_y_ratio)

    if style.bg_box:
        pad = style.bg_padding
        draw.rectangle([x - pad, y - pad, x + text_w + pad, y + text_h + pad],
                      fill=_hex_to_rgba(style.bg_color))

    cursor_x = x
    for i, w in enumerate(words):
        color = style.highlight_color if i == active_index else style.font_color
        draw.text((cursor_x, y), w, font=font, fill=_hex_to_rgba(color),
                  stroke_width=style.stroke_width, stroke_fill=_hex_to_rgba(style.stroke_color))
        w_bbox = draw.textbbox((0, 0), w + " ", font=font)
        cursor_x += w_bbox[2] - w_bbox[0]

    return np.array(img)


def _build_caption_clips(cards: list, style: CaptionStyle, total_duration: float) -> list:
    clips = []
    size = (VIDEO_WIDTH, VIDEO_HEIGHT)
    for card in cards:

        def make_frame(t, card=card):
            idx = card.active_index(t + card.start_time)
            return _render_text_card(card.words, idx, style, size)

        clip = (ImageClip(make_frame(card.start_time), ismask=False, duration=card.duration)
                if False else None)
        # ImageClip needs a static frame; captions change per word, so we use a
        # tiny VideoClip-style callback instead — moviepy's `make_frame` on a
        # VideoClip subclass handles the per-word highlight cheaply since each
        # card only lasts ~0.5-1.5s.
        from moviepy.editor import VideoClip
        vclip = VideoClip(lambda t, card=card: _render_text_card(
            card.words, card.active_index(t + card.start_time), style, size)[:, :, :3],
            duration=card.duration)
        mask = VideoClip(lambda t, card=card: _render_text_card(
            card.words, card.active_index(t + card.start_time), style, size)[:, :, 3] / 255.0,
            duration=card.duration, ismask=True)
        vclip = vclip.set_mask(mask).set_start(card.start_time)
        clips.append(vclip)
    return clips


def _build_branding(branding: dict, total_duration: float) -> list:
    channel_name = (branding or {}).get("channel_name")
    if not channel_name:
        return []
    size = (VIDEO_WIDTH, 90)
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = _load_font(40)
    text = f"@{channel_name.lstrip('@')}"
    bbox = draw.textbbox((0, 0), text, font=font)
    x = (size[0] - (bbox[2] - bbox[0])) // 2
    draw.text((x, 20), text, font=font, fill=(255, 255, 255, 200),
              stroke_width=2, stroke_fill=(0, 0, 0, 200))
    arr = np.array(img)
    clip = (ImageClip(arr[:, :, :3], duration=total_duration)
            .set_mask(ImageClip(arr[:, :, 3] / 255.0, ismask=True, duration=total_duration))
            .set_position(("center", 60)))
    return [clip]
