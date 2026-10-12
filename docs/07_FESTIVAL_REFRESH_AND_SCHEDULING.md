# 7. Festival Calendar Refresh + How Scheduling Works

## Why lunar festivals can't be hardcoded

Diwali, Eid al-Fitr, Eid al-Adha, and Gurpurab/Guru Nanak Jayanti all
shift every year on non-Gregorian calendars. `engine/observances.py`
ships with its `observances_lunar` table **empty on purpose** — hand
guessing multi-year dates into source code is exactly the mistake this
step avoids.

## Set it up (2 minutes)

1. [calendarific.com/signup](https://calendarific.com/signup) → free
   tier, 500 calls/month, no card.
2. Copy the API key → `.env` and GitHub secrets: `CALENDARIFIC_API_KEY=...`
3. Run once locally to seed this year + next year immediately, rather
   than waiting for the 1st of next month:
   ```
   python -m engine.observances --refresh
   ```
4. After that, `.github/workflows/festival-refresh.yml` re-runs this
   automatically on the 1st of every month (monthly rather than strictly
   annual, so one missed/failed run doesn't leave the calendar stale for
   a whole year — each run just re-confirms the same dates).

## Skipping this

If you leave `CALENDARIFIC_API_KEY` blank, the "Today's Observance"
category simply never includes a shifting festival — it still covers
every FIXED-date UN International Day (Women's Day, Men's Day, World
Animal Day, International Day of Forests, and the rest of
`FIXED_DATE_OBSERVANCES` in `engine/observances.py`) with zero setup.

## Manually seeding a date (no API key route)

You can also just insert a row yourself in Supabase's Table Editor,
table `observances_lunar`:

| year | month | day | name | tone |
|---|---|---|---|---|
| 2026 | 11 | 8 | Diwali | celebratory |

(Check the real date for this year from any panchang/calendar site —
this project deliberately doesn't ship a guessed date here.)

## How the posting schedule actually works

Section 5 of the build spec: post between **11 PM and 5 AM** local time,
ascending, at least 20-30 minutes apart, pre-generated 2-3 days ahead.

- `engine/orchestrator.py` runs once a day and generates **every**
  video/part for a date 2 days out (`--ahead-days 2`), so a bad
  generation day never threatens a near-term slot.
- `engine/scheduler.py` then gives each surviving video a `scheduled_at`
  time inside that night's posting window, 25 minutes apart, respecting
  your daily upload cap (`MAX_UPLOADS_PER_DAY`, default 6). Anything over
  the cap is automatically queued into the **next** night's window
  instead of being dropped.
- `engine/publish_queue.py` runs hourly and uploads whatever's
  `scheduled_at` has passed — it is not itself the thing deciding
  "20-30 minutes apart," it's just checking the clock often enough not
  to miss a slot that was already decided at generation time.

Change the channel's local timezone (used for both the posting window
and the daily-cap "day") in `engine/daycycle.py`'s `DEFAULT_LOCAL_TZ`
(defaults to `Asia/Kolkata`).

## Repeat dates, one year later

Section 5: a video's content can legitimately repeat only on the exact
same calendar date the following year — and even then, it must be
**regenerated fresh**, never the old render reused verbatim.
`engine/duplicate_check.py`'s `same_date_last_year()` simply confirms a
prior video exists for that slot; the orchestrator always calls
`script_generator` again regardless, so next year's video always carries
next year's actual date references rather than stale ones.
