# 8. Troubleshooting — the most likely first-week failures

Run `python -m tools.selfcheck` first, always — it catches most of the
items below before you even get to a real run.

---

**"Missing required environment variables: ..."**
A `.env` value (or GitHub secret, if this happened in Actions) is blank.
The error names exactly which key — fill it in and re-run.

---

**"ffmpeg was not found on your PATH"**
Install FFmpeg (docs/START_HERE.md step 0) and, on Windows, open a
**new** terminal — PATH changes don't apply to a terminal that was
already open. Not an issue inside GitHub Actions; the workflow installs
it for you.

---

**Gemini: "Not enough Gemini quota left" / a 429 error**
The free tier's ~20 requests/day is spent. This is expected, not a bug —
it resets at midnight Pacific. If you've set up `GROQ_API_KEY`, the
pipeline automatically retries with Groq instead of failing; check the
log for `llm_router` to confirm it switched over.

---

**A video used "gtts" / you got a Telegram alert about it**
Every better voice tier failed that run — Google TTS unset or
exhausted, Azure unset or exhausted, Kokoro failed to download its
model. Check `python -m tools.selfcheck`'s `[6/7]` section; this should
be rare once at least one tier is properly configured.

---

**YouTube: "invalid_grant" / refresh token rejected**
Almost always means your OAuth consent screen is still in **Testing**
status, which expires tokens after 7 days. Fix: docs/04, "Why Testing
status will break publishing." Temporary stopgap: re-run
`python -m engine.publisher --setup` and update the secret — but you'll
be back here in 7 days until you fix the consent screen setting.

---

**Playlist auto-create/insert fails with "insufficientPermissions"**
Your refresh token was minted with the narrower `.youtube.upload` scope
instead of the full `.youtube` scope this project needs for playlist
calls. Re-run `python -m engine.publisher --setup` to re-consent — see
docs/04's note on OAuth scope.

---

**"Daily upload cap reached" alert every day**
Not an error — this is Section 8's safety cap working as designed
(~6 uploads/day on YouTube's default free quota). Overflow videos are
automatically queued to the next night, nothing is lost. See docs/04's
quota-increase section if you've genuinely outgrown 6/day.

---

**A category is missing from today's output / "a legitimately thin day"**
Some days have very few notable births/deaths/events for a given
category — `engine/topic_assembler.py` is designed to skip a category
entirely rather than pad it with low-notability filler. Check the
`review_queue` table too: a candidate might have been excluded because
Wikidata and the "On this day" blurb disagreed on a year, not because
nothing existed.

---

**A video never got a photo — it's a plain text card instead**
This is the deliberate, safe fallback (Section 4: never substitute an
unrelated photo to avoid a face mismatch). It means no Wikidata P18
portrait and no QID-linked Commons photo existed for that subject. Check
the subject's actual Wikidata page — if it does have a photo, the QID
resolution in `engine/wikidata_source.resolve_qid()` may have failed;
check the log for that job's `wikidata_source` lines.

---

**Storage keeps climbing / "Storage is filling up" alert**
Published and failed videos should auto-delete from storage
(`engine/storage_r2.delete_video`, called right after a successful
publish). If usage keeps climbing, check for videos stuck in
`status='approved'` for a long time (an auth failure stopping
`publish_queue.py` from ever reaching the delete step) — fix the
underlying publish failure first.

---

**`python -m tools.selfcheck` says a package import failed**
`pip install -r requirements.txt` again — if you're using a virtual
environment, make sure it's activated. `kokoro_onnx` specifically needs
`pip install kokoro-onnx soundfile` (listed in requirements.txt, but easy
to miss if you installed packages piecemeal).

---

Still stuck? Re-read the specific `docs/0X_*.md` file for the step that's
failing — each one has the exact menu path for that service, since
Google/Cloudflare/Supabase occasionally move things around in their own
dashboards.
