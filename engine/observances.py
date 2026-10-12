"""
observances.py — Today's Observance category + the opening/closing wish
segment (Sections 2 item 5, and Section 3).
============================================================================
THREE TIERS, EACH HANDLED DIFFERENTLY, PER SECTION 3's INSTRUCTION
  1. FIXED_DATE_OBSERVANCES — UN International Days with a permanent
     calendar date (e.g. Women's Day = March 8). Hardcoded ONCE, here,
     because they never move. This list intentionally goes well beyond
     the festival examples (Diwali/Eid/Pongal/Gurpurab) — it is the "full
     UN-designated International Days calendar" the build spec calls for
     in Section 2/3, not just a handful of headline days. It is still not
     literally exhaustive (the UN's own list runs to ~150 entries and is
     revised by the General Assembly over time) — cross-check and extend
     it against https://www.un.org/en/observances/list-days-weeks
     whenever you want to add more.
  2. COMPUTED_OBSERVANCES — a handful of UN days defined by RULE rather
     than a fixed date (e.g. World Migratory Bird Day = the second
     Saturday of May AND of October; World Habitat Day = the first
     Monday of October). These are still fully deterministic calendar
     math, just not a plain MM-DD, so they're computed here rather than
     hardcoded per year.
  3. LUNAR / SHIFTING FESTIVALS (Diwali, Eid al-Fitr, Eid al-Adha,
     Gurpurab/Guru Nanak Jayanti) — these genuinely shift year to year on
     non-Gregorian calendars and must NEVER be hardcoded permanently
     (Section 3's explicit instruction). They live in the
     `observances_lunar` Supabase table, refreshed once a year by
     `refresh_lunar_festivals()` (wired to the festival-refresh.yml
     GitHub Action — see docs/07). This file ships with that table
     EMPTY, on purpose: hand-guessing multi-year lunar dates into source
     code is exactly the mistake Section 3 is warning against. Run the
     refresh (needs one free Calendarific API key, see docs/07) or
     insert this year's real dates into the table yourself as a one-time
     bootstrap before relying on the Observance category.
"""
from datetime import date, timedelta

from engine.config import get

