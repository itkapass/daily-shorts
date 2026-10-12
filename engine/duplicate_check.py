"""
duplicate_check.py — Section 5's repeat-date rule + general dedup.
============================================================================
"A video's content can only legitimately repeat the following year on the
same calendar date — when regenerating for a repeat date, refresh the
script/visuals with that year's actual date references rather than
reusing the prior year's render verbatim."

Two checks, adapted from the reference project's TF-IDF approach:
  1. same_date_last_year(): looks up last year's video for this exact
     category/part/date — if found, the orchestrator must regenerate a
     fresh script (never reuse the stored storyboard verbatim), which
     this function enforces by simply never returning old content, only
     a flag that a prior video exists.
  2. check_near_duplicate(): the general 30-day near-duplicate guard
     (TF-IDF cosine similarity), catching an accidental repeat script
     within the same rotation of candidates.
Fails OPEN: any internal error allows the video through rather than
blocking the whole day's generation over a broken dedup check.
"""
import json
from datetime import datetime, timedelta, timezone

SIMILARITY_THRESHOLD = 0.75
LOOKBACK_DAYS = 30


def _full_script_text(storyboard: dict) -> str:
    return " ".join(s.get("voice_text", "") for s in storyboard.get("scenes", []))


def same_date_last_year(db, category: str, part_number, date_str: str) -> dict:
    """Returns {"exists": bool, "job_id": str|None} for last year's video
    in this exact category/part/calendar-date slot."""
    try:
        d = datetime.fromisoformat(date_str).date()
        last_year = d.replace(year=d.year - 1).isoformat()
    except ValueError:
        return {"exists": False, "job_id": None}
    try:
        q = db.table("videos").select("job_id").eq("category", category).eq("scheduled_date", last_year)
        q = q.is_("part_number", "null") if part_number is None else q.eq("part_number", part_number)
        rows = q.execute().data or []
        return {"exists": bool(rows), "job_id": rows[0]["job_id"] if rows else None}
    except Exception as e:
        print(f"[duplicate_check] same_date_last_year check failed (allowing through): {e}")
        return {"exists": False, "job_id": None}


def check_near_duplicate(db, new_storyboard: dict, lookback_days: int = LOOKBACK_DAYS) -> dict:
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        new_text = _full_script_text(new_storyboard)
        if not new_text.strip():
            return {"is_duplicate": False, "similarity": 0.0, "matched_title": None}

        cutoff = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()
        rows = db.table("videos").select("title, storyboard").gte("created_at", cutoff).execute().data or []
        if not rows:
            return {"is_duplicate": False, "similarity": 0.0, "matched_title": None}

        history_texts, history_titles = [], []
        for row in rows:
            try:
                sb = row["storyboard"] if isinstance(row.get("storyboard"), dict) else json.loads(row.get("storyboard") or "{}")
            except (json.JSONDecodeError, TypeError):
                continue
            text = _full_script_text(sb)
            if text.strip():
                history_texts.append(text)
                history_titles.append(row.get("title", "(untitled)"))

        if not history_texts:
            return {"is_duplicate": False, "similarity": 0.0, "matched_title": None}

        corpus = history_texts + [new_text]
        matrix = TfidfVectorizer(stop_words="english").fit_transform(corpus)
        sims = cosine_similarity(matrix[-1], matrix[:-1])[0]
        best_idx, best_sim = int(sims.argmax()), float(sims.max())
        return {"is_duplicate": best_sim >= SIMILARITY_THRESHOLD, "similarity": round(best_sim, 3),
                "matched_title": history_titles[best_idx] if best_sim >= SIMILARITY_THRESHOLD else None}
    except Exception as e:
        print(f"[duplicate_check] Check failed, allowing video through (fail-open): {e}")
        return {"is_duplicate": False, "similarity": 0.0, "matched_title": None, "error": str(e)}
