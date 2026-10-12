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
import requests

REST_BASE = "https://en.wikipedia.org/api/rest_v1"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
USER_AGENT = "DailyHistoryShorts/1.0 (free educational short-form video project)"
REQUEST_TIMEOUT = 15

INDIA_QID = "Q668"


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
            resp = requests.get(
                f"{REST_BASE}/feed/onthisday/{kind}/{month:02d}/{day:02d}",
                headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
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
    try:
        resp = requests.get(
            WIKIPEDIA_API,
            params={
                "action": "query", "prop": "pageprops", "titles": wikipedia_title,
                "format": "json", "redirects": 1,
            },
            headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {})
        for page in pages.values():
            qid = (page.get("pageprops") or {}).get("wikibase_item")
            if qid:
                return qid
    except Exception as e:
        print(f"[wikidata_source] QID lookup failed for '{wikipedia_title}': {e}")
    return None


def _sparql(query: str) -> list:
    resp = requests.get(
        WIKIDATA_SPARQL, params={"query": query, "format": "json"},
        headers={"User-Agent": USER_AGENT, "Accept": "application/sparql-results+json"},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json().get("results", {}).get("bindings", [])


def country_of_citizenship(qid: str) -> list:
    """Returns a list of {"qid": "...", "label": "..."} countries of
    citizenship (Wikidata P27) for `qid`. Empty list on no data or failure."""
    if not qid:
        return []
    query = f"""
    SELECT ?country ?countryLabel WHERE {{
      wd:{qid} wdt:P27 ?country .
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    """
    try:
        rows = _sparql(query)
        return [{"qid": r["country"]["value"].rsplit("/", 1)[-1], "label": r["countryLabel"]["value"]}
                for r in rows]
    except Exception as e:
        print(f"[wikidata_source] Citizenship lookup failed for {qid}: {e}")
        return []


def is_indian(qid: str) -> bool:
    return any(c["qid"] == INDIA_QID for c in country_of_citizenship(qid))


def birth_death_years(qid: str) -> dict:
    """Returns {"birth_year": int|None, "death_year": int|None} straight
    from Wikidata's own structured statements (P569/P570) — this is the
    'Wikidata' leg of the three-way cross-check in verification.py, kept
    separate from the free-text 'On this day' blurb on purpose."""
    if not qid:
        return {"birth_year": None, "death_year": None}
    query = f"""
    SELECT ?birth ?death WHERE {{
      OPTIONAL {{ wd:{qid} wdt:P569 ?birth . }}
      OPTIONAL {{ wd:{qid} wdt:P570 ?death . }}
    }}
    """
    try:
        rows = _sparql(query)
        if not rows:
            return {"birth_year": None, "death_year": None}
        row = rows[0]
        by = int(row["birth"]["value"][:4]) if "birth" in row else None
        dy = int(row["death"]["value"][:4]) if "death" in row else None
        return {"birth_year": by, "death_year": dy}
    except Exception as e:
        print(f"[wikidata_source] Birth/death year lookup failed for {qid}: {e}")
        return {"birth_year": None, "death_year": None}


def image_claim(qid: str) -> str:
    """Returns the Commons filename from Wikidata's own P18 (image) claim
    for `qid`, or None. This is the MOST reliable QID-anchored image —
    visual_matcher.py tries this first, before any Commons search, because
    it is the subject's own curated portrait rather than a search result."""
    if not qid:
        return None
    query = f"""
    SELECT ?image WHERE {{ wd:{qid} wdt:P18 ?image . }} LIMIT 1
    """
    try:
        rows = _sparql(query)
        if rows:
            url = rows[0]["image"]["value"]
            return requests.utils.unquote(url.rsplit("/", 1)[-1])
    except Exception as e:
        print(f"[wikidata_source] P18 image claim lookup failed for {qid}: {e}")
    return None