# tone: "celebratory" (greet/congratulate) | "awareness" (neutral "today is")
#       | "solemn" (respectful "today marks", never "happy")
FIXED_DATE_OBSERVANCES = [
    (1, 4,  "World Braille Day", "awareness"),
    (1, 24, "International Day of Education", "awareness"),
    (1, 27, "International Holocaust Remembrance Day", "solemn"),
    (2, 4,  "World Cancer Day", "awareness"),
    (2, 6,  "International Day of Zero Tolerance for Female Genital Mutilation", "solemn"),
    (2, 11, "International Day of Women and Girls in Science", "celebratory"),
    (2, 13, "World Radio Day", "awareness"),
    (2, 20, "World Day of Social Justice", "awareness"),
    (2, 21, "International Mother Language Day", "celebratory"),
    (3, 1,  "Zero Discrimination Day", "awareness"),
    (3, 3,  "World Wildlife Day", "celebratory"),
    (3, 8,  "International Women's Day", "celebratory"),
    (3, 20, "International Day of Happiness", "celebratory"),
    (3, 21, "International Day of Forests", "celebratory"),
    (3, 21, "World Down Syndrome Day", "celebratory"),
    (3, 21, "International Day for the Elimination of Racial Discrimination", "awareness"),
    (3, 22, "World Water Day", "awareness"),
    (3, 23, "World Meteorological Day", "awareness"),
    (3, 24, "World Tuberculosis Day", "awareness"),
    (4, 2,  "World Autism Awareness Day", "awareness"),
    (4, 7,  "World Health Day", "awareness"),
    (4, 22, "International Mother Earth Day", "celebratory"),
    (4, 23, "World Book and Copyright Day", "celebratory"),
    (4, 26, "World Intellectual Property Day", "awareness"),
    (4, 28, "World Day for Safety and Health at Work", "awareness"),
    (5, 1,  "International Workers' Day", "celebratory"),
    (5, 3,  "World Press Freedom Day", "awareness"),
    (5, 15, "International Day of Families", "celebratory"),
    (5, 17, "World Telecommunication and Information Society Day", "awareness"),
    (5, 21, "World Day for Cultural Diversity for Dialogue and Development", "celebratory"),
    (5, 22, "International Day for Biological Diversity", "awareness"),
    (5, 29, "International Day of UN Peacekeepers", "solemn"),
    (5, 31, "World No Tobacco Day", "awareness"),
    (6, 1,  "Global Day of Parents", "celebratory"),
    (6, 4,  "International Day of Innocent Children Victims of Aggression", "solemn"),
    (6, 5,  "World Environment Day", "awareness"),
    (6, 8,  "World Oceans Day", "awareness"),
    (6, 12, "World Day Against Child Labour", "awareness"),
    (6, 14, "World Blood Donor Day", "celebratory"),
    (6, 17, "World Day to Combat Desertification and Drought", "awareness"),
    (6, 20, "World Refugee Day", "solemn"),
    (6, 21, "International Day of Yoga", "celebratory"),
    (6, 23, "International Widows' Day", "solemn"),
    (6, 26, "International Day Against Drug Abuse and Illicit Trafficking", "awareness"),
    (7, 11, "World Population Day", "awareness"),
    (7, 15, "World Youth Skills Day", "celebratory"),
    (7, 18, "Nelson Mandela International Day", "celebratory"),
    (7, 30, "International Day of Friendship", "celebratory"),
    (7, 30, "World Day against Trafficking in Persons", "solemn"),
    (8, 9,  "International Day of the World's Indigenous Peoples", "celebratory"),
    (8, 12, "International Youth Day", "celebratory"),
    (8, 19, "World Humanitarian Day", "solemn"),
    (8, 23, "International Day for the Remembrance of the Slave Trade and its Abolition", "solemn"),
    (8, 30, "International Day of the Victims of Enforced Disappearances", "solemn"),
    (9, 5,  "International Day of Charity", "celebratory"),
    (9, 8,  "International Literacy Day", "celebratory"),
    (9, 10, "World Suicide Prevention Day", "awareness"),
    (9, 15, "International Day of Democracy", "awareness"),
    (9, 16, "International Day for the Preservation of the Ozone Layer", "awareness"),
    (9, 21, "International Day of Peace", "celebratory"),
    (9, 27, "World Tourism Day", "celebratory"),
    (9, 29, "International Day of Awareness of Food Loss and Waste", "awareness"),
    (10, 1, "International Day of Older Persons", "celebratory"),
    (10, 2, "International Day of Non-Violence", "awareness"),
    (10, 4, "World Animal Day", "celebratory"),
    (10, 5, "World Teachers' Day", "celebratory"),
    (10, 9, "World Post Day", "awareness"),
    (10, 10, "World Mental Health Day", "awareness"),
    (10, 11, "International Day of the Girl Child", "celebratory"),
    (10, 13, "International Day for Disaster Risk Reduction", "awareness"),
    (10, 15, "International Day of Rural Women", "celebratory"),
    (10, 16, "World Food Day", "awareness"),
    (10, 17, "International Day for the Eradication of Poverty", "awareness"),
    (10, 24, "United Nations Day", "celebratory"),
    (11, 10, "World Science Day for Peace and Development", "awareness"),
    (11, 14, "World Diabetes Day", "awareness"),
    (11, 16, "International Day for Tolerance", "awareness"),
    (11, 19, "International Men's Day", "celebratory"),
    (11, 19, "World Toilet Day", "awareness"),
    (11, 20, "Universal Children's Day", "celebratory"),
    (11, 20, "Africa Industrialization Day", "awareness"),
    (11, 21, "World Television Day", "celebratory"),
    (11, 25, "International Day for the Elimination of Violence against Women", "solemn"),
    (11, 29, "International Day of Solidarity with the Palestinian People", "solemn"),
    (12, 1, "World AIDS Day", "solemn"),
    (12, 2, "International Day for the Abolition of Slavery", "solemn"),
    (12, 3, "International Day of Persons with Disabilities", "celebratory"),
    (12, 5, "International Volunteer Day", "celebratory"),
    (12, 7, "International Civil Aviation Day", "awareness"),
    (12, 9, "International Anti-Corruption Day", "awareness"),
    (12, 10, "Human Rights Day", "awareness"),
    (12, 11, "International Mountain Day", "celebratory"),
    (12, 12, "International Universal Health Coverage Day", "awareness"),
    (12, 18, "International Migrants Day", "awareness"),
    (12, 20, "International Human Solidarity Day", "celebratory"),
]

