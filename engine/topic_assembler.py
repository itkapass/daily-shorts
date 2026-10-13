"""
topic_assembler.py — today's candidate lists, ranked, verified, and sized
to a runtime budget (Section 2).
============================================================================
"The content/topic-generation step must first assemble the full candidate
list for the day (ranked by notability), then decide how many entries
justify a video and whether to split into Part 1/Part 2/Part 3 — sized
against a fixed runtime budget, not the other way around. Target ~45-60
seconds per video/part."

PIPELINE PER CATEGORY
  1. Pull raw candidates for the day (engine.wikidata_source).
  2. Resolve each candidate's Wikidata QID (needed for notability,
     verification, AND the QID-anchored image lookup downstream).
  3. Rank by trailing-30-day Wikipedia pageviews (engine.notability) —
     "data-driven, not arbitrary."
  4. Cross-verify each against Wikidata's own structured dates
     (engine.verification); disagreements are routed to review_queue and
     excluded from today's batch rather than aired as unverified fact.
  5. Size the surviving, ranked list against the runtime budget — how
     many entries actually fit ~TARGET_RUNTIME_SECONDS at this project's
     narration pace — and split into Part 1/2/3 if the day is big.
"""
import re
from datetime import date

from engine import wikidata_source, notability, verification
from engine.config import get

WORDS_PER_SECOND = 2.5          # ~150 wpm narration pace
HOOK_OUTRO_OVERHEAD_WORDS = 40  # hook + closing CTA, roughly, per video/part
WORDS_PER_ENTRY = 32            # name/fact + one line of commentary, roughly
MAX_CANDIDATES_CONSIDERED = 40  # per category, before sizing — keeps API calls bounded


def target_runtime_seconds() -> float:
    return float(get("TARGET_RUNTIME_SECONDS", "52"))


