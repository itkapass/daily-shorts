"""
notability.py — ranks today's candidates by actual public interest, free.
============================================================================
Section 4 of the build spec: "Wikipedia Pageviews API — ranks candidates
so the 'how many people' decision (Section 2) is data-driven, not
arbitrary." No API key, no signup.
"""
import requests
from datetime import datetime, timedelta

PAGEVIEWS_API = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
USER_AGENT = "DailyHistoryShorts/1.0 (free educational short-form video project)"
REQUEST_TIMEOUT = 12
LOOKBACK_DAYS = 30   # trailing 30-day average — smooths out a one-off news spike


def pageviews_score(wikipedia_title: str) -> int:
    """Average daily pageviews over the trailing LOOKBACK_DAYS. Returns 0
    on any failure — a candidate with no measurable score simply sorts to
    the bottom rather than blocking the batch."""
    if not wikipedia_title:
        return 0
    article = wikipedia_title.replace(" ", "_")
    end = datetime.utcnow().date() - timedelta(days=2)   # pageviews data lags ~1-2 days
    start = end - timedelta(days=LOOKBACK_DAYS)
    try:
        resp = requests.get(
            f"{PAGEVIEWS_API}/en.wikipedia/all-access/all-agents/{article}/daily/"
            f"{start.strftime('%Y%m%d')}/{end.strftime('%Y%m%d')}",
            headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code == 404:
            return 0   # no pageviews data for this title (very obscure, or a redirect)
        resp.raise_for_status()
        items = resp.json().get("items", [])
        if not items:
            return 0
        return round(sum(i["views"] for i in items) / len(items))
    except Exception as e:
        print(f"[notability] Pageviews lookup failed for '{wikipedia_title}': {e}")
        return 0


def rank_candidates(candidates: list, title_key: str = "wikipedia_title") -> list:
    """Sorts `candidates` (each a dict with a Wikipedia title under
    `title_key`) by descending pageviews score, annotating each with its
    score. Pure, no side effects beyond the network calls — safe to call
    on a freshly-fetched candidate list before any DB writes happen."""
    scored = []
    for c in candidates:
        score = pageviews_score(c.get(title_key))
        scored.append({**c, "notability_score": score})
    scored.sort(key=lambda c: c["notability_score"], reverse=True)
    return scored
