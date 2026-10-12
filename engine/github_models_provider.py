"""
github_models_provider.py — third, zero-signup free LLM fallback.

Only reached if Gemini AND Groq have both genuinely failed with a daily
quota error today. In GitHub Actions this needs no new secret at all —
just `models: read` under the workflow's `permissions:` block (already set
in .github/workflows/generate.yml) and the automatic GITHUB_TOKEN. Running
locally outside Actions, set GITHUB_MODELS_TOKEN to a personal access
token with the `models: read` scope.
"""
import os
import requests

ENDPOINT = "https://models.inference.ai.azure.com/chat/completions"
DEFAULT_MODEL = "gpt-4o-mini"
TIMEOUT_SECONDS = 60


def _token():
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GITHUB_MODELS_TOKEN")


def available() -> bool:
    return bool(_token())


def call(system_prompt: str, user_prompt: str, temperature: float = 0.9) -> str:
    token = _token()
    if not token:
        raise RuntimeError(
            "No GitHub Models token available. In Actions this needs 'models: read' "
            "under permissions:; locally set GITHUB_MODELS_TOKEN."
        )
    try:
        resp = requests.post(
            ENDPOINT,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "model": os.environ.get("GITHUB_MODELS_MODEL", DEFAULT_MODEL),
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt +
                     "\n\nRespond with ONLY the JSON. No markdown fences."},
                ],
                "temperature": temperature,
            },
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as e:
        raise RuntimeError(f"Could not reach GitHub Models (network error): {e}") from e

    if not resp.ok:
        raise RuntimeError(f"GitHub Models returned {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Unexpected response shape from GitHub Models: {data}") from e
