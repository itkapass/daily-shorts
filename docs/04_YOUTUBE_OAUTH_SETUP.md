# 4. YouTube Publishing Setup

This is the most involved step, but it's a one-time thing. You need a
real browser for this part — it can't be done inside GitHub Actions.

## 1. Enable the API

1. [console.cloud.google.com](https://console.cloud.google.com) → create
   a new project (or reuse one) — name it anything, e.g. "daily-history-shorts".
2. **APIs & Services → Library** → search **"YouTube Data API v3"** → **Enable**.

## 2. Set up the OAuth consent screen (do this BEFORE creating credentials)

1. **APIs & Services → OAuth consent screen**.
2. User type: **External** (unless you have a Google Workspace org, in
   which case Internal also works).
3. Fill in an app name (anything) and your email for the two required
   contact fields. Scopes: you don't need to add any here — the app
   requests its scope directly in code.
4. Add yourself as a **Test user** under the Test users section (your own
   Google account / the one that owns the YouTube channel).
5. **Save**. It will show status **"Testing"** — see the warning below
   about why you must change this.

### Why "Testing" status will break publishing after 7 days

While the consent screen is in **Testing**, Google expires your refresh
token after 7 days, which silently stops all publishing until you
re-authorize. The fix is permanent and takes 2 minutes:

1. **OAuth consent screen** → **Publish App** (or, depending on the
   current Cloud Console layout, a button/toggle labeled **"In
   production"**).
2. For the scope this app uses (`.../auth/youtube`, not a "sensitive" or
   "restricted" scope in Google's classification), publishing to
   production does **not** require Google's verification review — your
   app just stops being time-limited. If your specific project ever
   shows a verification requirement, you can also simply re-run
   `--setup` every 7 days as a manual stopgap, but setting production
   mode is the actual fix.

## 3. Create the OAuth client

1. **APIs & Services → Credentials → Create Credentials → OAuth client ID**.
2. Application type: **Desktop app**.
3. Name it anything, **Create**.
4. Copy the **Client ID** and **Client Secret** shown.
5. `.env`:
   ```
   YOUTUBE_CLIENT_ID=...
   YOUTUBE_CLIENT_SECRET=...
   ```

## 4. Run the one-time authorization

From this project's root, locally (needs a browser):
```
python -m engine.publisher --setup
```
- Your browser opens → sign in with the Google account that **owns the
  YouTube channel** you want to publish to.
- You'll likely see **"Google hasn't verified this app"** — click
  **Advanced → Go to (your app name) (unsafe)**. This is expected; it's
  your own app, not a third party's.
- On success, the terminal prints a **Client ID**, **Client Secret**, and
  **Refresh Token**. Copy the refresh token into `.env`:
  ```
  YOUTUBE_REFRESH_TOKEN=...
  ```

### Why the OAuth scope matters here specifically

This project requests `https://www.googleapis.com/auth/youtube` (the
broader scope), **not** the narrower `.../auth/youtube.upload` that a
simple "just upload videos" project would use. The wider scope is
required for the mandatory playlist automation (Section 8 of the build
spec: each category auto-creates its own YouTube playlist and
auto-inserts every video into it). If you ever reuse an older refresh
token minted with only the narrow upload scope, playlist calls will fail
with an `insufficientPermissions` error — just re-run `--setup` to
re-consent with the correct scope.

## Verify

```
python -m tools.selfcheck
```
`[7/7] YouTube OAuth` refreshes the token for real and tells you
immediately if something's wrong, rather than you finding out at 2am
when a scheduled publish silently fails.

## One thing this can't automate: the quota increase request {#quota-increase}

YouTube's default quota is 10,000 units/day, and one upload costs about
1,600 units + ~50 for the thumbnail + ~100 for the two playlist calls —
so **about 6 uploads/day** is the real ceiling per Google Cloud project.
This project's scheduler (`engine/scheduler.py`) automatically queues any
overflow to the next day rather than failing, so going over the cap never
loses a video — it just delays it.

When you outgrow 6/day, Google requires a human-reviewed form to raise
it — this is the one manual, one-time step nothing here can do for you:
1. **APIs & Services → YouTube Data API v3 → Quotas** → request an
   increase, explaining your use case.
2. This is entirely optional — do it only when the 6/day cap is actually
   limiting you.

Do **not** create a second Google Cloud project/channel purely to dodge
this cap — the quota is meant to be per legitimate channel, and stacking
shadow projects to multiply it reads as exactly the kind of
inauthentic/spammy pattern Section 8 of the build spec explicitly says to
avoid.
