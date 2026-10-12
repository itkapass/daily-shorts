"""
supabase_client.py — one place that builds the Supabase client.

Every engine module that touches the database imports get_db() from here
instead of constructing its own client, so there is exactly one code path
to fix if the connection logic ever needs to change.
"""
from engine.config import get

_client = None


def get_db():
    global _client
    if _client is not None:
        return _client
    from supabase import create_client
    url, key = get("SUPABASE_URL"), get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL / SUPABASE_SERVICE_KEY not configured. See docs/01_SUPABASE_SETUP.md."
        )
    _client = create_client(url, key)
    return _client
