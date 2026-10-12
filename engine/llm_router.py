"""
llm_router.py — tries every configured free backup provider, in order,
before giving up. Adapted from the reference project.

Gemini is always tried first (see script_generator.py). This only runs
once Gemini has genuinely failed with a per-day quota error:
  1. Groq           (engine/backup_provider.py)       — 1,000 req/day/model
  2. GitHub Models   (engine/github_models_provider.py) — needs no new
                      signup in Actions (models: read permission only)
"""
from engine import backup_provider
from engine import github_models_provider

_CHAIN = [
    ("groq", backup_provider),
    ("github_models", github_models_provider),
]


def any_backup_available() -> bool:
    return any(mod.available() for _, mod in _CHAIN)


def call(system_prompt: str, user_prompt: str, temperature: float = 0.9) -> tuple:
    tried = []
    for name, mod in _CHAIN:
        if not mod.available():
            continue
        try:
            text = mod.call(system_prompt, user_prompt, temperature)
            return text, name
        except Exception as e:
            tried.append(f"{name}: {e}")
            print(f"[llm_router] Backup provider '{name}' failed, trying the next: {e}")

    if not tried:
        raise RuntimeError(
            "No backup LLM provider is configured. See docs/03_FREE_LLM_AND_TTS_KEYS.md "
            "to add a free Groq key, and/or enable GitHub Models (models: read in the "
            "workflow permissions)."
        )
    raise RuntimeError("Every configured backup LLM provider failed today:\n" +
                        "\n".join(f"  - {t}" for t in tried))