# name, month, weekday (0=Mon..6=Sun), n (1st/2nd/...), tone
COMPUTED_OBSERVANCES = [
    ("World Habitat Day", 10, 0, 1, "awareness"),            # 1st Monday of October
    ("World Migratory Bird Day", 5, 5, 2, "celebratory"),    # 2nd Saturday of May
    ("World Migratory Bird Day", 10, 5, 2, "celebratory"),   # 2nd Saturday of October
    ("International Day of Families Week start", 5, 0, 3, "celebratory"),
]

# Custom greeting overrides for well-known festivals/days where a generic
# template would sound off. Matched case-insensitively by substring.
CUSTOM_GREETINGS = {
    "diwali":        ("Happy Diwali!", "Wishing you a joyful Diwali."),
    "eid al-fitr":   ("Eid Mubarak!", "Eid Mubarak to you and your family."),
    "eid al-adha":   ("Eid Mubarak!", "Eid Mubarak to you and your family."),
    "pongal":        ("Happy Pongal!", "Wishing you a prosperous Pongal."),
    "gurpurab":      ("Happy Gurpurab!", "Wishing you a blessed Gurpurab."),
    "guru nanak":    ("Happy Gurpurab!", "Wishing you a blessed Gurpurab."),
    "christmas":     ("Merry Christmas!", "Wishing you a Merry Christmas."),
    "women's day":   ("Happy International Women's Day!", "Celebrating women everywhere today."),
    "men's day":     ("Happy International Men's Day!", "Celebrating men everywhere today."),
}


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    d = date(year, month, 1)
    offset = (weekday - d.weekday()) % 7
    d += timedelta(days=offset + 7 * (n - 1))
    return d


def _wish_lines(name: str, tone: str) -> dict:
    needle = name.lower()
    for key, (open_line, close_line) in CUSTOM_GREETINGS.items():
        if key in needle:
            return {"open": open_line, "close": close_line}
    if tone == "celebratory":
        return {"open": f"Happy {name}!", "close": f"Wishing everyone a wonderful {name}."}
    if tone == "solemn":
        return {"open": f"Today marks {name}.", "close": f"Let's take a moment to remember {name}."}
    return {"open": f"Today is {name}.", "close": f"That's today's observance — {name}."}


def fixed_observances_for(month: int, day: int) -> list:
    return [{"name": n, "tone": t, "kind": "un_day_fixed", **_wish_lines(n, t)}
            for (m, d, n, t) in FIXED_DATE_OBSERVANCES if m == month and d == day]


def computed_observances_for(year: int, month: int, day: int) -> list:
    out = []
    for name, m, weekday, n, tone in COMPUTED_OBSERVANCES:
        if m != month:
            continue
        if _nth_weekday(year, m, weekday, n).day == day:
            out.append({"name": name, "tone": tone, "kind": "un_day_computed", **_wish_lines(name, tone)})
    return out


