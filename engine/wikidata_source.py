"""
wikidata_source.py — the day's raw candidate facts, free and keyless.
=======================================================================
Fact source for Section 4 of the build spec: Wikidata SPARQL + Wikipedia's
"On this day" feed. No API key, no signup, no rate-limit headaches for
this project's light daily call volume.

WHAT THIS RETURNS
`fetch_on_this_day(month, day)` gives raw candidates for all four content
categories at once: births, deaths, events (+ holidays, used by
observances.py separately). Each candidate carries a Wikipedia page title
plus — once resolved via `resolve_qid()` — its Wikidata QID, which is the
anchor every other module (notability ranking, cross-verification, and
crucially visual_matcher.py's image lookup) keys off of. Section 4 of the
spec is explicit that images must be tied to THIS SAME QID, never a
generic search, specifically to avoid showing the wrong person's photo.

INDIA FILTER
`country_of_citizenship(qid)` runs a small, targeted Wikidata SPARQL query
(P27 = country of citizenship) so topic_assembler.py can build the
"India-specific" category (Section 2, item 3) from genuine Wikidata facts
rather than guessing from a name.
"""
import time

import requests

REST_BASE = "https://en.wikipedia.org/api/rest_v1"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
USER_AGENT = "DailyHistoryShorts/1.0 (free educational short-form video project)"
REQUEST_TIMEOUT = 15

INDIA_QID = "Q668"

# ── Pacing + backoff ──────────────────────────────────────────────────────
# Wikipedia/Wikidata are free and keyless, which makes them the easiest
# thing in this pipeline to accidentally rate-limit: a single busy day's
# raw "on this day" list can run into the hundreds of candidates, and
# firing that many requests back-to-back with no pacing reliably trips a
# 429 partway through and silently drops every candidate after that point
# (this is exactly what happened on 2026-10-13's test run — 366 failed
# lookups in one batch). _get() below paces every call and retries once
# or twice on a 429 before giving up; topic_assembler.py separately caps
# how many raw candidates even reach this module (see MAX_CANDIDATES_CONSIDERED
# there) so the two fixes together bound both the rate AND the volume.
_MIN_INTERVAL_SECONDS = 0.4
_last_request_at = [0.0]


def _throttle():
    elapsed = time.monotonic() - _last_request_at[0]
    if elapsed < _MIN_INTERVAL_SECONDS:
        time.sleep(_MIN_INTERVAL_SECONDS - elapsed)
    _last_request_at[0] = time.monotonic()


