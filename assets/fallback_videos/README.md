# Fallback videos — local staging folder

This folder is just a convenient place to **keep the raw files** on your
own computer. The pipeline itself never reads from here directly — it
reads from the `fallback_videos` table in Supabase, which stores a
**public URL**, not a local path.

## Why this exists (Section 10 of the build spec)

If a category fails to generate twice in a row, `engine/scheduler.py`
substitutes a video from this table instead of leaving that night's slot
empty. The table ships empty — there's nothing to substitute until you
add at least one per category.

## One-time setup, per category

1. Make (or reuse) one generic, evergreen 30-60s video for the category —
   something that stays true regardless of date (e.g. a "did you know"
   style clip, not tied to a specific day).
2. Save it here, e.g. `assets/fallback_videos/science_generic_01.mp4`.
3. Upload that file once to your R2 bucket (or Supabase Storage) the same
   way any other asset gets uploaded there — see
   [docs/02_CLOUDFLARE_R2_SETUP.md](../../docs/02_CLOUDFLARE_R2_SETUP.md).
   Copy the public URL it gives you.
4. In Supabase → Table Editor → `fallback_videos`, insert one row:

   | column | value |
   |---|---|
   | `category` | e.g. `science` (must match the category name used in `engine/topic_assembler.py`) |
   | `storage_url` | the public URL from step 3 |
   | `title` | a real YouTube title for this video |
   | `is_generic` | `true` if it can stand in for ANY category, `false` if only for the one in `category` |

Repeat for as many categories as you want covered. This is entirely
optional — skipping it just means a thin night skips that category's
video instead of substituting one, which is still safe.
