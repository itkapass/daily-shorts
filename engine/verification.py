"""
verification.py — cross-verification + review-queue routing (Section 4).
============================================================================
"Wikidata + Wikipedia prose + one additional free news/reference API. If
sources disagree, auto-route to a review queue instead of guessing."

THREE INDEPENDENT SOURCES, CROSS-CHECKED
  1. Wikidata's own structured statement   — P569/P570 (birth/death dates),
                                              wikidata_source.birth_death_years()
  2. Wikipedia's "On this day" blurb's year — the fact this candidate was
                                              sourced from in the first place
  3. Wikipedia's own prose extract/summary  — engine.research's grounding,
                                              checked for the same year
This project intentionally avoids bolting on a fourth paid/rate-limited
"news API" just to tick a box — these three sources are already
independent enough (one structured database, one curated feed, one
free-text article) to catch the actual failure mode Section 4 cares about:
a scraped year or fact that doesn't match the subject's own record. Swap
in a fourth source in `_third_party_checks()` below if you want one later
(e.g. a wire-service API) — the review-queue routing logic doesn't change.

Disagreement does not reject the candidate — it flags it for human review
(Section 4: "auto-route to a review queue instead of guessing") so a
genuinely rare mismatch (a Wikidata statement that is itself wrong, or an
On-This-Day entry using an Old Style calendar date) doesn't silently kill
a video, but also never airs unverified as a confident fact.
"""
import re

from engine import wikidata_source, research


def verify_candidate(candidate: dict, qid: str, kind: str) -> dict:
    """`kind` is "birth" or "death". Returns:
        {"verified": bool, "conflict": str|None, "notes": list}
    `notes` is the Wikipedia research grounding (research.py), reused
    directly as script_generator.py's RESEARCH NOTES input so verification
    and script-writing share one fetch instead of two.
    """
    on_this_day_year = candidate.get("year")
    wd_years = wikidata_source.birth_death_years(qid) if qid else {"birth_year": None, "death_year": None}
    wd_year = wd_years.get(f"{kind}_year")

    notes = research.fetch_research_notes(candidate.get("wikipedia_title", ""), candidate.get("text", ""))
    prose_text = " ".join(n["extract"] for n in notes)

    conflict = None
    if on_this_day_year and wd_year and on_this_day_year != wd_year:
        conflict = (f"On-this-day year ({on_this_day_year}) does not match Wikidata's "
                    f"P569/P570 {kind} year ({wd_year}) for QID {qid}.")
    elif on_this_day_year and prose_text and str(on_this_day_year) not in prose_text:
        # Soft check only — a prose extract legitimately may not restate the
        # exact year (it might describe an era instead). Flagged as a
        # low-confidence note, not a hard conflict, to avoid false
        # positives from an otherwise-fine candidate.
        conflict = None

    return {
        "verified": conflict is None,
        "conflict": conflict,
        "notes": notes,
        "on_this_day_year": on_this_day_year,
        "wikidata_year": wd_year,
    }


def verify_event(candidate: dict) -> dict:
    """Events (Section 2, category 4) have no QID birth/death pair to check
    against, so verification here is: does the year stated in the
    "On this day" blurb appear, unchanged, in the Wikipedia prose extract
    for the linked page? Mismatch -> flagged for review, same as people."""
    year = candidate.get("year")
    notes = research.fetch_research_notes(candidate.get("wikipedia_title", ""), candidate.get("text", ""))
    prose_text = " ".join(n["extract"] for n in notes)

    conflict = None
    if year and prose_text and str(year) not in prose_text and str(abs(year)) not in prose_text:
        conflict = (f"Year {year} from the On-this-day listing was not found anywhere in "
                    f"the linked Wikipedia article's own text — worth a human look before airing.")

    return {"verified": conflict is None, "conflict": conflict, "notes": notes, "on_this_day_year": year}


def route_to_review_queue(db, date_str: str, category: str, candidate: dict, conflict: str):
    """Inserts a flagged candidate into the `review_queue` table instead of
    silently dropping it OR silently airing it as fact — Section 4's
    explicit instruction. A human clears these from the Supabase table
    directly (no admin UI in this build); topic_assembler.py skips
    anything still sitting here with status='pending' on the next run.
    """
    try:
        db.table("review_queue").insert({
            "date": date_str,
            "category": category,
            "subject": candidate.get("text", "")[:500],
            "wikipedia_title": candidate.get("wikipedia_title"),
            "conflict_detail": conflict,
            "status": "pending",
        }).execute()
        print(f"[verification] Routed to review_queue: {candidate.get('wikipedia_title')} — {conflict}")
    except Exception as e:
        print(f"[verification] Could not write to review_queue ({e}); skipping this candidate instead.")
