"""
subtitle_engine.py — word-by-word caption cards with a moving highlight.
Adapted directly from the reference project (same punctuation-safe
grouping, same per-word highlight-while-speaking behaviour).
"""
from dataclasses import dataclass, field


@dataclass
class CaptionStyle:
    words_per_card: int = 3
    font_file: str = "assets/fonts/Montserrat-Variable.ttf"
    font_size: int = 72
    font_color: str = "#FFFFFF"
    highlight_color: str = "#FFD700"
    stroke_color: str = "#000000"
    stroke_width: int = 3
    position_y_ratio: float = 0.62
    max_width_ratio: float = 0.80
    bg_box: bool = True
    bg_color: str = "#00000066"
    bg_padding: int = 18


@dataclass
class CaptionCard:
    words: list
    start_time: float
    end_time: float
    is_hook: bool = False
    word_times: list = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(self.words)

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    def active_index(self, t: float) -> int:
        for i, (ws, we) in enumerate(self.word_times):
            if ws <= t < we:
                return i
        return -1


_BREAK_CHARS = ".!?"
_SOFT_BREAK_CHARS = ",;:"


def build_caption_cards(word_timestamps: list, style: CaptionStyle = None) -> list:
    style = style or CaptionStyle()
    if not word_timestamps:
        return []
    cards, current, first = [], [], True

    def flush():
        nonlocal current, first
        if not current:
            return
        words = [w["word"] for w in current]
        times = [(float(w["start"]), float(w["end"])) for w in current]
        cards.append(CaptionCard(words=words, start_time=times[0][0], end_time=times[-1][1],
                                 is_hook=first, word_times=times))
        current = []
        first = False

    for w in word_timestamps:
        text = str(w.get("word", "")).strip()
        if not text:
            continue
        current.append(w)
        last_char = text[-1:]
        if last_char in _BREAK_CHARS:
            flush()
        elif last_char in _SOFT_BREAK_CHARS and len(current) >= 2:
            flush()
        elif len(current) >= style.words_per_card:
            flush()
    flush()

    for i in range(len(cards) - 1):
        cards[i].end_time = min(cards[i].end_time, cards[i + 1].start_time - 0.03)

    print(f"[subtitle_engine] Generated {len(cards)} caption cards")
    return cards


def get_active_card(cards: list, t: float):
    for card in cards:
        if card.start_time <= t <= card.end_time:
            return card
    return None


def export_srt(cards: list, output_path: str) -> str:
    def fmt(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{h:02}:{m:02}:{s:02},{ms:03}"

    lines = []
    for i, card in enumerate(cards, 1):
        lines += [str(i), f"{fmt(card.start_time)} --> {fmt(card.end_time)}", card.text, ""]
    content = "\n".join(lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[subtitle_engine] SRT exported: {output_path}")
    return output_path
