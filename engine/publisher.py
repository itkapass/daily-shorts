"""
publisher.py — YouTube Data API v3 uploader, with mandatory playlist
automation (Section 8) and the synthetic-media disclosure (Section 7).
============================================================================
OAuth SCOPE IS WIDENED vs. a typical "just upload" project. Playlist
management (playlists.insert / playlistItems.insert) needs more than the
narrow https://www.googleapis.com/auth/youtube.upload scope — it needs
the full https://www.googleapis.com/auth/youtube scope. This is the one
substantive change from the pattern this project's reference codebase
used (which only ever uploaded, never touched playlists): if you reuse an
older refresh token that was only ever granted .youtube.upload, playlist
calls will fail with insufficientPermissions — run --setup again to
re-consent with the wider scope (see docs/04).
"""
import os
import json
import argparse
import pickle

import google.oauth2.credentials
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request

from engine.config import get

SCOPES = ["https://www.googleapis.com/auth/youtube"]
API_SERVICE, API_VERSION = "youtube", "v3"
TOKEN_FILE = "engine/youtube_token.pickle"
CLIENT_SECRETS_FILE = "engine/youtube_client_secrets.json"

# 27 = Education — the best fit for history/trivia content.
CATEGORY_ID = "27"


# ─── Authentication ────────────────────────────────────────────────────────

def get_authenticated_service(force_interactive: bool = False):
    if force_interactive:
        return googleapiclient.discovery.build(API_SERVICE, API_VERSION, credentials=_run_interactive_setup())

    credentials = _credentials_from_env() or _credentials_from_pickle()
    if credentials and credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(Request())
            if os.path.exists(os.path.dirname(TOKEN_FILE) or "."):
                _save_token(credentials)
        except Exception as e:
            print(f"[publisher] Stored token is no longer valid: {e}")
            credentials = None
            if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
                raise RuntimeError(
                    "YOUTUBE_REFRESH_TOKEN has expired or been revoked.\n"
                    "Run locally: python -m engine.publisher --setup\n"
                    "then update the YOUTUBE_REFRESH_TOKEN secret in GitHub."
                ) from e
            print("[publisher] Starting a fresh authorization instead...")

    if not credentials or not credentials.valid:
        credentials = _run_interactive_setup()
    return googleapiclient.discovery.build(API_SERVICE, API_VERSION, credentials=credentials)


def _credentials_from_env():
    client_id = get("YOUTUBE_CLIENT_ID")
    client_secret = get("YOUTUBE_CLIENT_SECRET")
    refresh_token = get("YOUTUBE_REFRESH_TOKEN")
    if not (client_id and client_secret and refresh_token):
        return None
    creds = google.oauth2.credentials.Credentials(
        token=None, refresh_token=refresh_token, token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id, client_secret=client_secret, scopes=SCOPES,
    )
    try:
        creds.refresh(Request())
    except Exception as e:
        msg = str(e).lower()
        if "invalid_grant" in msg:
            raise RuntimeError(
                "YouTube refresh token rejected (invalid_grant). Usual cause: your OAuth "
                "consent screen is still 'Testing', which expires tokens after 7 days. "
                "Fix: set it to 'In production' (docs/04 section 3), or re-run --setup."
            ) from e
        raise
    return creds


def _credentials_from_pickle():
    if not os.path.exists(TOKEN_FILE):
        return None
    with open(TOKEN_FILE, "rb") as f:
        return pickle.load(f)


