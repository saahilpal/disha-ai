from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

ALIASES: dict[str, tuple[str, ...]] = {
    "GI_SYMPTOM_ACUTE": ("pet dard", "paet dard", "dast", "loose motions", "paet kharab"),
    "GI_BLOATING": ("bloating", "gas", "pet phoolna", "paet phoolna", "pet fulna"),
    "FRUIT_MODERATION": ("mango", "aam", "fruits", "fruit"),
}


@dataclass(frozen=True)
class NormalizedText:
    original: str
    normalized: str
    tags: tuple[str, ...]


@lru_cache(maxsize=1)
def _patterns() -> tuple[tuple[str, re.Pattern[str]], ...]:
    return tuple(
        (tag, re.compile(r"(?<!\w)(?:" + "|".join(re.escape(x) for x in aliases) + r")(?!\w)", re.I))
        for tag, aliases in ALIASES.items()
    )


def normalize(text: str) -> NormalizedText:
    normalized = " ".join(unicodedata.normalize("NFKC", text).casefold().split())
    tags = tuple(tag for tag, pattern in _patterns() if pattern.search(normalized))
    return NormalizedText(text, normalized, tags)

