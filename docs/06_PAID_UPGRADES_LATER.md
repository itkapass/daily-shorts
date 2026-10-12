# 6. Optional Paid Upgrades (anytime later, zero code changes)

Everything below is already built and wired in, switched **off** by
default. Turning any of these on is just adding an env var / API key —
no code to touch, per Section 11 of the build spec.

## Cloned voice (self-hosted, still free)

Uses Coqui XTTS to clone a specific voice (yours, or another consenting
speaker's — never without ownership/consent).

1. `pip install TTS` (not installed by default — pulls in ~2GB of model
   weights on first run).
2. Record a clean 10-20 second sample, no background noise, save as
   `.wav`.
3. `.env`:
   ```
   VOICE_PROVIDER=cloned
   XTTS_SPEAKER_WAV_PATH=assets/voice_samples/my_voice.wav
   ```
GitHub Actions' free runners are CPU-only, so this renders slower than
the cloud TTS tiers — expected and accepted; render time isn't a
constraint for this project.

## ElevenLabs voice (paid)

Characters-based billing; supports instant voice cloning with commercial
rights at the Starter tier and above.

1. [elevenlabs.io](https://elevenlabs.io) → sign up → **Profile → API
   Keys** → create one.
2. Pick a voice → copy its **Voice ID**. The default baked into
   `engine/elevenlabs_tts.py` (ElevenLabs' public "Rachel" voice) is
   US-accented — for this channel's Indian audience, use ElevenLabs'
   **Voice Library** search and filter by accent/language to find an
   Indian-English voice instead (several community ones exist free to
   use), or clone one (own voice / explicit consent only, per docs
   above).
3. `.env`:
   ```
   VOICE_PROVIDER=paid
   ELEVENLABS_API_KEY=...
   ELEVENLABS_VOICE_ID=...
   ```

## Paid stock video / AI-generated abstract B-roll for history events

For "This Day in History" events with no good archival photo on
Wikimedia Commons (a treaty signing, a scientific milestone — anything
with no single identifiable face), this project can generate an
**abstract, non-literal** illustration instead of falling back to a
plain text card.

**Scope, strictly enforced (Section 12 of the build spec):** this is
ONLY for abstract/non-person imagery. It will never generate a sketch or
likeness of a real, named person — `engine/ai_visuals.py` has a hard
refusal check for person-shaped prompts on top of the prompt wording
itself.

1. [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
   → **New token** → role **Read**.
2. `.env`:
   ```
   HUGGINGFACE_API_KEY=...
   HUGGINGFACE_IMAGE_MODEL=black-forest-labs/FLUX.1-schnell
   ```

A genuine paid stock-video API (e.g. a licensed footage library) is not
wired in by default since none has a meaningful free tier for this use
case — if you add one later, it slots into `engine/orchestrator.py`'s
scene-visual fallback chain (`visual_matcher` → your new provider →
`ai_visuals` → `text_card`) the same way `ai_visuals.py` does now.

## Multiple language tracks

This project ships the fonts needed for a Tamil track
(`assets/fonts/NotoSansTamil-Bold.ttf`, already included) as a starting
point for expansion — adding a second language track means duplicating
`script_generator.py`'s prompt to request that language and pointing
`subtitle_engine.py`'s `font_file` at the matching font for scenes in
that language. Not built further than that scaffold, since it's a real
content decision (which videos get a second track, and whether that's a
separate upload or a second audio/caption track on the same video) best
made once you know this channel's audience.
