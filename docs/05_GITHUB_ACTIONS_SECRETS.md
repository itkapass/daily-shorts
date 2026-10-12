# 5. Wire It Up on GitHub Actions

Everything in your local `.env` needs to also exist as a **GitHub
Actions secret** on this repository — the scheduled workflows run on
GitHub's servers, which never see your local `.env` file.

**This only goes one direction.** Adding a secret on GitHub does *not*
add it to your local `.env` — they're two completely separate stores
that happen to need the same values. If `python -m tools.selfcheck` or
any local run says a key is missing even though you already added it on
GitHub, that's why: open your local `.env` file and add it there too.
(This is exactly what happened with `CALENDARIFIC_API_KEY` if you added
it to GitHub first — add the same line to your local `.env` and
`--refresh` will work locally too.)

## Steps

1. Push this project to a GitHub repository you own (private is fine).
2. Repo → **Settings → Secrets and variables → Actions → New repository
   secret**.
3. Add each of the following (name must match exactly). Skip any you
   left blank in `.env` — the pipeline treats a missing optional secret
   exactly like a missing optional `.env` value (that feature just turns
   itself off, nothing breaks).

### Required
| Secret name | From |
|---|---|
| `GEMINI_API_KEY` | docs/03 |
| `SUPABASE_URL` | docs/01 |
| `SUPABASE_SERVICE_KEY` | docs/01 |
| `YOUTUBE_CLIENT_ID` | docs/04 |
| `YOUTUBE_CLIENT_SECRET` | docs/04 |
| `YOUTUBE_REFRESH_TOKEN` | docs/04 |

### Recommended
| Secret name | From |
|---|---|
| `GROQ_API_KEY` | docs/03 |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | below |
| At least one of `GOOGLE_TTS_API_KEY` / `AZURE_TTS_KEY` + `AZURE_TTS_REGION` | docs/03 |

### Optional
`GEMINI_MODEL`, `GEMINI_TEMPERATURE`, `GROQ_MODEL`, `R2_ACCOUNT_ID`,
`R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_PUBLIC_BASE`,
`STORAGE_BUCKET`, `VOICE_PROVIDER`, `XTTS_SPEAKER_WAV_PATH`,
`ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `HUGGINGFACE_API_KEY`,
`HUGGINGFACE_IMAGE_MODEL`, `YOUTUBE_CHANNEL_HANDLE`,
`CALENDARIFIC_API_KEY`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`,
`SMTP_PASSWORD`, `ALERT_EMAIL_TO`, `TARGET_RUNTIME_SECONDS`,
`MAX_UPLOADS_PER_DAY`, `GOOGLE_TTS_VOICE_NAME`,
`GOOGLE_TTS_LANGUAGE_CODE`, `AZURE_TTS_VOICE_NAME`,
`AZURE_TTS_LANGUAGE_CODE`, `GTTS_TLD`, `KOKORO_VOICE_ID`,
`KOKORO_VOICE_LANG` (all seven only needed if you want a voice/accent
*other* than the Indian-English default — see docs/03).

## Set up Telegram alerts (5 minutes, strongly recommended)

Every failure in this pipeline is otherwise silent — you'd only find out
weeks later that nothing had published. Telegram is free and arrives on
your phone in a second:

1. In Telegram, message **@BotFather** → `/newbot` → follow the prompts
   → it gives you a token. This is `TELEGRAM_BOT_TOKEN`.
2. Message your new bot anything (bots can't message you first — you
   have to open the chat and send something, even just "hi").
3. Visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a
   browser → find `"chat":{"id":123456789` in the response → that number
   is `TELEGRAM_CHAT_ID`.
4. Add both as secrets, then test:
   ```
   python -m engine.alerts --test
   ```

## Set up email alerts (optional — in addition to or instead of Telegram, ~3 minutes)

Both channels are independent (`engine/alerts.py`) — set up one or both. A
Gmail address works well as the sender, via an **App Password** (not your
normal Gmail password — Google blocks plain-password SMTP logins):

1. Your Gmail account needs **2-Step Verification turned on** first — App
   Passwords aren't offered without it. [myaccount.google.com/security](https://myaccount.google.com/security) → **2-Step Verification** → turn it on if it isn't already.
2. [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) → name it anything (e.g. "daily-history-shorts") → **Create**. Copy the
   16-character password shown (spaces don't matter either way).
3. `.env` (and the matching GitHub secrets):
   ```
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=your_gmail_address@gmail.com
   SMTP_PASSWORD=the_16_character_app_password
   ALERT_EMAIL_TO=where_you_want_alerts_sent@example.com
   ```
   `ALERT_EMAIL_TO` can be the same Gmail address or a different inbox
   entirely — it's just where the alert lands, unrelated to `SMTP_USER`
   (the account actually sending the email).
4. Test it — this sends via whichever channel(s) are configured, so if
   you've also done Telegram above you'll get both:
   ```
   python -m engine.alerts --test
   ```

Using a different email provider instead of Gmail? The same four `SMTP_*`
values work for any provider — just use that provider's SMTP hostname,
port, and an app-specific password if it requires one (most do, for the
same reason Gmail does).

## Turn it on

Once the secrets are in place, just push to the repo's default branch.
The four workflows under `.github/workflows/` start running on their own
schedule immediately — nothing else to flip on:

| Workflow | Schedule | What it does |
|---|---|---|
| `generate.yml` | Daily, 06:00 UTC | Builds the whole batch of videos for 2 days from now |
| `publish.yml` | Hourly | Uploads whatever is due inside tonight's posting window |
| `health-check.yml` | Daily, 07:30 UTC | Flags anything silently broken |
| `festival-refresh.yml` | Monthly | Refreshes Diwali/Eid/Gurpurab dates (docs/07) |

You can also trigger any of them immediately from the **Actions** tab →
pick the workflow → **Run workflow**, instead of waiting for the next
scheduled time.

## Quota increase request

See [docs/04_YOUTUBE_OAUTH_SETUP.md#quota-increase](04_YOUTUBE_OAUTH_SETUP.md#quota-increase) — this is the one step that needs a human-reviewed Google form and can't be scripted.
