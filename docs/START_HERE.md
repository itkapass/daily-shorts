# Start Here

This is the **one checklist** that covers everything you need to do, once,
to get this channel running on autopilot. Each step links to a separate
doc with the full detail (screenshots-in-words, exact menu paths) — this
page is deliberately just the checklist so you can see your whole to-do
list in one place.

Total time if every service is new to you: **about 60-90 minutes**, done
once. After that, nothing here needs touching again except the two
genuinely recurring items marked **(recurring)** below.

---

## 0. Before you start

- A GitHub account, and this project pushed to a **GitHub repository you own**
  (private is fine). Everything below assumes you can get to
  **Settings → Secrets and variables → Actions** on that repo.
- A YouTube channel already created (even empty) under the Google account
  you want to publish from.
- Install locally, once, on your own computer (you only need your computer
  for the one-time setup steps marked **[local]** — the daily pipeline
  itself runs entirely on GitHub's servers):
  - [Python 3.11+](https://www.python.org/downloads/)
  - [FFmpeg](https://ffmpeg.org/download.html) — Windows: `winget install ffmpeg` (open a **new** terminal after); macOS: `brew install ffmpeg`; Linux: `sudo apt-get install ffmpeg`
  - Then: `pip install -r requirements.txt`

---

## 1. Database — Supabase (free) — **[local + web]**

Full detail: [docs/01_SUPABASE_SETUP.md](01_SUPABASE_SETUP.md)

- [ ] Create a free Supabase project.
- [ ] Copy the **Project URL** and **service_role key** (Settings → API).
- [ ] Open the SQL Editor, paste in `supabase/schema.sql`, click Run.
- [ ] Put both values in your local `.env` as `SUPABASE_URL` and `SUPABASE_SERVICE_KEY`.

## 2. Storage — Cloudflare R2 (free, optional but recommended) — **[web]**

Full detail: [docs/02_CLOUDFLARE_R2_SETUP.md](02_CLOUDFLARE_R2_SETUP.md)

- [ ] Create a free Cloudflare R2 bucket.
- [ ] Create an R2 API token, enable public access on the bucket.
- [ ] Put `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_PUBLIC_BASE` in `.env`.
- [ ] *Skip this whole section* and the pipeline automatically uses Supabase Storage instead (smaller free tier, but zero extra setup).

## 3. Script + voice keys — all free tier — **[web]**

Full detail: [docs/03_FREE_LLM_AND_TTS_KEYS.md](03_FREE_LLM_AND_TTS_KEYS.md)

- [ ] **Gemini** (required): get a free key at [aistudio.google.com](https://aistudio.google.com/) → `GEMINI_API_KEY`.
- [ ] **Groq** (recommended backup, ~2 min): [console.groq.com/keys](https://console.groq.com/keys) → `GROQ_API_KEY`.
- [ ] **Voice** — set up **Google Cloud TTS** (`GOOGLE_TTS_API_KEY`) first — ~2 min, free, and it's the one that defaults to an **Indian-English voice**, which matters a lot for retention with an Indian audience. Azure (`AZURE_TTS_KEY` + `AZURE_TTS_REGION`) is a good second one as backup, also Indian-accented by default. Kokoro (`pip install kokoro-onnx soundfile`, zero setup) is worth having too as the offline safety net, but it only has US/UK voices — see docs/03's note before treating it as your main voice.

## 4. YouTube publishing — **[local, needs a real browser]**

Full detail: [docs/04_YOUTUBE_OAUTH_SETUP.md](04_YOUTUBE_OAUTH_SETUP.md)

- [ ] Google Cloud Console → enable **YouTube Data API v3**.
- [ ] Create an OAuth client (Desktop app type), get Client ID + Secret.
- [ ] Put them in `.env`, then run: `python -m engine.publisher --setup`
- [ ] Copy the printed **refresh token** into `.env` as `YOUTUBE_REFRESH_TOKEN`.
- [ ] **Important:** set the OAuth consent screen to **"In production"** (not "Testing") — otherwise your refresh token expires every 7 days. Detail doc has the exact menu path.

## 5. Put it all on GitHub Actions — **[web]**

Full detail: [docs/05_GITHUB_ACTIONS_SECRETS.md](05_GITHUB_ACTIONS_SECRETS.md)

- [ ] Repo → Settings → Secrets and variables → Actions → add every value from your `.env` as a secret with the same name.
- [ ] Push this repo to GitHub. The four workflows under `.github/workflows/` start running on their own schedule — nothing else to turn on.

## 6. Verify everything before trusting it — **[local]**

- [ ] `python -m tools.selfcheck` — fixes anything it flags.
- [ ] `python -m engine.orchestrator --ahead-days 0` — generates one real batch for today right now, so you see output instead of waiting for tomorrow's cron.
- [ ] Check the Actions tab on GitHub: `generate.yml` and `publish.yml` both show green after their first scheduled run.
- [ ] **Seed at least one fallback video per category** (optional but recommended before you trust this unattended): drop a finished 30-60s evergreen video per category into `assets/fallback_videos/` locally (see the README there), upload it once to your R2/Supabase storage, then insert one row per video into the `fallback_videos` table (Supabase Table Editor) with that video's public URL, category, and title. Without this, two consecutive failures for a category just skip that night's video instead of substituting one — not broken, just less resilient.

## 7. Festival calendar (recurring, automated) — **[web, optional]**

Full detail: [docs/07_FESTIVAL_REFRESH_AND_SCHEDULING.md](07_FESTIVAL_REFRESH_AND_SCHEDULING.md)

- [ ] Get a free key at [calendarific.com/signup](https://calendarific.com/signup) → `CALENDARIFIC_API_KEY`, so Diwali/Eid/Gurpurab dates refresh themselves every month automatically.
- [ ] Or skip it — the Observance category just won't include shifting festivals until you add this.

## 8. The one thing you can't automate (do this later, when you need it)

YouTube's starting API quota caps you at **~6 uploads/day**. When you
outgrow that, request a quota increase — this needs a human-reviewed
Google form, so it can't be automated. See
[docs/05_GITHUB_ACTIONS_SECRETS.md](05_GITHUB_ACTIONS_SECRETS.md#quota-increase)
for the exact steps, when you're ready.

## 9. Optional paid upgrades (anytime later, zero code changes)

Full detail: [docs/06_PAID_UPGRADES_LATER.md](06_PAID_UPGRADES_LATER.md) —
cloned voice (free, self-hosted), ElevenLabs voice (paid), paid stock
video / AI-generated B-roll for history events.

## 10. Admin panel (optional, recommended) — **[web, ~10 min]**

Full detail: [docs/09_ADMIN_PANEL.md](09_ADMIN_PANEL.md)

A small web app to see how many days of videos are ready, watch one
before it goes live, hold it back, or send it back for a redo with a
note. Run it locally (`npm run dev`, nothing to sign up for) or deploy
it to Vercel for a real link you can check from your phone — the doc
covers both.

- [ ] Run `supabase/migrations/001_admin_panel.sql` in the SQL Editor.
- [ ] Create your one admin login (Supabase Dashboard → Authentication → Users).
- [ ] `cd admin-panel && npm install && npm run dev` — or deploy to Vercel, see the doc.

## Something broke?

[docs/08_TROUBLESHOOTING.md](08_TROUBLESHOOTING.md) covers the most
likely first-week failures and exactly what each one means.

---

### What this project will never do automatically
- Create multiple shadow YouTube channels/projects to dodge the quota cap (Section 8 of the build spec — explicitly rejected, looks like spam).
- Hide that the channel is automated from YouTube's own systems — every upload is tagged with the synthetic-media disclosure (Section 7) and compliance here comes from genuinely varied content, not evasion.
- Generate an AI sketch/likeness of a real, named person — only real photos tied to that person's own Wikidata record, or (for faceless historical events only) abstract AI B-roll. See Section 12 of the build spec.
