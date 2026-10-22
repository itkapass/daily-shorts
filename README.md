# Daily History Shorts — Automation Engine

An automated pipeline that researches real "this day in history" facts
and UN/international observances, writes a script, generates voice +
captions + Ken-Burns-style video, and publishes YouTube Shorts on a
schedule — with playlists, quota handling, retries, and alerting all
built in. Runs on free-tier services end to end (Supabase, Cloudflare
R2, GitHub Actions, Gemini, Kokoro TTS); paid upgrades are optional and
off by default.

## New here? Start with one file

👉 **[docs/START_HERE.md](docs/START_HERE.md)** — the complete one-time
setup checklist, in order, ~60-90 minutes total. Every other doc in
`docs/` is the detailed version of one checklist item, linked from
there when you need it.

## Project layout

```
engine/      The pipeline itself (research → script → voice → video → publish)
supabase/    schema.sql + migrations/ — run these once in Supabase's SQL Editor
admin-panel/ Optional web app: video queue, review, regenerate-with-note (docs/09)
.github/     The 4 scheduled workflows that run this on autopilot
docs/        START_HERE.md + 9 detailed per-topic setup guides
tools/       selfcheck.py — run this to verify your setup before trusting it
assets/      Fonts (bundled) and a staging folder for fallback videos
```

## First commands once setup is done

```
python -m tools.selfcheck                      # verifies every credential/service
python -m engine.orchestrator --ahead-days 0    # generates one real batch right now
```

Nothing here has been run with live credentials yet — it's freshly
built code, syntax-checked but not execution-tested. `selfcheck.py` is
designed to be your first real signal that something is (or isn't)
wired up correctly, catching the first likely-broken thing instead of
you discovering it two days later.
