"""
backup_provider.py — free Groq fallback for when Gemini's daily quota is
genuinely gone. Adapted near-verbatim from the reference project (same
provider, same two-model retry logic) — see llm_router.py for where this
sits in the overall chain.

Groq (groq.com) runs open models with an OpenAI-compatible API — no new
SDK, a free tier with no card needed. Get a key in ~2 minutes:
  console.groq.com/keys -> sign in -> Create API Key
Leave GROQ_API_KEY unset and this module is simply never called.
"""
import os
import time
import requests

GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"
FALLBACK_GROQ_MODEL = "openai/gpt-oss-20b"
TIMEOUT_SECONDS = 60
PROVIDER_NAME = "groq"


def available() -> bool:
    return bool(os.environ.get("GROQ_API_KEY"))


class _TryNextModel(RuntimeError):
    """Internal signal: retry with the OTHER model (a missing/retired model
    name, or a rate limit specific to this one) rather than giving up."""


def call(system_prompt: str, user_prompt: str, temperature: float = 0.9) -> str:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Get a free key at console.groq.com/keys "
            "and add it as a GitHub secret. See docs/03."
        )
    primary_model = os.environ.get("GROQ_MODEL", DEFAULT_GROQ_MODEL)
    try:
        return _call_model(primary_model, system_prompt, user_prompt, temperature, api_key)
    except _TryNextModel as e:
        if primary_model == FALLBACK_GROQ_MODEL:
            raise RuntimeError(str(e)) from e
        print(f"[backup_provider] {e} Retrying once against '{FALLBACK_GROQ_MODEL}'.")
        try:
            return _call_model(FALLBACK_GROQ_MODEL, system_prompt, user_prompt, temperature, api_key)
        except _TryNextModel as e2:
            raise RuntimeError(str(e2)) from e2


def _parse_retry_seconds(text: str, default: int = 25) -> int:
    import re
    m = re.search(r"try again in (\d+(?:\.\d+)?)\s*s", text, re.IGNORECASE)
    return min(int(float(m.group(1))) + 2, 60) if m else default


def _call_model(model, system_prompt, user_prompt, temperature, api_key, _minute_retries=0) -> str:
    MAX_MINUTE_RETRIES = 3
    try:
        resp = requests.post(
            GROQ_ENDPOINT,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt +
                     "\n\nRespond with ONLY the JSON. No markdown fences, no commentary."},
                ],
                "temperature": temperature,
            },
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as e:
        raise RuntimeError(f"Could not reach Groq (network error): {e}") from e

    if resp.status_code == 401:
        raise RuntimeError("Groq rejected the API key (401). Check GROQ_API_KEY.")
    if resp.status_code == 429:
        if "per minute" in resp.text.lower() or "tpm" in resp.text.lower() or "rpm" in resp.text.lower():
            if _minute_retries >= MAX_MINUTE_RETRIES:
                raise _TryNextModel(f"Groq model '{model}' still per-minute limited: {resp.text[:200]}")
            wait = _parse_retry_seconds(resp.text)
            print(f"[backup_provider] Per-minute limit on '{model}', waiting {wait}s "
                  f"(attempt {_minute_retries + 1}/{MAX_MINUTE_RETRIES}).")
            time.sleep(wait)
            return _call_model(model, system_prompt, user_prompt, temperature, api_key,
                               _minute_retries=_minute_retries + 1)
        raise _TryNextModel(f"Groq model '{model}' hit its daily limit: {resp.text[:200]}")
    if resp.status_code == 404 or "model_not_found" in resp.text.lower():
        raise _TryNextModel(f"Groq model '{model}' not found — may be retired. Set GROQ_MODEL.")
    if not resp.ok:
        raise RuntimeError(f"Groq returned {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Unexpected response shape from Groq: {data}") from e
