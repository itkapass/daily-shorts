"""
script_generator.py — turns a verified candidate list into a storyboard,
avoiding YouTube's "Inauthentic Content" policy by construction (Section 7).
============================================================================
Gemini (google-genai, the current maintained SDK) is tried first on every
call. Only on a confirmed per-day 429 does this fall through to
llm_router's free backups (Groq, then GitHub Models) — see api_budget.py
for the budget bookkeeping that decides whether to even attempt Gemini.

SECTION 7 BUILT INTO THE PROMPT, NOT LEFT TO CHANCE
  - One consistent host persona (voice + phrasing register) — PERSONA_VOICE
    below, injected into every system prompt.
  - Brief original commentary/framing per fact, never a flat recitation —
    an explicit RULE, plus a worked example.
  - Varied pacing/hook phrasing/segment order — a hook is chosen from
    HOOK_STYLES per job (deterministic per job_id, not random each retry,
    so retries are reproducible) rather than every video opening the same way.
  - Closing CTA required in the prompt (quality_gates.py's closing_cta
    check is the mechanical back-check that the model actually complied).
"""
import json
import re

from engine import llm_router, research
from engine.config import get

PERSONA_VOICE = (
    "You are the calm, warm narrator of a daily history/trivia Shorts channel. "
    "You sound like a well-read friend telling someone something genuinely "
    "interesting they didn't know, never like a textbook or a press release."
)

HOOK_STYLES = [
    "Open with a surprising 'did you know' twist about the first fact.",
    "Open by directly addressing the viewer with a question tied to today's date.",
    "Open with a bold, confident claim that the next few seconds will justify.",
    "Open by naming today's date and immediately contrasting it with something unexpected.",
]


def _hook_for_job(job_id: str) -> str:
    idx = sum(ord(c) for c in job_id) % len(HOOK_STYLES)
    return HOOK_STYLES[idx]


def _build_system_prompt(category: str, part_label: str) -> str:
    return f"""{PERSONA_VOICE}

You are writing the voiceover script for a YouTube Short in the "{category}"
series{part_label}. Output ONLY valid JSON, no markdown fences, no commentary
before or after it, matching exactly this shape:

{{
  "title": "a punchy, specific title under 90 characters",
  "description": "2-3 sentences for the YouTube description",
  "hashtags": ["#Shorts", "#OnThisDay", "...3-6 more relevant tags..."],
  "scenes": [
    {{"voice_text": "...", "subject_qid": "Q123 or null", "visual_keyword": "..."}}
  ]
}}

RULES:
1. One scene per candidate fact given to you, in the order given, plus
   exactly one opening hook scene and exactly one closing scene.
2. {_rules_hook_placeholder()}
3. For EVERY fact scene, add one short original line of commentary or
   framing after stating the fact — never just the bare fact alone.
   Example: not "Isaac Newton was born on this day in 1643." but
   "Isaac Newton was born on this day in 1643 — and his laws of motion
   are still how we calculate a rocket's trajectory today."
4. The FINAL scene must end with a question, a follow/subscribe line, or
   a tease for more — never just stop on the last fact.
5. Vary sentence length and rhythm across scenes. Do not repeat the same
   sentence structure for every fact.
6. subject_qid must be the exact Wikidata QID given to you for that
   candidate, or null if none was given — never invent one.
7. Only state a specific number, date, or record as fact if it is in the
   RESEARCH NOTES you were given for that candidate; otherwise describe it
   qualitatively.
"""


def _rules_hook_placeholder() -> str:
    return "HOOK_STYLE_PLACEHOLDER"


