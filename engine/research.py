"""
research.py — verified factual grounding pulled from Wikipedia's own
prose, so the script never has to rely on the model's memory for a date,
name, or figure. Adapted directly from the reference project's module —
same source, same reasoning, same degrade-to-nothing-safely contract.
"""
import re
import time
import urllib.parse
import requests

WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
REQUEST_TIMEOUT = 12
MAX_PAGES = 2
MAX_EXTRACT_CHARS = 2200
USER_AGENT = "DailyHistoryShorts/1.0 (free educational short-form video project)"

# ── Pacing + backoff ──────────────────────────────────────────────────────
# Same fix as wikidata_source.py's _get(): this module hits the same
# Wikipedia API host, so unthrottled calls here can trip the same 429s on a
# busy day with many topics needing research notes. See wikidata_source.py
# for the full story (366 failed lookups in one real run on 2026-10-13).
_MIN_INTERVAL_SECONDS = 0.4
_last_request_at = [0.0]


def _throttle():
    elapsed = time.monotonic() - _last_request_at[0]
    if elapsed < _MIN_INTERVAL_SECONDS:
        time.sleep(_MIN_INTERVAL_SECONDS - elapsed)
    _last_request_at[0] = time.monotonic()


def _get(url: str, params: dict = None, timeout: int = REQUEST_TIMEOUT, max_attempts: int = 3):
    headers = {"User-Agent": USER_AGENT}
    last_exc = None
    for attempt in range(1, max_attempts + 1):
        _throttle()
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=timeout)
            if resp.status_code == 429 and attempt < max_attempts:
                wait = 2 * attempt
                print(f"[research] 429, backing off {wait}s (attempt {attempt}/{max_attempts})...")
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


# A single run can ask for research notes on the same topic more than once
# (e.g. a topic reused across categories), so memoize by the exact query
# inputs — zero extra network calls on a repeat.
_notes_cache = {}


def _search_titles(query: str, limit: int = 3) -> list:
    try:
        resp = _get(
            WIKIPEDIA_API,
            params={"action": "query", "list": "search", "srsearch": query,
                    "srlimit": limit, "format": "json", "srprop": ""},
        )
        return [r["title"] for r in resp.json().get("query", {}).get("search", [])]
    except Exception as e:
        print(f"[research] Wikipedia search failed for {query!r}: {e}")
        return []


def _fetch_extract(title: str) -> dict:
    try:
        resp = _get(
            WIKIPEDIA_API,
            params={"action": "query", "prop": "extracts", "explaintext": 1,
                    "exsectionformat": "plain", "titles": title, "format": "json", "redirects": 1},
        )
        pages = resp.json().get("query", {}).get("pages", {})
        for page in pages.values():
            if "missing" in page:
                continue
            extract = (page.get("extract") or "").strip()
            if not extract:
                continue
            extract = re.sub(r"\n{3,}", "\n\n", extract)[:MAX_EXTRACT_CHARS]
            real_title = page.get("title", title)
            url = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(real_title.replace(" ", "_"))
            return {"title": real_title, "extract": extract, "url": url}
    except Exception as e:
        print(f"[research] Wikipedia extract failed for {title!r}: {e}")
    return {}


def fetch_research_notes(topic_name: str, topic_description: str = "") -> list:
    cache_key = (topic_name, topic_description)
    if cache_key in _notes_cache:
        return _notes_cache[cache_key]
    query = topic_name if not topic_description else f"{topic_name} {topic_description.split('.')[0]}"
    titles = _search_titles(query, limit=MAX_PAGES + 1)
    notes, seen = [], set()
    for title in titles:
        if len(notes) >= MAX_PAGES:
            break
        if title in seen:
            continue
        seen.add(title)
        page = _fetch_extract(title)
        if page:
            notes.append(page)
    _notes_cache[cache_key] = notes
    return notes


def prompt_block(notes: list) -> str:
    if not notes:
        return ""
    sections = "\n\n".join(f"[{n['title']}]\n{n['extract']}" for n in notes)
    return f"""

RESEARCH NOTES (real, sourced background — Wikipedia, {len(notes)} page(s)):
{sections}

HOW TO USE THESE NOTES:
Only state a specific number, date, name or record as fact if it appears in
the notes above. Paraphrase in your own words — never copy a sentence
verbatim. If the notes don't cover something you want to say, describe it
qualitatively instead of inventing a figure.
"""
