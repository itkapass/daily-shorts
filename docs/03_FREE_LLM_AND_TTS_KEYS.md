# 3. Free API Keys — Script Generation + Voice

## Script generation

### Gemini (required — the primary script writer)
1. [aistudio.google.com](https://aistudio.google.com/) → sign in → **Get API key** → **Create API key**.
2. `.env`: `GEMINI_API_KEY=...`

Free tier is roughly 20 requests/day on the default model — comfortably
enough for one full day's batch of videos (each video/part costs exactly
one call). If you ever see a "quota exhausted" message, that's this
limit, not a bug; it resets at midnight Pacific time.

### Groq (recommended — free backup #1)
Only used the day Gemini's quota genuinely runs out. Takes ~2 minutes:
1. [console.groq.com/keys](https://console.groq.com/keys) → sign in with
   any Google/GitHub account → **Create API Key**.
2. `.env`: `GROQ_API_KEY=...`

### GitHub Models (free backup #2 — no key needed in Actions)
Only reached if Gemini AND Groq have both failed for the day. In GitHub
Actions this needs **no secret at all** — `.github/workflows/generate.yml`
already requests the `models: read` permission, and GitHub's own
automatic token covers it. Nothing to do here unless you want to test
this specific fallback locally, in which case set `GITHUB_MODELS_TOKEN`
to a personal access token with the `models: read` scope.

## Voice (Section 6 — pick at least one; more than one is fine, they form a fallback chain)

This project tries, in order: **Google Cloud TTS → Azure TTS → Kokoro
(offline) → gTTS (absolute last resort)**.

### Accent matters more than you'd think — read this first

This channel defaults to an **Indian-English (en-IN) voice** everywhere
it can, on purpose: a US/UK-accented voice at a measured TTS pace reads
as an obvious "foreign AI voice" to an Indian audience and gets skipped
in the first 1-2 seconds, which is the single biggest retention killer
on Shorts. `engine/google_tts.py` and `engine/azure_tts.py` both default
to an `en-IN` voice already — nothing to configure, just get a key for
one of them.

**The one gap:** Kokoro (Option A below, zero setup) only ships American
and British English voices — there is currently no Indian-English option
in its bundled voicepack. That makes it fine as the offline safety net
(something posts rather than nothing if both cloud tiers are down or
over quota) but the **wrong tier to rely on as your main voice** for this
audience. **Set up Option B (Google Cloud TTS) first** — it's still free,
takes about 2 minutes, and is what actually gets used on a normal day.

### Option A — Google Cloud TTS (do this first — best quality + Indian accent)
1. [console.cloud.google.com](https://console.cloud.google.com) → create
   or pick a project → search **"Cloud Text-to-Speech API"** → **Enable**.
2. **APIs & Services → Credentials → Create Credentials → API key**.
   (You do NOT need a service account JSON for this project — it uses
   the simpler API-key REST endpoint on purpose.)
3. `.env`: `GOOGLE_TTS_API_KEY=...`

Free tier: ~1 million characters/month (Neural2 voices) — far more than
one channel needs. Defaults to `en-IN-Neural2-B`; the full current voice
list (in case that name ever changes) is at
[cloud.google.com/text-to-speech/docs/voices](https://cloud.google.com/text-to-speech/docs/voices) — filter by "Indian English."

### Option B — Azure Neural TTS (free backup for when Google's tier is spent)
1. [portal.azure.com](https://portal.azure.com) → **Create a resource** →
   search **"Speech"** → create it on the **Free F0** pricing tier.
2. Resource page → **Keys and Endpoint** → copy **Key 1** and the
   **Region** (e.g. `eastus` — the region just hosts the API call, it has
   no effect on the voice's accent).
3. `.env`: `AZURE_TTS_KEY=...` and `AZURE_TTS_REGION=eastus`

Free tier: ~500,000 characters/month. Defaults to `en-IN-PrabhatNeural`
(male) — swap to `en-IN-NeerjaNeural` (female) via `AZURE_TTS_VOICE_NAME`
in `.env` if you'd rather have that persona.

### Option C — Kokoro (zero setup, offline safety net only — see warning above)
```
pip install kokoro-onnx soundfile
```
That's it. The first time it runs it downloads its own voice model
(~350MB, cached afterward) — no account, no key, fully offline from then
on. Worth having installed as the fallback under A and B, but set up at
least one of those first so this isn't the voice actually narrating your
videos day to day.

## Verify

```
python -m tools.selfcheck
```
Checks `[5/7] Gemini` and `[6/7] Voice pipeline` and tells you exactly
which of the above are missing.
