"""
ai_visuals.py — abstract, non-person AI-generated B-roll (Section 12 /
Section 15's future-improvement hook).

Explicitly scoped: this is ONLY for abstract event visuals with no single
identifiable face — "the UN was formed," a nuclear test, a treaty
signing — never a sketch/likeness of a real, named person (that stays
permanently out of scope, see Section 12). Used as a LAST resort, after
visual_matcher.py's QID-anchored photo lookup and before falling back to
a plain text_card, for "This Day in History" events that have no good
archival photo.

OFF by default — this calls Hugging Face's free inference API, which
needs a free token (docs/06). With no key set, available() is False and
callers skip straight to text_card.py, exactly like every other optional
provider in this pipeline.
"""
import os

import requests

from engine.config import get
from engine.visual_kenburns import image_to_clip

HF_ENDPOINT = "https://api-inference.huggingface.co/models/{model}"
DEFAULT_MODEL = "black-forest-labs/FLUX.1-schnell"

# A hard-coded guard, not just documentation: if a caller ever passes a
# prompt containing a likely person-name pattern, refuse rather than
# generate. This can't catch everything, but it is a real backstop behind
# the "never generate a real person" rule, not only a comment.
_PERSON_HINT_WORDS = ("portrait of", "face of", "likeness of")


def available() -> bool:
    return bool(get("HUGGINGFACE_API_KEY"))


def generate_abstract_broll(prompt: str, duration_needed: float, job_id: str,
                            scene_number: int, output_dir: str) -> dict:
    api_key = get("HUGGINGFACE_API_KEY")
    if not api_key:
        return None
    lowered = prompt.lower()
    if any(h in lowered for h in _PERSON_HINT_WORDS):
        print(f"[ai_visuals] Refusing a person-shaped prompt ({prompt!r}) — out of scope per Section 12.")
        return None

    safe_prompt = (f"Abstract, cinematic, non-literal illustration of: {prompt}. "
                   f"No readable text, no recognizable real people, symbolic and atmospheric only.")
    model = get("HUGGINGFACE_IMAGE_MODEL", DEFAULT_MODEL)
    try:
        resp = requests.post(
            HF_ENDPOINT.format(model=model),
            headers={"Authorization": f"Bearer {api_key}"},
            json={"inputs": safe_prompt}, timeout=60,
        )
        if not resp.ok or "image" not in resp.headers.get("content-type", ""):
            print(f"[ai_visuals] Hugging Face generation failed or returned non-image ({resp.status_code}).")
            return None
        os.makedirs(output_dir, exist_ok=True)
        img_path = os.path.join(output_dir, f"{job_id}_s{scene_number}_ai.png")
        mp4_path = os.path.join(output_dir, f"{job_id}_s{scene_number}_ai.mp4")
        with open(img_path, "wb") as f:
            f.write(resp.content)
        ok = image_to_clip(img_path, mp4_path, duration_needed, scene_number=scene_number, motion_seed=2)
        try:
            os.remove(img_path)
        except OSError:
            pass
        if not ok:
            return None
        return {"clip_path": mp4_path, "source": "ai_abstract", "qid": None}
    except Exception as e:
        print(f"[ai_visuals] Generation failed ({e}).")
        return None
