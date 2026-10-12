"""
research.py — verified factual grounding pulled from Wikipedia's own
prose, so the script never has to rely on the model's memory for a date,
name, or figure. Adapted directly from the reference project's module —
same source, same reasoning, same degrade-to-nothing-safely contract.
"""
import re
import urllib.parse
import requests

WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
REQUEST_TIMEOUT = 12
MAX_PAGES = 2
MAX_EXTRACT_CHARS = 2200
USER_AGENT = "DailyHistoryShorts/1.0 (free educational short-form video project)"


def _search_titles(query: str, limit: int = 3) -> list:
    try:
        resp = requests.get(
            WIKIPEDIA_API,
            params={"action": "query", "list": "search", "srsearch": query,
                    "srlimit": limit, "format": "json", "srprop": ""},
            headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return [r["title"] for r in resp.json().get("query", {}).get("search", [])]
    except Exception as e:
        print(f"[research] Wikipedia search failed for {query!r}: {e}")
        return []


def _fetch_extract(title: str) -> dict:
    try:
        resp = requests.get(
            WIKIPEDIA_API,
            params={"action": "query", "prop": "extracts", "explaintext": 1,
                    "exsectionformat": "plain", "titles": title, "format": "json", "redirects": 1},
            headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
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