def _get(url: str, params: dict = None, timeout: int = REQUEST_TIMEOUT,
          max_attempts: int = 3, extra_headers: dict = None):
    headers = {"User-Agent": USER_AGENT}
    if extra_headers:
        headers.update(extra_headers)
    last_exc = None
    for attempt in range(1, max_attempts + 1):
        _throttle()
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=timeout)
            if resp.status_code == 429 and attempt < max_attempts:
                wait = 2 * attempt
                print(f"[wikidata_source] 429, backing off {wait}s (attempt {attempt}/{max_attempts})...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            last_exc = e
            if attempt < max_attempts and "429" in str(e):
                wait = 2 * attempt
                time.sleep(wait)
                continue
            raise
    raise last_exc


# In-process caches — a single run resolves the same person twice (the
# India-specific category re-filters the same raw births/deaths list), so
# memoizing here means the second pass costs zero extra network calls.
_qid_cache = {}
_citizenship_cache = {}
_birth_death_cache = {}
_image_claim_cache = {}


def fetch_on_this_day(month: int, day: int) -> dict:
    """Returns {"births": [...], "deaths": [...], "events": [...],
    "holidays": [...]}, each item shaped like Wikipedia's own REST response:
    {"text": "...", "year": 1452, "pages": [{"title": "...", "...": ...}]}.

    Returns empty lists (never raises) on any failure — callers treat a
    thin or empty day exactly like a real thin day (Section 2's "a day
    with 2 notable people still gets a full-quality video" already
    assumes this can legitimately happen).
    """
    out = {"births": [], "deaths": [], "events": [], "holidays": []}
    for kind in out.keys():
        try:
            resp = _get(f"{REST_BASE}/feed/onthisday/{kind}/{month:02d}/{day:02d}")
            out[kind] = resp.json().get(kind, [])
        except Exception as e:
            print(f"[wikidata_source] On-this-day '{kind}' fetch failed: {e}")
    return out


def resolve_qid(wikipedia_title: str) -> str:
    """Resolves an English Wikipedia page title to its Wikidata QID via
    pageprops. Returns None if the page has no linked Wikidata item or the
    lookup fails — callers must treat that as 'skip this candidate's
    QID-anchored image/verification', never as a hard error for the batch.
    """
    if not wikipedia_title:
        return None
    if wikipedia_title in _qid_cache:
        return _qid_cache[wikipedia_title]
    qid = None
    try:
        resp = _get(
            WIKIPEDIA_API,
            params={
                "action": "query", "prop": "pageprops", "titles": wikipedia_title,
                "format": "json", "redirects": 1,
            },
        )
        pages = resp.json().get("query", {}).get("pages", {})
        for page in pages.values():
            found = (page.get("pageprops") or {}).get("wikibase_item")
            if found:
                qid = found
                break
    except Exception as e:
        print(f"[wikidata_source] QID lookup failed for '{wikipedia_title}': {e}")
    _qid_cache[wikipedia_title] = qid
    return qid


def _sparql(query: str) -> list:
    resp = _get(
        WIKIDATA_SPARQL, params={"query": query, "format": "json"},
        extra_headers={"Accept": "application/sparql-results+json"},
    )
    return resp.json().get("results", {}).get("bindings", [])


def country_of_citizenship(qid: str) -> list:
    """Returns a list of {"qid": "...", "label": "..."} countries of
    citizenship (Wikidata P27) for `qid`. Empty list on no data or failure."""
    if not qid:
        return []
    if qid in _citizenship_cache:
        return _citizenship_cache[qid]
    query = f"""
    SELECT ?country ?countryLabel WHERE {{
      wd:{qid} wdt:P27 ?country .
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    """
    try:
        rows = _sparql(query)
        result = [{"qid": r["country"]["value"].rsplit("/", 1)[-1], "label": r["countryLabel"]["value"]}
                  for r in rows]
    except Exception as e:
        print(f"[wikidata_source] Citizenship lookup failed for {qid}: {e}")
        result = []
    _citizenship_cache[qid] = result
    return result


def is_indian(qid: str) -> bool:
    return any(c["qid"] == INDIA_QID for c in country_of_citizenship(qid))


def birth_death_years(qid: str) -> dict:
    """Returns {"birth_year": int|None, "death_year": int|None} straight
    from Wikidata's own structured statements (P569/P570) — this is the
    'Wikidata' leg of the three-way cross-check in verification.py, kept
    separate from the free-text 'On this day' blurb on purpose."""
    if not qid:
        return {"birth_year": None, "death_year": None}
    if qid in _birth_death_cache:
        return _birth_death_cache[qid]
    query = f"""
    SELECT ?birth ?death WHERE {{
      OPTIONAL {{ wd:{qid} wdt:P569 ?birth . }}
      OPTIONAL {{ wd:{qid} wdt:P570 ?death . }}
    }}
    """
    try:
        rows = _sparql(query)
        if not rows:
            result = {"birth_year": None, "death_year": None}
        else:
            row = rows[0]
            by = int(row["birth"]["value"][:4]) if "birth" in row else None
            dy = int(row["death"]["value"][:4]) if "death" in row else None
            result = {"birth_year": by, "death_year": dy}
    except Exception as e:
        print(f"[wikidata_source] Birth/death year lookup failed for {qid}: {e}")
        result = {"birth_year": None, "death_year": None}
    _birth_death_cache[qid] = result
    return result


def image_claim(qid: str) -> str:
    """Returns the Commons filename from Wikidata's own P18 (image) claim
    for `qid`, or None. This is the MOST reliable QID-anchored image —
    visual_matcher.py tries this first, before any Commons search, because
    it is the subject's own curated portrait rather than a search result."""
    if not qid:
        return None
    if qid in _image_claim_cache:
        return _image_claim_cache[qid]
    query = f"""
    SELECT ?image WHERE {{ wd:{qid} wdt:P18 ?image . }} LIMIT 1
    """
    filename = None
    try:
        rows = _sparql(query)
        if rows:
            url = rows[0]["image"]["value"]
            filename = requests.utils.unquote(url.rsplit("/", 1)[-1])
    except Exception as e:
        print(f"[wikidata_source] P18 image claim lookup failed for {qid}: {e}")
    _image_claim_cache[qid] = filename
    return filename
