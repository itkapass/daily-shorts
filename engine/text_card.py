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
import textwrap

from PIL import Image, ImageDraw, ImageFont

from engine.visual_kenburns import image_to_clip, OUT_W, OUT_H

_BG_COLORS = [(18, 18, 28), (24, 20, 36), (16, 24, 32)]


def _load_font(size: int):
    for path in ("assets/fonts/Montserrat-Variable.ttf",):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _render_card_png(text: str, output_png: str, seed: int = 0) -> str:
    bg = _BG_COLORS[seed % len(_BG_COLORS)]
    img = Image.new("RGB", (OUT_W, OUT_H), bg)
    draw = ImageDraw.Draw(img)
    font = _load_font(78)

    wrapped = textwrap.fill(text, width=22)
    lines = wrapped.split("\n")
    line_height = 92
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
