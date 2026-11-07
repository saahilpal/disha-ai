from __future__ import annotations

import re
import time
import unicodedata
from collections import deque
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

try:
    import ahocorasick as _ahocorasick
except ImportError:
    _ahocorasick = None


# shortcut: built-in lexicon lacks 1,200 reviewed variants, load a clinician corpus before production.
EMERGENCY_PATTERNS: dict[str, tuple[str, ...]] = {
    "CARDIOVASCULAR": (
        "chest pain", "chest pressure", "heart attack", "severe chest pain",
        "chhati mein dard", "chhati me dard", "chhati mein dabaav", "chhati mein dabav",
        "seene mein dard", "seene me dard", "seene mein dabaav", "seene mein dabav",
        "seene mein bhaari dabav", "seene mein bhari dabav",
        "cardiac arrest", "crushing chest pain", "acute chest pain",
    ),
    "RESPIRATORY": (
        "cannot breathe", "can't breathe", "difficulty breathing", "not breathing",
        "saans nahi aa rahi", "saans ruk rahi", "saans lene mein dikkat",
        "saas lene mein takleef", "gasping for air", "choking", "suffocating", "asthma attack",
        "oxygen level",
    ),
    "NEUROLOGICAL": (
        "face drooping", "one sided weakness", "slurred speech", "stroke symptoms",
        "achanak chehra tedha", "bol nahi pa raha", "ek taraf kamzori",
        "chehra ek taraf latak", "facial droop", "suddenly paralyzed", "achanak behosh",
        "loss of balance", "blackout",
    ),
    "CRISIS": (
        "suicide", "kill myself", "end my life", "self harm", "want to die",
        "khudkushi", "jaan dena chahta", "apne aap ko maar", "zeher kha liya",
        "zeher", "poison",
    ),
    "TRAUMA": (
        "uncontrolled bleeding", "heavy bleeding", "major accident", "severe burn",
        "bahut khoon beh", "tez khoon beh", "bada accident", "gehri chot",
        "khoon ki ulti", "blood vomiting", "head injury unconscious", "arterial bleeding",
        "extensive burn",
    ),
}

EMERGENCY_SCRIPTS = {
    "CARDIOVASCULAR": "Yeh emergency ho sakti hai. Abhi 112 par call karein ya kisi paas ke vyakti se call karne ko kahein.",
    "RESPIRATORY": "Yeh emergency ho sakti hai. Abhi 112 par call karein ya kisi paas ke vyakti se call karne ko kahein.",
    "NEUROLOGICAL": "Yeh emergency ho sakti hai. Abhi 112 par call karein ya kisi paas ke vyakti se call karne ko kahein.",
    "CRISIS": "Agar aap turant khatre mein hain, 112 par call karein ya kisi bharosemand vyakti ke paas jaayen. Tele-MANAS se 14416 par bhi baat kar sakte hain.",
    "TRAUMA": "Yeh emergency ho sakti hai. Abhi 112 par call karein aur paas ke kisi vyakti se madad lein.",
}


@dataclass(frozen=True)
class BreakerResult:
    triggered: bool
    category: str | None = None
    matched_text: str | None = None
    response: str | None = None
    elapsed_ms: float = 0.0


class _PythonAhoCorasick:
    def __init__(self, entries: Iterable[tuple[str, str]]) -> None:
        self.goto: list[dict[str, int]] = [{}]
        self.fail: list[int] = [0]
        self.output: list[list[tuple[str, str]]] = [[]]
        for pattern, category in entries:
            state = 0
            for char in pattern:
                if char not in self.goto[state]:
                    self.goto[state][char] = self._new_state()
                state = self.goto[state][char]
            self.output[state].append((pattern, category))
        queue: deque[int] = deque()
        for state in self.goto[0].values():
            queue.append(state)
        while queue:
            state = queue.popleft()
            for char, child in self.goto[state].items():
                queue.append(child)
                fallback = self.fail[state]
                while fallback and char not in self.goto[fallback]:
                    fallback = self.fail[fallback]
                self.fail[child] = self.goto[fallback].get(char, 0)
                self.output[child].extend(self.output[self.fail[child]])

    def _new_state(self) -> int:
        self.goto.append({})
        self.fail.append(0)
        self.output.append([])
        return len(self.goto) - 1

    def find(self, text: str) -> tuple[str, str] | None:
        state = 0
        for index, char in enumerate(text):
            while state and char not in self.goto[state]:
                state = self.fail[state]
            state = self.goto[state].get(char, 0)
            for pattern, category in self.output[state]:
                start = index - len(pattern) + 1
                left_ok = start == 0 or not (text[start - 1].isalnum() or text[start - 1] == "_")
                right_ok = index + 1 == len(text) or not (text[index + 1].isalnum() or text[index + 1] == "_")
                if left_ok and right_ok:
                    return category, pattern
        return None


class _AhoCorasick:
    def __init__(self, entries: Iterable[tuple[str, str]]) -> None:
        entries = tuple(entries)
        self._fallback: _PythonAhoCorasick | None = None
        self._native: Any = None
        if _ahocorasick is None:
            self._fallback = _PythonAhoCorasick(entries)
            return
        automaton = _ahocorasick.Automaton()
        for phrase, category in entries:
            automaton.add_word(phrase, (phrase, category))
        automaton.make_automaton()
        self._native = automaton

    def find(self, text: str) -> tuple[str, str] | None:
        if self._fallback is not None:
            return self._fallback.find(text)
        assert self._native is not None
        for end, (phrase, category) in self._native.iter(text):
            start = end - len(phrase) + 1
            left_ok = start == 0 or not (text[start - 1].isalnum() or text[start - 1] == "_")
            right_ok = end + 1 == len(text) or not (text[end + 1].isalnum() or text[end + 1] == "_")
            if left_ok and right_ok:
                return category, phrase
        return None