def _run_interactive_setup():
    try:
        if os.path.exists(TOKEN_FILE):
            os.remove(TOKEN_FILE)
    except OSError:
        pass

    env_id, env_secret = get("YOUTUBE_CLIENT_ID"), get("YOUTUBE_CLIENT_SECRET")
    if os.path.exists(CLIENT_SECRETS_FILE):
        flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, scopes=SCOPES)
    elif env_id and env_secret:
        flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_config(
            {"installed": {"client_id": env_id, "client_secret": env_secret,
                           "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                           "token_uri": "https://oauth2.googleapis.com/token",
                           "redirect_uris": ["http://localhost"]}},
            scopes=SCOPES,
        )
    else:
        raise FileNotFoundError(
            "No OAuth client credentials found. Put YOUTUBE_CLIENT_ID and "
            "YOUTUBE_CLIENT_SECRET in .env, or save your OAuth client JSON as "
            f"{CLIENT_SECRETS_FILE}. See docs/04."
        )

    print("[publisher] Opening your browser for YouTube authorization...")
    print("[publisher] Sign in with the account that owns the YouTube channel.")
    credentials = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    _save_token(credentials)

    if not credentials.refresh_token:
        print("\n[publisher] Google did not return a refresh token. Revoke this app at "
              "myaccount.google.com/permissions and run --setup again.\n")
    else:
        print("\n" + "=" * 64 + "\n  AUTHORIZATION COMPLETE\n" + "=" * 64)
        print("\n  Add these three as GitHub repository secrets:\n")
        print(f"  YOUTUBE_CLIENT_ID\n     {credentials.client_id}\n")
        print(f"  YOUTUBE_CLIENT_SECRET\n     {credentials.client_secret}\n")
        print(f"  YOUTUBE_REFRESH_TOKEN\n     {credentials.refresh_token}\n")
        print("=" * 64 + "\n  Copy the REFRESH TOKEN now. It is not shown again.\n" + "=" * 64 + "\n")
    return credentials


def _save_token(credentials):
    with open(TOKEN_FILE, "wb") as f:
        pickle.dump(credentials, f)


# ─── Playlist automation (Section 8 — mandatory, not optional) ─────────────

def get_or_create_playlist(youtube, db, category: str, part_number=None) -> str:
    """Returns the YouTube playlist id for this category/part, creating it
    (playlists.insert) the first time it's needed and caching the id in
    the `playlists` table so every later video in this category reuses
    the same playlist instead of creating a new one each run."""
    try:
        q = db.table("playlists").select("youtube_playlist_id").eq("category", category)
        q = q.is_("part_number", "null") if part_number is None else q.eq("part_number", part_number)
        rows = q.execute().data or []
        if rows:
            return rows[0]["youtube_playlist_id"]
    except Exception as e:
        print(f"[publisher] Playlist cache lookup failed ({e}); checking YouTube directly.")

    title = _playlist_title(category, part_number)

    # Check YouTube directly in case the cache table was wiped but the
    # playlist still exists on the channel — avoids creating a duplicate.
    try:
        resp = youtube.playlists().list(part="snippet", mine=True, maxResults=50).execute()
        for item in resp.get("items", []):
            if item["snippet"]["title"] == title:
                _cache_playlist(db, category, part_number, item["id"], title)
                return item["id"]
    except Exception as e:
        print(f"[publisher] Could not list existing playlists ({e}); will attempt to create one.")

    body = {"snippet": {"title": title, "description": f"Auto-generated playlist for '{category}' content."},
            "status": {"privacyStatus": "public"}}
    response = youtube.playlists().insert(part="snippet,status", body=body).execute()
    playlist_id = response["id"]
    _cache_playlist(db, category, part_number, playlist_id, title)
    print(f"[publisher] Created playlist '{title}' -> {playlist_id}")
    return playlist_id


def _playlist_title(category: str, part_number) -> str:
    pretty = category.replace("_", " ").title()
    return f"{pretty} - Part {part_number}" if part_number else pretty


def _cache_playlist(db, category: str, part_number, playlist_id: str, title: str):
    try:
        db.table("playlists").upsert({
            "category": category, "part_number": part_number,
            "youtube_playlist_id": playlist_id, "title": title,
        }, on_conflict="category,part_number").execute()
    except Exception as e:
        print(f"[publisher] Could not cache playlist id ({e}) — it will be re-looked-up next run.")


def add_video_to_playlist(youtube, playlist_id: str, video_id: str):
    youtube.playlistItems().insert(
        part="snippet",
        body={"snippet": {"playlistId": playlist_id, "resourceId": {"kind": "youtube#video", "videoId": video_id}}},
    ).execute()


