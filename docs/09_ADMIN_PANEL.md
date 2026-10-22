# 9. Admin Panel (optional, but recommended)

A small web app for checking on the pipeline without reading terminal
logs: see which days have videos ready, watch a video before it goes
live, hold one back, or send it back for a redo with a note (e.g. "wrong
photo used" or "double-check this date") — the engine picks that note up
automatically on its next scheduled generation run.

You can run it two ways, and they're not exclusive — do local first (5
minutes, nothing to sign up for), add the online version later if you
want to check from your phone.

## One-time setup (needed either way)

### Step 1 — run the new database migration

1. Supabase Dashboard → **SQL Editor** → paste the whole contents of
   `supabase/migrations/001_admin_panel.sql` → **Run**.

This adds one column (`videos.admin_note`) and a handful of access rules
so the admin panel can read/update your data. It does **not** touch
anything the Python pipeline already relies on, and it's safe to run
even if you run it twice.

### Step 2 — create your one admin login

The admin panel has its own sign-in, separate from everything else —
this is what stops a stranger who somehow found the panel's web address
from seeing your data (see "Is this actually secure?" at the bottom).

1. Supabase Dashboard → **Authentication → Users → Add user**.
2. Pick **Create new user**, enter any email and password you'll
   remember (this doesn't need to be a real inbox — it's just your
   login, nothing gets emailed to it unless you later turn that on).
3. Leave "Auto Confirm User" checked, then **Create user**.

That's your one login for the admin panel from now on.

### Step 3 — get your anon key

Supabase Dashboard → **Project Settings → API** → copy the
**`anon` `public`** key (NOT the `service_role` key — that one's only
for the Python pipeline's `.env` / GitHub secrets, and must never go
into the admin panel). Copy your **Project URL** from the same page too.

## Option A — run it locally (recommended to start)

1. Make sure [Node.js](https://nodejs.org) is installed (same requirement
   as nothing else in this project — if you've gotten this far you likely
   already have it; if not, install the LTS version).
2. In a terminal:
   ```
   cd admin-panel
   npm install
   ```
3. Copy `admin-panel/.env.example` to `admin-panel/.env` and fill in the
   two values from Step 3 above:
   ```
   VITE_SUPABASE_URL=https://your-project-id.supabase.co
   VITE_SUPABASE_ANON_KEY=your_anon_key_here
   ```
4. ```
   npm run dev
   ```
   Open the `http://localhost:5173` link it prints. Sign in with the
   login you created in Step 2.

Whenever you want to check on things, open a terminal, `cd admin-panel`,
`npm run dev` again. Close the terminal (or Ctrl+C) when you're done —
nothing keeps running in the background.

## Option B — deploy it online (Vercel, free)

Gives you a real `https://...vercel.app` link you can open from your
phone, no terminal needed after the one-time setup.

1. [vercel.com](https://vercel.com) → **Sign up** → choose **Continue
   with GitHub** and authorize it against the same GitHub account your
   repo is on.
2. **Add New → Project** → find and **Import** your repo
   (`daily-shorts` or whatever you named it).
3. Vercel will try to guess a "Root Directory" — click **Edit** next to
   it and set it to `admin-panel` (important: without this it'll try to
   build the whole repo, including the Python pipeline, and fail).
4. Before deploying, open **Environment Variables** and add the same two
   values from Step 3:
   | Name | Value |
   |---|---|
   | `VITE_SUPABASE_URL` | your Supabase project URL |
   | `VITE_SUPABASE_ANON_KEY` | your Supabase anon key |
5. **Deploy**. After ~1 minute you'll get a link like
   `https://daily-shorts-admin.vercel.app` — that's yours permanently,
   bookmark it (and add it to your phone's home screen if you want it to
   feel like an app).
6. If you ever change the admin panel's code and push to GitHub, Vercel
   redeploys automatically — nothing to repeat.

## Using it

- **Video Queue** — every generated video, newest-scheduled first. The
  top summary shows how far ahead you're actually covered ("Ready
  through: Oct 25") — this directly answers "how many days of videos do
  I have banked?"
- Click any video to expand it: watch it, see every scene's voiceover
  line and whether it actually got a **real photo**, **AI art**, or just
  a **text card** (📷 / 🎨 / 🅰 icons) — this is exactly the "are faces
  actually showing up" question made visible, instead of only finding
  out after it's live.
- **Hold** keeps an approved video out of the publish queue indefinitely
  (its scheduled time passes with nothing happening) until you **Release**
  it — use this for "let me look at this again before it goes out."
- **Regenerate with a note** — write what should be different, submit,
  and it's picked up automatically the next time `generate.yml` runs for
  that date (daily, or trigger it manually from the Actions tab — see
  docs/05). The note gets fed straight into the script-writing prompt as
  a direct instruction, and the old video is replaced once the new one
  finishes.
- **Review Queue** tab — candidates where two sources disagreed on a
  fact (see `engine/verification.py`), held back from any video rather
  than aired as unverified. Clear one once you've checked it, or
  discard it for good.

## Is this actually secure?

Reasonably, for a personal tool: the `anon` key is *meant* to be public
(it's baked into the deployed app's code, visible to anyone who looks) —
what actually protects your data is that Supabase checks every request
against the Row Level Security rules from Step 1, which only grant
access to a **signed-in** user, and the only account that exists is the
one you created in Step 2. Nobody can read or change anything without
that password. This is the same pattern Supabase's own docs recommend
for small admin tools — it's a normal, supported way to do this, not a
shortcut.

## What this doesn't do (yet)

No settings editor (voice/runtime/budget knobs are still `.env` /
GitHub secrets only), and no per-topic pause control — this project is
organized by fixed category, not a pausable topic list, so that part of
`cricket_shorts_studio`'s admin panel doesn't map over directly. Both
are easy to add later if useful.
