# 2. Storage Setup — Cloudflare R2 (optional)

Rendered videos need to live somewhere between "rendered" and
"published" (usually a few hours to a couple of days, inside the posting
window). This project supports two free options:

| | Free tier | Egress (download) cost | Setup effort |
|---|---|---|---|
| **Cloudflare R2** (recommended) | 10 GB | **$0** | ~10 minutes, this doc |
| Supabase Storage (automatic fallback) | 1 GB | Counts against Supabase bandwidth | **Zero** — do nothing |

The pipeline downloads each video again at publish time, so R2's zero
egress fee matters. But if you'd rather skip a setup step entirely,
**skip this whole doc** — leaving the four `R2_*` variables blank in
`.env` makes the pipeline use Supabase Storage automatically, no code
changes needed either way.

## Steps (if you want R2)

1. [dash.cloudflare.com](https://dash.cloudflare.com) → sign up free →
   left sidebar **R2 Object Storage** → **Create bucket**.
   - Name it `daily-history-shorts` (or anything — just match it in
     `STORAGE_BUCKET` in `.env`).
2. Open the bucket → **Settings** → **Public access** → under
   "R2.dev subdomain" click **Allow Access** → copy the
   `https://pub-xxxxxxxx.r2.dev` URL. This is `R2_PUBLIC_BASE` (no
   trailing slash).
3. Back on the R2 overview page → **Manage R2 API Tokens** → **Create
   API token**.
   - Permissions: **Object Read & Write**.
   - Scope it to the bucket you just made (or "All buckets" if you
     prefer).
   - Copy the **Access Key ID** and **Secret Access Key** — shown only
     once.
4. Your **Account ID** is shown on the R2 overview page's right sidebar
   (a long hex string).
5. Fill in `.env`:
   ```
   R2_ACCOUNT_ID=your_account_id
   R2_ACCESS_KEY_ID=your_access_key_id
   R2_SECRET_ACCESS_KEY=your_secret_access_key
   R2_PUBLIC_BASE=https://pub-xxxxxxxx.r2.dev
   STORAGE_BUCKET=daily-history-shorts
   ```

## Verify

```
python -c "from engine import storage_r2; print(storage_r2.check_storage_pressure())"
```
Should print `{'used_mb': 0.0, ..., 'backend': 'r2', ...}`. If `backend`
says `supabase` instead, one of the four R2 variables is still blank.