# ─── Core upload ─────────────────────────────────────────────────────────────

def upload_video(video_path: str, title: str, description: str, hashtags: list,
                 category: str, part_number=None, privacy: str = "public",
                 captions_srt: str = None, db=None) -> dict:
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")
    if "#Shorts" not in title and "#shorts" not in title.lower():
        title = title[:90] + " #Shorts"

    full_description = f"{description}\n\n{' '.join(hashtags)}"
    body = {
        "snippet": {"title": title[:100], "description": full_description[:5000],
                   "tags": [t.lstrip("#") for t in hashtags[:15]], "categoryId": CATEGORY_ID,
                   "defaultLanguage": "en"},
        "status": {
            "privacyStatus": privacy, "selfDeclaredMadeForKids": False,
            "notifySubscribers": False,
            # Section 7: required disclosure for AI-narrated/AI-visual content
            # about real people/events, automated rather than a manual
            # checkbox. VERIFY this exact field name against YouTube's
            # current Data API reference before relying on it in
            # production — the Data API has changed synthetic-media
            # disclosure fields before and may again.
            "containsSyntheticMedia": True,
        },
    }

    print(f"[publisher] Uploading: '{title}' ({os.path.getsize(video_path) / 1024 / 1024:.1f} MB)")
    youtube = get_authenticated_service()
    media = MediaFileUpload(video_path, chunksize=10 * 1024 * 1024, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part=",".join(body.keys()), body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"[publisher] Upload progress: {int(status.progress() * 100)}%", end="\r")

    video_id = response.get("id", "")
    url = f"https://www.youtube.com/shorts/{video_id}"
    print(f"\n[publisher] Uploaded. Video ID: {video_id} -> {url}")

    if captions_srt and captions_srt.strip():
        _upload_captions(youtube, video_id, captions_srt)

    playlist_result = {"status": "skipped"}
    if db is not None:
        try:
            playlist_id = get_or_create_playlist(youtube, db, category, part_number)
            add_video_to_playlist(youtube, playlist_id, video_id)
            playlist_result = {"status": "added", "playlist_id": playlist_id}
            print(f"[publisher] Added to playlist {playlist_id}")
        except Exception as e:
            print(f"[publisher] Playlist auto-create/insert failed (video itself still published): {e}")
            try:
                from engine import alerts
                alerts.playlist_setup_failed(category, part_number, str(e))
            except Exception:
                pass
            playlist_result = {"status": "failed", "error": str(e)}

    return {"video_id": video_id, "url": url, "status": "uploaded", "title": title, "playlist": playlist_result}


def _upload_captions(youtube, video_id: str, srt_content: str):
    import tempfile
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".srt", delete=False, encoding="utf-8") as f:
            f.write(srt_content)
            tmp_path = f.name
        try:
            media = MediaFileUpload(tmp_path, mimetype="application/octet-stream")
            youtube.captions().insert(
                part="snippet",
                body={"snippet": {"videoId": video_id, "language": "en", "name": "", "isDraft": False}},
                media_body=media, sync=False,
            ).execute()
            print(f"[publisher] Real caption track uploaded for {video_id}")
        finally:
            os.unlink(tmp_path)
    except Exception as e:
        print(f"[publisher] Caption upload failed ({e}) — video itself is unaffected.")


# ─── CLI ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="YouTube publisher")
    parser.add_argument("--setup", action="store_true")
    parser.add_argument("--upload", type=str)
    parser.add_argument("--title", type=str, default="Test Video #Shorts")
    parser.add_argument("--category", type=str, default="history")
    parser.add_argument("--privacy", type=str, default="private")
    args = parser.parse_args()

    if args.setup:
        get_authenticated_service(force_interactive=True)
    elif args.upload:
        from engine.supabase_client import get_db
        result = upload_video(args.upload, args.title, "Test upload.", ["#Shorts", "#History"],
                              category=args.category, privacy=args.privacy, db=get_db())
        print(json.dumps(result, indent=2))
    else:
        print("Usage:\n  python -m engine.publisher --setup\n  python -m engine.publisher --upload path.mp4")
