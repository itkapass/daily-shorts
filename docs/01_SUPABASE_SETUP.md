# 1. Database Setup — Supabase

Supabase is the free database this project uses as its job queue (which
videos are rendering, approved, published) and small settings store. Free
tier: 500 MB database, 1 GB file storage (used only if you skip Cloudflare
R2 — see docs/02).

## Steps

1. Go to [supabase.com](https://supabase.com) → sign up (GitHub login is
   fastest) → **New Project**.
2. Pick any name/region, set a database password (you won't need it
   again — the API key is what the code actually uses), click **Create
   new project**. Wait ~2 minutes for it to provision.
3. Left sidebar → **SQL Editor** → **New query**.
4. Open `supabase/schema.sql` from this project, copy the whole file,
   paste it into the SQL editor, click **Run**.
   - You should see "Success. No rows returned." If you see an error
     about a table already existing, that's fine — the script is safe
     to re-run.
5. Left sidebar → **Project Settings** (gear icon) → **API**.
   - Copy **Project URL** → this is `SUPABASE_URL`.
   - Copy the **service_role** key (NOT the `anon` `public` key — this
     project's Python code uses the service key, which bypasses the
     security rules the schema sets up; the schema deliberately gives
     the public `anon` key zero access since there's no public-facing
     app here).
6. Paste both into your local `.env`:
   ```
   SUPABASE_URL=https://xxxxxxxx.supabase.co
   SUPABASE_SERVICE_KEY=eyJ...
   ```

## Verify it worked

```
python -m tools.selfcheck
```
Look for `[4/7] Supabase connection + schema` — it checks the connection
AND that every table from `schema.sql` actually exists.

## What's in the database

| Table | What it's for |
|---|---|
| `videos` | The queue: one row per video, from "rendering" through "approved" to "published". |
| `playlists` | Caches each category's YouTube playlist id so it's only created once. |
| `observances_lunar` | This year's/next year's Diwali, Eid, Gurpurab dates (empty until you run the festival refresh — see docs/07). |
| `review_queue` | Candidates where two sources disagreed on a date/fact — flagged for you to check by hand, never aired unverified. |
| `fallback_videos` | Your evergreen backup videos, used only if a category fails to generate twice in a row. Empty by default — see the note in docs/START_HERE.md about seeding at least one per category before fully trusting unattended operation. |
| `settings` | Small key/value store: daily API-usage counters, consecutive-failure counts. |

## Security note

`schema.sql` enables Row Level Security on every table with **no
policies**, which means the public `anon` key (the one that would ship in
a browser app) can read or write nothing at all. This project has no
admin panel or public frontend, so this is deliberately the simplest safe
setup — only your `service_role` key (used by the Python code, never
exposed anywhere public) can touch the data.
