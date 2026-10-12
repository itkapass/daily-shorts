"""
visual_matcher.py — QID-anchored images, never a generic image search.
==========================================================================
Section 4 of the build spec, verbatim: "Wikimedia Commons images tied to
the same Wikidata QID as the matched person — never a generic image
search. This is the fix for face-mismatch risk."

TWO-STEP LOOKUP, BOTH ANCHORED TO THE SAME QID
  1. Wikidata's own P18 ("image") claim for the QID — the subject's own
     curated infobox portrait. Tried first because it IS the canonical
     photo for that specific Wikidata item, not a search result that
     merely mentions the subject's name.
  2. If no P18 claim exists, search Commons' "haswbstatement" index for
     files explicitly linked back to this QID (Commons' own structured
     data, not keyword text search) — still QID-anchored, just a second
     path to the same guarantee.
If NEITHER yields an image, this returns None and the caller (the topic
assembler / orchestrator) falls back to a plain text/title card for that
scene rather than ever substituting an unrelated photo — silently
"finding something close enough" is exactly the bug Section 4 is guarding
against.

For non-person "This Day in History" events with no single identifiable
face (a treaty signing, a scientific milestone), the same QID-first
approach is used against the EVENT's own Wikidata item when one exists;
Section 12's AI-generated-abstract-B-roll path (engine/ai_visuals.py) is
the documented fallback when it does not.
"""
import os
import requests

from engine.visual_kenburns import image_to_clip

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
TIMEOUT_SECONDS = 20
USER_AGENT = "DailyHistoryShorts/1.0 (free educational short-form video project)"
_REJECT_MARKERS = ("icon", "logo", "flag of", ".svg", "diagram", "map of", "coa_")


def _file_info(filename: str) -> dict:
    """Resolves a bare Commons filename (e.g. 'Example.jpg') to its direct
    download URL + dimensions."""
    try:
        resp = requests.get(
            COMMONS_API,
            params={"action": "query", "format": "json", "prop": "imageinfo",
                    "titles": f"File:{filename}", "iiprop": "url|size"},
            headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {})
        for page in pages.values():
            info = (page.get("imageinfo") or [None])[0]
            if info and info.get("url"):
                return {"title": page.get("title"), "url": info["url"],
                        "width": info.get("width", 0), "height": info.get("height", 0)}
    except Exception as e:
        print(f"[visual_matcher] Commons file lookup failed for '{filename}': {e}")
    return {}


def _search_by_qid(qid: str, limit: int = 5) -> list:
    """Commons files whose own structured data explicitly links back to
    this Wikidata QID — a structured match, not a keyword search."""
    try:
        resp = requests.get(
            COMMONS_API,
            params={"action": "query", "format": "json", "list": "search",
                    "srsearch": f"haswbstatement:P180={qid} filetype:bitmap",
                    "srnamespace": 6, "srlimit": limit},
            headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        titles = [h["title"].split("File:", 1)[-1] for h in resp.json().get("query", {}).get("search", [])]
        out = []
        for t in titles:
            info = _file_info(t)
            if info and not any(m in info["title"].lower() for m in _REJECT_MARKERS):
                out.append(info)
        return out
    except Exception as e:
        print(f"[visual_matcher] QID-structured Commons search failed for {qid}: {e}")
        return []


def fetch_photo_for_candidate(qid: str, duration_needed: float, job_id: str,
                               scene_number: int, output_dir: str) -> dict:
    """Returns {"clip_path", "source", "qid"} on success, or None — callers
    fall back to a text-card scene on None, never to an unrelated photo."""
    if not qid:
        return None

    from engine import wikidata_source
    candidate = None

    p18_filename = wikidata_source.image_claim(qid)
    if p18_filename:
        info = _file_info(p18_filename)
        if info and info.get("width", 0) >= 400:
            candidate = info

    if not candidate:
        results = _search_by_qid(qid)
        results = [r for r in results if r.get("width", 0) >= 700 or r.get("height", 0) >= 700] or results
        if results:
            candidate = results[0]

    if not candidate:
        print(f"[visual_matcher] No QID-anchored image found for {qid} — using a text card instead.")
        return None

    os.makedirs(output_dir, exist_ok=True)
    img_ext = os.path.splitext(candidate["url"])[1] or ".jpg"
    img_path = os.path.join(output_dir, f"{job_id}_s{scene_number}_{qid}{img_ext}")
    mp4_path = os.path.join(output_dir, f"{job_id}_s{scene_number}_{qid}.mp4")

    try:
        r = requests.get(candidate["url"], timeout=30, headers={"User-Agent": USER_AGENT})
        r.raise_for_status()
        with open(img_path, "wb") as f:
            f.write(r.content)
    except Exception as e:
        print(f"[visual_matcher] Download failed for '{candidate['title']}': {e}")
        return None

    ok = image_to_clip(img_path, mp4_path, duration_needed, scene_number=scene_number, motion_seed=1)
    try:
        os.remove(img_path)
    except OSError:
        pass
    if not ok:
        return None

    print(f"[visual_matcher] QID-anchored photo used for {qid}: {candidate['title']}")
    return {"clip_path": mp4_path, "source": "wikidata_qid", "qid": qid}
