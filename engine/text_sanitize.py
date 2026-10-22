"""
text_sanitize.py — strips characters a given font can't actually render.
============================================================================
Found via a real bug: Gemini-generated script text sometimes contains
"smart typography" Unicode (exotic space/punctuation variants it uses to
avoid an awkward line-break, e.g. around a date like "13 October 1980")
that this project's bundled font (assets/fonts/Montserrat-Variable.ttf)
has no real glyph for. PIL/FreeType then silently substitutes the font's
.notdef glyph — a visible empty box ("tofu") — right in the middle of the
sentence, on screen, in a real user-facing video (first caught in a
generated card reading "13<tofu>October<tofu>1980").

This doesn't hardcode a denylist of "known bad" codepoints, because the
actual offending codepoint turned out NOT to be any of the usual suspects
(NBSP, non-breaking hyphen, narrow no-break space, word joiner — all of
which this font renders FINE) — it could be something else entirely, and
a different font swapped in later would have a different gap. Instead,
this checks empirically, against the actual loaded font, whether each
non-ASCII character renders as that font's real .notdef box, and only
replaces the ones that do. That makes it correct regardless of which
exact character a future model response contains or which font is in use.
"""
import unicodedata

from PIL import Image, ImageDraw, ImageFont

_PUA_PROBE = ""  # Private Use Area codepoint: guaranteed unmapped in
                        # any normal font, so its rendered size IS that
                        # font's .notdef/"tofu" box — the signature we
                        # compare every other character against.

_tofu_size_cache = {}


def _tofu_size(font: ImageFont.FreeTypeFont, draw: ImageDraw.ImageDraw):
    key = id(font)
    if key not in _tofu_size_cache:
        bbox = draw.textbbox((0, 0), _PUA_PROBE, font=font)
        _tofu_size_cache[key] = (bbox[2] - bbox[0], bbox[3] - bbox[1])
    return _tofu_size_cache[key]


def _fallback_for(ch: str) -> str:
    """What to substitute for a character this font can't render, picked
    from the character's own Unicode category so the substitution stays
    typographically sensible (a missing space-like char becomes a space,
    a missing dash-like char becomes a hyphen) rather than just vanishing
    or leaving a box."""
    category = unicodedata.category(ch)
    if category == "Zs":          # any Unicode space separator
        return " "
    if category == "Pd":          # any dash/hyphen variant
        return "-"
    if category in ("Pi", "Pf"):  # initial/final quotation marks
        return '"'
    # Try stripping accents/compatibility formatting down to plain ASCII
    # (e.g. a ligature or stylized digit) before giving up.
    decomposed = unicodedata.normalize("NFKD", ch)
    ascii_fallback = decomposed.encode("ascii", "ignore").decode("ascii")
    if ascii_fallback:
        return ascii_fallback
    # Nothing usable came out of decomposition (true edge case — some
    # symbol with no ASCII equivalent at all). A space is the safe
    # default: it can never visibly break like a box, and it's far less
    # confusing than silently splicing two words together.
    return " "


def sanitize_for_font(text: str, font: ImageFont.FreeTypeFont) -> str:
    """Returns `text` with every character the given font would render as
    a .notdef box replaced by a sensible plain-ASCII fallback. Characters
    the font can render (including ordinary accented letters, em dashes,
    curly quotes, etc. that this specific bundled font does support) pass
    through untouched."""
    if not text:
        return text
    draw = ImageDraw.Draw(Image.new("RGB", (4, 4)))
    tofu_size = _tofu_size(font, draw)
    out = []
    for ch in text:
        if ch.isascii() or ch in "\n\t":
            out.append(ch)
            continue
        bbox = draw.textbbox((0, 0), ch, font=font)
        size = (bbox[2] - bbox[0], bbox[3] - bbox[1])
        if size == tofu_size:
            out.append(_fallback_for(ch))
        else:
            out.append(ch)
    return "".join(out)