def _build_user_prompt(candidates: list, observance_open: str, observance_close: str,
                       job_id: str, target_runtime_seconds: float, admin_note: str = "") -> str:
    blocks = []
    for i, c in enumerate(candidates, 1):
        notes_block = research.prompt_block(c.get("research_notes") or [])
        blocks.append(
            f"CANDIDATE {i}:\n"
            f"  Fact: {c['text']}\n"
            f"  Year: {c.get('year')}\n"
            f"  Wikidata QID: {c.get('qid') or 'null'}\n"
            f"{notes_block}"
        )
    header = ""
    if observance_open:
        header += (f"Today is also a recognized observance. Make the VERY FIRST scene a 1-2 "
                   f"second greeting: \"{observance_open}\" fused naturally into the hook, and "
                   f"make the LAST scene's closing line incorporate: \"{observance_close}\"\n\n")
    if admin_note:
        # A human reviewer asked for this specific video to be regenerated
        # with this guidance (set via the admin panel -- videos.admin_note,
        # consumed once by orchestrator.py). Surfaced as a hard instruction,
        # not a suggestion, since it's the one signal in this whole pipeline
        # that came from an actual person who watched the last attempt.
        header += (f"A human reviewer asked for this video to be redone with this specific "
                   f"guidance -- follow it closely: \"{admin_note}\"\n\n")

    return (
        header +
        f"Target total spoken runtime: about {target_runtime_seconds:.0f} seconds "
        f"(~{target_runtime_seconds * 2.5:.0f} words total across all scenes).\n\n" +
        "\n\n".join(blocks)
    )


def _call_gemini(system_prompt: str, user_prompt: str, temperature: float) -> str:
    from engine import api_budget
    api_key = get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set.")
    from google import genai
    client = genai.Client(api_key=api_key)
    # Google retires Gemini model names over time — "gemini-2.5-flash" was
    # this project's original default but is already gone for new API keys
    # as of October 2026 (confirmed via the API's own error message, which
    # names the current replacement). If this ever 404s again with a
    # "no longer available" message, that message names the correct
    # current model — put it in GEMINI_MODEL in .env rather than waiting
    # for a code update, since this default will drift again.
    model = get("GEMINI_MODEL") or "gemini-3.8-flash"
    try:
        resp = client.models.generate_content(
            model=model,
            contents=f"{system_prompt}\n\n{user_prompt}",
            config={"temperature": temperature, "response_mime_type": "application/json"},
        )
        return resp.text
    except Exception as e:
        if api_budget.is_quota_error(e):
            raise
        raise RuntimeError(f"Gemini call failed: {e}") from e


def _extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    return json.loads(text)


def generate_storyboard(job: dict, job_id: str, observance_open: str = "",
                        observance_close: str = "", db=None, admin_note: str = "") -> dict:
    """Returns {"title", "description", "hashtags", "scenes": [...], "provider": "gemini"|"groq"|...}.

    `admin_note`: optional human-reviewer guidance from the admin panel
    (videos.admin_note on a video marked status='regenerate_requested'),
    threaded straight into the prompt -- see orchestrator.py for where
    this gets read and cleared."""
    from engine import api_budget
    category, candidates = job["category"], job["candidates"]
    part_label = f", part {job['part_number']}" if job.get("part_number") else ""
    runtime = float(get("TARGET_RUNTIME_SECONDS", "52"))

    system_prompt = _build_system_prompt(category, part_label).replace(
        "HOOK_STYLE_PLACEHOLDER", _hook_for_job(job_id))
    user_prompt = _build_user_prompt(candidates, observance_open, observance_close, job_id, runtime,
                                     admin_note=admin_note)
    temperature = float(get("GEMINI_TEMPERATURE", "0.9"))

    provider = "gemini"
    budget = api_budget.llm_budget(db) if db else None
    try:
        if budget:
            budget.require(1, what=f"script for {category}{part_label}")
        text = _call_gemini(system_prompt, user_prompt, temperature)
        if budget:
            budget.spend(1)
    except Exception as e:
        if budget and api_budget.is_quota_error(e):
            budget.hard_stop(str(e))
        print(f"[script_generator] Gemini failed ({e}); trying free backup providers.")
        if not llm_router.any_backup_available():
            raise
        text, provider = llm_router.call(system_prompt, user_prompt, temperature)

    data = _extract_json(text)
    data["provider"] = provider
    return data