def lunar_observances_for(db, year: int, month: int, day: int) -> list:
    """Reads this year's shifting-festival dates from the `observances_lunar`
    table (populated by refresh_lunar_festivals() — see that function's
    docstring for why nothing is hardcoded here)."""
    try:
        rows = (db.table("observances_lunar").select("*")
                .eq("year", year).eq("month", month).eq("day", day).execute().data) or []
        return [{"name": r["name"], "tone": r.get("tone", "celebratory"), "kind": "lunar_festival",
                 **_wish_lines(r["name"], r.get("tone", "celebratory"))} for r in rows]
    except Exception as e:
        print(f"[observances] Could not read observances_lunar ({e}); treating today as having none.")
        return []


def todays_observances(db, target_date: date = None) -> list:
    target_date = target_date or date.today()
    out = fixed_observances_for(target_date.month, target_date.day)
    out += computed_observances_for(target_date.year, target_date.month, target_date.day)
    out += lunar_observances_for(db, target_date.year, target_date.month, target_date.day)
    return out


def refresh_lunar_festivals(db, year: int) -> int:
    """Pulls next year's Diwali / Eid al-Fitr / Eid al-Adha / Gurpurab
    dates from Calendarific's free tier (500 calls/month, no card — see
    docs/07) and upserts them into `observances_lunar`. Called by the
    yearly festival-refresh.yml GitHub Action, automated per Section 3's
    explicit instruction ("a scheduled job that pulls the next 12 months
    of festival dates from a maintained calendar API/source each year").

    Returns the number of rows written. Logs and returns 0 (never raises)
    if CALENDARIFIC_API_KEY is unset — the Observance category simply has
    no lunar festivals that year until a key is added or the table is
    seeded manually. This is intentionally a safe no-op, not a guess.
    """
    api_key = get("CALENDARIFIC_API_KEY")
    if not api_key:
        print("[observances] CALENDARIFIC_API_KEY not set — skipping lunar festival refresh. "
              "See docs/07_FESTIVAL_REFRESH_AND_SCHEDULING.md.")
        return 0

    import requests
    wanted = ["Diwali", "Eid al-Fitr", "Eid-Ul-Fitr", "Eid al-Adha", "Eid-Ul-Adha",
              "Guru Nanak Jayanti", "Gurpurab"]
    written = 0
    try:
        resp = requests.get(
            "https://calendarific.com/api/v2/holidays",
            params={"api_key": api_key, "country": "IN", "year": year, "type": "religious"},
            timeout=20,
        )
        resp.raise_for_status()
        holidays = resp.json().get("response", {}).get("holidays", [])
        for h in holidays:
            name = h.get("name", "")
            if not any(w.lower() in name.lower() for w in wanted):
                continue
            d = h.get("date", {}).get("iso", "")[:10]
            if not d:
                continue
            y, m, day = (int(p) for p in d.split("-"))
            db.table("observances_lunar").upsert({
                "year": y, "month": m, "day": day, "name": name, "tone": "celebratory",
                "source": "calendarific",
            }, on_conflict="year,month,day,name").execute()
            written += 1
        print(f"[observances] Refreshed {written} lunar festival date(s) for {year}.")
    except Exception as e:
        print(f"[observances] Lunar festival refresh failed: {e}")
    return written


if __name__ == "__main__":
    import argparse
    import json

    p = argparse.ArgumentParser(description="Observance calendar utilities")
    p.add_argument("--refresh", action="store_true",
                   help="Refresh lunar/shifting festival dates for this year and next (writes to Supabase)")
    args = p.parse_args()

    if args.refresh:
        from engine.supabase_client import get_db
        db = get_db()
        year = date.today().year
        refresh_lunar_festivals(db, year)
        refresh_lunar_festivals(db, year + 1)
    else:
        today = date.today()
        print(json.dumps(fixed_observances_for(today.month, today.day) +
                          computed_observances_for(today.year, today.month, today.day), indent=2))