def entries_per_part(runtime_seconds: float = None) -> int:
    """How many candidate entries fit inside one video/part at this
    project's narration pace — the thing Section 2 says must drive list
    size, not the other way around."""
    runtime_seconds = runtime_seconds if runtime_seconds is not None else target_runtime_seconds()
    available_words = max(runtime_seconds * WORDS_PER_SECOND - HOOK_OUTRO_OVERHEAD_WORDS, WORDS_PER_ENTRY)
    return max(1, int(available_words // WORDS_PER_ENTRY))


def split_into_parts(candidates: list, per_part: int) -> list:
    return [candidates[i:i + per_part] for i in range(0, len(candidates), per_part)]


def _resolve_and_filter(db, raw_items: list, kind: str, date_str: str, category: str,
                        india_only: bool = None) -> list:
    """kind: 'birth' | 'death' | 'event'. Resolves QIDs, runs
    cross-verification, routes conflicts to review, and (for
    births/deaths) filters by India citizenship when india_only is set."""
    out = []
    for item in raw_items:
        pages = item.get("pages") or []
        title = pages[0].get("title") if pages else None
        candidate = {
            "text": item.get("text", ""), "year": item.get("year"),
            "wikipedia_title": title,
        }
        qid = wikidata_source.resolve_qid(title) if title else None
        candidate["qid"] = qid

        if india_only is not None and qid:
            is_in = wikidata_source.is_indian(qid)
            if is_in != india_only:
                continue
        elif india_only is True and not qid:
            continue   # can't confirm India-specific without a QID — skip rather than guess

        if kind in ("birth", "death"):
            v = verification.verify_candidate(candidate, qid, kind)
        else:
            v = verification.verify_event(candidate)

        if not v["verified"]:
            verification.route_to_review_queue(db, date_str, category, candidate, v["conflict"])
            continue

        candidate["research_notes"] = v["notes"]
        out.append(candidate)
    return out


def _is_india_related_event(text: str) -> bool:
    return bool(re.search(r"\bIndia\b|\bIndian\b", text or "", re.IGNORECASE))


def build_batch_for_date(db, target_date: date = None) -> list:
    """Returns a list of job dicts, one per video/part to generate today:
        {"category": "born_today" | "died_today" | "born_died_india" |
                      "history_world" | "history_india",
         "part_number": int | None,
         "candidates": [...]}
    Categories with zero surviving candidates are simply omitted — a thin
    or empty day is a legitimate outcome (Section 2), never an error.
    """
    target_date = target_date or date.today()
    date_str = target_date.isoformat()
    raw = wikidata_source.fetch_on_this_day(target_date.month, target_date.day)
    per_part = entries_per_part()
    jobs = []

    # Cap raw candidates BEFORE the expensive per-candidate resolution (each
    # one costs a Wikipedia QID lookup + a Wikidata SPARQL call) — slicing
    # AFTER resolving, as this used to do, meant resolving the entire raw
    # "on this day" list (hundreds of entries on a busy date) and is what
    # caused the 429 storm on 2026-10-13. wikidata_source.py's own caching
    # means re-resolving the same raw slice for the India-specific pass
    # below costs zero extra network calls.
    raw_births = raw["births"][:MAX_CANDIDATES_CONSIDERED]
    raw_deaths = raw["deaths"][:MAX_CANDIDATES_CONSIDERED]
    raw_events = raw["events"][:MAX_CANDIDATES_CONSIDERED]

    # 1. Born Today (Global) ────────────────────────────────────────────
    born_global = _resolve_and_filter(db, raw_births, "birth", date_str, "born_today")
    born_global = notability.rank_candidates(born_global, "wikipedia_title")
    for i, part in enumerate(split_into_parts(born_global, per_part), start=1):
        jobs.append({"category": "born_today", "part_number": i if len(born_global) > per_part else None,
                     "candidates": part})

    # 2. Died Today (Global) ─────────────────────────────────────────────
    died_global = _resolve_and_filter(db, raw_deaths, "death", date_str, "died_today")
    died_global = notability.rank_candidates(died_global, "wikipedia_title")
    for i, part in enumerate(split_into_parts(died_global, per_part), start=1):
        jobs.append({"category": "died_today", "part_number": i if len(died_global) > per_part else None,
                     "candidates": part})

    # 3. Born/Died Today (India-specific) ────────────────────────────────
    born_in = _resolve_and_filter(db, raw_births, "birth", date_str, "born_died_india", india_only=True)
    died_in = _resolve_and_filter(db, raw_deaths, "death", date_str, "born_died_india", india_only=True)
    india_people = notability.rank_candidates(born_in + died_in, "wikipedia_title")
    for i, part in enumerate(split_into_parts(india_people, per_part), start=1):
        jobs.append({"category": "born_died_india", "part_number": i if len(india_people) > per_part else None,
                     "candidates": part})

    # 4. This Day in History — split World / India only if volume justifies it ──
    events = _resolve_and_filter(db, raw_events, "event", date_str, "history")
    events_india = [e for e in events if _is_india_related_event(e["text"])]
    events_world = [e for e in events if e not in events_india]
    events_india = notability.rank_candidates(events_india, "wikipedia_title")
    events_world = notability.rank_candidates(events_world, "wikipedia_title")

    # Sub-split only when India has enough of its own content for a full
    # entry-count video; otherwise keep everything in one combined "history" run.
    if len(events_india) >= max(3, per_part // 2):
        for i, part in enumerate(split_into_parts(events_world, per_part), start=1):
            jobs.append({"category": "history_world", "part_number": i if len(events_world) > per_part else None,
                         "candidates": part})
        for i, part in enumerate(split_into_parts(events_india, per_part), start=1):
            jobs.append({"category": "history_india", "part_number": i if len(events_india) > per_part else None,
                         "candidates": part})
    else:
        combined = notability.rank_candidates(events_world + events_india, "wikipedia_title")
        for i, part in enumerate(split_into_parts(combined, per_part), start=1):
            jobs.append({"category": "history", "part_number": i if len(combined) > per_part else None,
                         "candidates": part})

    return [j for j in jobs if j["candidates"]]