def _compile_regex(
    phrase_map: Mapping[str, Sequence[str]], *, spaced: bool
) -> tuple[tuple[str, re.Pattern[str], str], ...]:
    compiled: list[tuple[str, re.Pattern[str], str]] = []
    for category, entries in phrase_map.items():
        for phrase in entries:
            words = phrase.split()
            # Some Hinglish speech-to-text inserts spaces between syllables/words.
            pattern = r"(?<!\w)" + r"\s*".join(re.escape(word) for word in words) + r"(?!\w)"
            compiled.append((phrase, re.compile(pattern, re.I), category))
    if spaced:
        compiled.extend((
            ("spaced chest pain", re.compile(r"(?<!\w)c\s*h\s*h\s*a\s*t\s*i.{0,12}(?:d\s*a\s*r\s*d|d\s*a\s*b\s*a\s*v)(?!\w)", re.I), "CARDIOVASCULAR"),
            ("spaced breathing distress", re.compile(r"(?<!\w)s\s*a\s*a\s*n\s*s.{0,16}(?:n\s*a\s*h\s*i|r\s*u\s*k)(?!\w)", re.I), "RESPIRATORY"),
            ("cardio regex", re.compile(r"\b(?:chhati|seene|chest)\b.{0,35}?\b(?:dard|daba+v|pressure|pain|attack|crushing)\b", re.I), "CARDIOVASCULAR"),
            ("respiratory regex", re.compile(r"\b(?:saans|saas|breath(?:e|ing)?)\b.{0,35}?\b(?:nahi|takleef|dikkat|ruk|choking|gasping|cannot|can't)\b|\basthma\s+attack\b|\bsuffocating\b", re.I), "RESPIRATORY"),
            ("neuro regex", re.compile(r"\b(?:chehra|face)\b.{0,30}?\b(?:tedha|droop|latak)\b|\bslurred\s+speech\b|\bparalyz(?:ed|is)\b|\bbol\s+nahi\s+pa\b|\bbehosh\b|\bunconscious\b|\bstroke\b", re.I), "NEUROLOGICAL"),
            ("crisis regex", re.compile(r"\bsuicide\b|\bkill\s+myself\b|\bend\s+my\s+life\b|\bself\s+harm\b|\bwant\s+to\s+die\b|\bkhudkushi\b|\bjaan\s+dena\b|\bzeher\b|\bpoison\b", re.I), "CRISIS"),
            ("trauma regex", re.compile(r"\b(?:khoon|blood)\b.{0,30}?\b(?:ulti|vomit|beh|heavy|arterial)\b|\bextensive\s+burn\b|\bsevere\s+burn\b|\bhead\s+injury\b", re.I), "TRAUMA"),
        ))
    return tuple(compiled)


class EmergencyBreaker:
    """Compiled phrase automaton with regex fallbacks; elapsed time is diagnostic only.

    The built-in phrases are a development starter set. Production deployments must
    provide a clinician-reviewed corpus; matching cannot guarantee emergency coverage.
    """

    def __init__(
        self,
        patterns: Mapping[str, Sequence[str]] | None = None,
        *,
        scripts: Mapping[str, str] | None = None,
    ) -> None:
        self.patterns = patterns if patterns is not None else EMERGENCY_PATTERNS
        self.scripts = {**EMERGENCY_SCRIPTS, **(scripts or {})}
        entries: list[tuple[str, str]] = []
        seen: dict[str, str] = {}
        for category, phrases in self.patterns.items():
            if not isinstance(category, str) or not category.strip():
                raise ValueError("emergency categories must be non-empty strings")
            for phrase in phrases:
                if not isinstance(phrase, str) or not phrase.strip():
                    raise ValueError("emergency phrases must be non-empty strings")
                normalized = phrase.casefold().strip()
                if normalized in seen and seen[normalized] != category:
                    raise ValueError(f"emergency phrase has conflicting categories: {phrase}")
                if normalized not in seen:
                    entries.append((normalized, category))
                    seen[normalized] = category
        if not entries:
            raise ValueError("at least one emergency phrase is required")
        self._automaton = _AhoCorasick(entries)
        self.pattern_count = len(entries)
        self._regexes = _compile_regex(
            self.patterns, spaced=patterns is None
        )

    def check(self, text: str) -> BreakerResult:
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        started = time.perf_counter_ns()
        raw = " ".join(unicodedata.normalize("NFKC", text).casefold().split())
        found = self._automaton.find(raw)
        if found:
            category, phrase = found
            return self._result(started, category, phrase)
        for phrase, pattern, category in self._regexes:
            match = pattern.search(raw)
            if match:
                return self._result(started, category, match.group(0) or phrase)
        return BreakerResult(False, elapsed_ms=(time.perf_counter_ns() - started) / 1_000_000)

    def _result(self, started: int, category: str, matched: str) -> BreakerResult:
        return BreakerResult(
            True, category, matched,
            self.scripts.get(category, "Yeh emergency ho sakti hai. Abhi 112 par call karein."),
            (time.perf_counter_ns() - started) / 1_000_000,
        )

