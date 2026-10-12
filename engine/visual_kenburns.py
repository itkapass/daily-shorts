"""
visual_kenburns.py — turns a still photo into a short 9:16 video clip.
=======================================================================
Adapted directly from the reference project (same ffmpeg zoompan
approach, same four motions chosen deterministically per scene). This is
exactly the "Ken Burns motion on real archival photos" Section 4 of the
build spec calls for, reused rather than rebuilt.
"""
import os
import subprocess

OUT_W, OUT_H = 1080, 1920
MOTIONS = ("zoom_in", "zoom_out", "pan_left", "pan_right")


def _motion_for_scene(scene_number: int, seed: int = 0) -> str:
    return MOTIONS[(int(scene_number or 1) + seed) % len(MOTIONS)]


def _zoompan_filter(motion: str, hold_seconds: float, fps: int = 30) -> str:
    frames = max(int(hold_seconds * fps), fps)
    if motion == "zoom_in":
        z = "min(zoom+0.0018,1.18)"
        x, y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    elif motion == "zoom_out":
        z = "if(eq(on,1),1.18,max(zoom-0.0018,1.0))"
        x, y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    elif motion == "pan_left":
        z = "1.16"
        x = f"if(eq(on,1),iw-iw/zoom,max(x-{max(1, int(1400 / frames))},0))"
        y = "ih/2-(ih/zoom/2)"
    else:
        z = "1.16"
        x = f"if(eq(on,1),0,min(x+{max(1, int(1400 / frames))},iw-iw/zoom))"
        y = "ih/2-(ih/zoom/2)"
    return f"zoompan=z='{z}':x='{x}':y='{y}':d=1:s={OUT_W}x{OUT_H}:fps={fps}"


def image_to_clip(image_path: str, output_mp4_path: str, hold_seconds: float,
                   scene_number: int = 1, motion_seed: int = 0) -> bool:
    """Converts one still image into a `hold_seconds`-long 1080x1920 .mp4
    with a Ken Burns pan or zoom. Returns False on any failure (never
    raises) — callers move to the next visual source on False."""
    if not image_path or not os.path.exists(image_path):
        return False

    motion = _motion_for_scene(scene_number, motion_seed)
    hold = max(float(hold_seconds) + 0.6, 1.5)
    zoompan = _zoompan_filter(motion, hold)
    oversize_w, oversize_h = int(OUT_W * 2.0), int(OUT_H * 2.0)
    vf = (f"scale={oversize_w}:{oversize_h}:force_original_aspect_ratio=increase,"
          f"crop={oversize_w}:{oversize_h},{zoompan},format=yuv420p")

    try:
        subprocess.run(
            ["ffmpeg", "-y", "-loop", "1", "-i", image_path, "-t", str(hold),
             "-vf", vf, "-r", "30", "-pix_fmt", "yuv420p", output_mp4_path],
            check=True, capture_output=True, timeout=45,
        )
        return os.path.exists(output_mp4_path) and os.path.getsize(output_mp4_path) > 2000
    except Exception as e:
        print(f"[visual_kenburns] Could not convert {image_path} to video ({e}).")
        return False
