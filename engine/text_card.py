"""
text_card.py — the no-image fallback scene.

Section 4 is explicit: images must be QID-anchored, never a generic
search substitute. So when visual_matcher.py finds no QID-anchored photo
for a candidate, THIS is the fallback — a plain generated title/fact
card, never an unrelated photo. It is rendered once as a PNG and then fed
through visual_kenburns.image_to_clip() exactly like a downloaded photo,
so the rest of the pipeline treats it identically to a real image scene.
"""
import os

from PIL import Image, ImageDraw, ImageFont

from engine.text_sanitize import sanitize_for_font
from engine.visual_kenburns import image_to_clip, OUT_W, OUT_H

_BG_COLORS = [(18, 18, 28), (24, 20, 36), (16, 24, 32)]

# Text must actually fit inside the frame — the previous version wrapped by
# a fixed CHARACTER count (textwrap.fill(..., width=22)), which has no idea
# how wide 22 characters of a proportional font actually render at 78px;
# on real sentences this ran words off the right edge of the video, clipped
# mid-word, for every text-card fallback scene (confirmed from real output:
# "...Manchester Unit[ed]" cut off at the frame boundary). MAX_WIDTH below
# is the real pixel budget words are wrapped against instead.
MAX_WIDTH = OUT_W - 160          # 80px margin each side
MAX_LINES = 9                    # shrink font rather than overflow past this
MAX_FONT_SIZE = 78
MIN_FONT_SIZE = 44
LINE_HEIGHT_RATIO = 1.18         # of font size


def _load_font(size: int):
    for path in ("assets/fonts/Montserrat-Variable.ttf",):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _wrap_to_width(text: str, font: ImageFont.FreeTypeFont, draw: ImageDraw.ImageDraw,
                    max_width: int) -> list:
    """Greedy word-wrap measured against actual rendered pixel width at
    this font/size, not a guessed character count."""
    words = text.split()
    lines, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        w = draw.textbbox((0, 0), candidate, font=font)[2]
        if w <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _fit_text(text: str, draw: ImageDraw.ImageDraw):
    """Picks the largest font size (within MAX/MIN_FONT_SIZE) whose
    word-wrapped layout fits both the horizontal pixel budget (every line
    <= MAX_WIDTH) and a sane line count (<= MAX_LINES), so long facts
    shrink gracefully instead of overflowing the frame."""
    size = MAX_FONT_SIZE
    while size >= MIN_FONT_SIZE:
        font = _load_font(size)
        text_for_font = sanitize_for_font(text, font)
        lines = _wrap_to_width(text_for_font, font, draw, MAX_WIDTH)
        if len(lines) <= MAX_LINES:
            return font, lines, size
        size -= 4
    # Smallest size still didn't fit the line-count budget — use it anyway
    # (better than crashing) and let the caller's text[:140] cap keep this rare.
    font = _load_font(MIN_FONT_SIZE)
    text_for_font = sanitize_for_font(text, font)
    return font, _wrap_to_width(text_for_font, font, draw, MAX_WIDTH), MIN_FONT_SIZE


def _render_card_png(text: str, output_png: str, seed: int = 0) -> str:
    bg = _BG_COLORS[seed % len(_BG_COLORS)]
    img = Image.new("RGB", (OUT_W, OUT_H), bg)
    draw = ImageDraw.Draw(img)

    font, lines, size = _fit_text(text, draw)
    line_height = int(size * LINE_HEIGHT_RATIO)
    total_h = line_height * len(lines)
    y = (OUT_H - total_h) // 2

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        x = (OUT_W - w) // 2
        draw.text((x, y), line, font=font, fill="#FFFFFF", stroke_width=2, stroke_fill="#000000")
        y += line_height

    img.save(output_png)
    return output_png


def build_text_card_clip(text: str, duration_needed: float, job_id: str,
                          scene_number: int, output_dir: str) -> dict:
    os.makedirs(output_dir, exist_ok=True)
    png_path = os.path.join(output_dir, f"{job_id}_s{scene_number}_card.png")
    mp4_path = os.path.join(output_dir, f"{job_id}_s{scene_number}_card.mp4")
    _render_card_png(text[:140], png_path, seed=scene_number)
    ok = image_to_clip(png_path, mp4_path, duration_needed, scene_number=scene_number, motion_seed=0)
    try:
        os.remove(png_path)
    except OSError:
        pass
    if not ok:
        return None
    return {"clip_path": mp4_path, "source": "text_card", "qid": None}
