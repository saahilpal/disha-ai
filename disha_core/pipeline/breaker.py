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


# Clinical red flag emergency lexicon with clinician-reviewed terms and colloquial Hinglish variants.
EMERGENCY_PATTERNS: dict[str, tuple[str, ...]] = {
    "CARDIOVASCULAR": (
        "chest pain", "chest pressure", "heart attack", "severe chest pain",
        "myocardial infarction", "acute coronary syndrome", "angina pectoris", "cardiac arrest",
        "chhati mein dard", "chhati me dard", "chhati mein dabaav", "chhati mein dabav",
        "seene mein dard", "seene me dard", "seene mein dabaav", "seene mein dabav",
        "seene mein bhaari dabav", "seene mein bhari dabav",
        "crushing chest pain", "acute chest pain",
        "dil ka daura", "dil ka daura pada", "dil me dard", "dil mein dard",
        "left hand pain", "left arm pain", "chest tightness", "chest discomfort",
        "chaati mein dard", "chaati me dard", "chaati me dabav", "chaati mein dabav",
        "heart stopped", "heart stopped beating", "dhadkan ruk", "dhadkan band",
        "dil ki dhadkan ruk", "dil ki dhadkan band", "no pulse", "pulse nahi mil rahi", "pulseless",
        "tearing chest pain", "छाती में दर्द", "सीने में दर्द", "दिल का दौरा", "दिल में दर्द",
        "छाती में दबाव", "सीने में दबाव", "हार्ट अटैक", "दिल की धड़कन बंद", "धड़कन रुक गई",
        "नब्ज नहीं चल रही", "पल्स नहीं", "छाती में असहनीय दर्द", "सीने में बहुत तेज दर्द",
    ),
    "RESPIRATORY": (
        "cannot breathe", "can't breathe", "difficulty breathing", "not breathing",
        "respiratory distress", "acute respiratory distress", "respiratory failure",
        "severe shortness of breath", "shortness of breath",
        "saans nahi aa rahi", "saans ruk rahi", "saans lene mein dikkat",
        "saas lene mein takleef", "saas lene me taklif", "saas lene mein taklif",
        "saans phool rahi", "saas phool rahi", "dum ghut raha",
        "gasping for air", "choking", "suffocating", "asthma attack",
        "oxygen level", "throat is closing", "throat closing", "unable to breathe",
        "stopped breathing", "lips turning blue", "hoth neele", "cyanosis", "stridor",
        "severe anaphylaxis", "anaphylaxis", "anaphylactic shock",
        "saans bilkul atak", "saans atak rahi", "saas lene me bahut takleef",
        "gale me khana atak", "gala band ho raha", "saans band ho rahi",
        "सांस नहीं आ रही", "सांस रुक रही", "सांस लेने में दिक्कत", "सांस लेने में तकलीफ",
        "सांस फूल रही", "दम घुट रहा", "सांस बंद", "सांस पूरी तरह रुक गई",
        "ऑक्सीजन लेवल बहुत तेजी से गिर", "गले में खाना अटक", "सांस बंद हो रही है",
    ),
    "NEUROLOGICAL": (
        "stroke", "acute stroke", "face drooping", "one sided weakness", "slurred speech", "stroke symptoms",
        "hemiplegia", "transient ischemic attack", "facial droop", "suddenly paralyzed", "achanak behosh",
        "achanak chehra tedha", "bol nahi pa raha", "ek taraf kamzori",
        "chehra ek taraf latak", "loss of balance", "blackout ho gaya", "had a blackout", "sudden blackout", "blacked out", "blacking out", "lakwa mar", "mirgi ka daura",
        "worst headache of my life", "thunderclap headache", "grand mal", "epileptic seizure",
        "seizure", "convulsing", "unresponsive", "passed out", "completely unconscious",
        "zubaan ladkhada", "jhatke lag rahe",
        "चेहरा टेढ़ा", "बोल नहीं पा रहा", "एक तरफ कमजोरी", "लकवा", "अचानक बेहोश", "बेहोश", "स्ट्रोक", "मिर्गी का दौरा",
        "मरीज अचानक बेहोश", "मरीज अचेत", "अचेत हो गया", "शरीर में झटके", "दौरा पड़ रहा है", "बोलना बंद हो गया",
    ),
    "CRISIS": (
        "suicide", "kill myself", "end my life", "self harm", "want to die",
        "khudkushi", "jaan dena chahta", "apne aap ko maar", "zeher kha liya",
        "zeher", "poison", "apni jaan", "nasein kaat", "faansi", "faasi",
        "overdose", "sleeping pills", "hang myself", "hanging myself",
        "cutting my wrists", "cut my wrists", "rat poison", "toilet cleaner acid", "pesticide",
        "neend ki goliyan", "neend ki sari goliyan", "neend ki 50 goliyan",
        "keede maarne wali dawa", "building se kood",
        "आत्महत्या", "खुदकुशी", "जान देना चाहता", "अपने आप को मार", "ज़हर", "जहर", "फांसी",
        "नींद की सारी गोलियां", "नींद की गोलियां", "कीटनाशक ज़हर", "हाथ की नस काट", "फांसी लगाने",
    ),
    "TRAUMA": (
        "uncontrolled bleeding", "heavy bleeding", "major accident", "severe burn",
        "internal bleeding", "abdominal hemorrhage", "acute abdominal hemorrhage",
        "abdominal haemorrhage", "acute hemorrhage", "massive bleeding", "arterial bleeding",
        "shock", "hypovolemic shock", "septic shock", "cardiogenic shock",
        "patient is in shock", "in shock and collapsing",
        "bahut khoon beh", "tez khoon beh", "bada accident", "gehri chot",
        "khoon ki ulti", "blood vomiting", "head injury unconscious",
        "extensive burn", "khoon nikal", "goli lag", "chaku lag",
        "bleeding uncontrollably", "stabbed", "stab wound", "gunshot wound", "gunshot",
        "massive blood loss", "mass blood loss", "hematemesis", "hemoptysis",
        "coughing up bright red blood", "coughing up blood", "car accident",
        "severe active bleeding", "chaku lag gaya", "goli lag gayi", "sar toot gaya",
        "खून की उल्टी", "खून बह रहा", "बहुत खून", "बड़ा एक्सीडेंट", "गहरी चोट", "गंभीर रूप से जल",
        "गोली लग गई", "चाकू लग गया", "फव्वारे की तरह खून", "आग में गंभीर रूप से जल",
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
        cat_pats = [r"\s*".join(re.escape(word) for word in phrase.split()) for phrase in entries]
        if cat_pats:
            pattern = r"(?<!\w)(?:" + "|".join(cat_pats) + r")(?!\w)"
            compiled.append((category, re.compile(pattern, re.I), category))
    if spaced:
        compiled.extend((
            ("spaced chest pain", re.compile(r"(?<!\w)c\s*h\s*h\s*a\s*t\s*i.{0,12}(?:d\s*a\s*r\s*d|d\s*a\s*b\s*a\s*v)(?!\w)", re.I), "CARDIOVASCULAR"),
            ("spaced breathing distress", re.compile(r"(?<!\w)s\s*a\s*a\s*n\s*s.{0,16}(?:n\s*a\s*h\s*i|r\s*u\s*k)(?!\w)", re.I), "RESPIRATORY"),
            ("cardio regex", re.compile(r"\b(?:chhati|chaati|seene|chest|dil|myocardial|angina|heart)\b.{0,35}?\b(?:dard|daba+v|pressure|pain|attack|crushing|tightness|daura|infarction|pectoris|arrest|stopped)\b|\bleft\s+(?:hand|arm)\s+pain\b|\b(?:no|lost)\s+pulse\b|\bpulseless\b|(?:छाती|सीने|दिल|धड़कन).{0,35}?(?:दर्द|दबाव|दौरा|बंद|रुक)", re.I), "CARDIOVASCULAR"),
            ("respiratory regex", re.compile(r"\b(?:saans|saas|breath(?:e|ing)?|dum|respiratory)\b.{0,35}?\b(?:nahi|takleef|taklif|dikkat|ruk|choking|gasping|cannot|can't|phool|ghut|distress|failure|atak)\b|\basthma\s+attack\b|\bsuffocating\b|\b(?:throat\s+is\s+closing|throat\s+closing|anaphylaxis|stridor|lips\s+turning\s+blue)\b|\b(?:oxygen|spo2)\b.{0,25}?\b(?:drop|gir|fall|low|kam)\b|सांस.{0,25}?(?:नहीं|रुक|फूल|दिक्कत|तकलीफ|बंद|अटक)|ऑक्सीजन.{0,20}?गिर", re.I), "RESPIRATORY"),
            ("neuro regex", re.compile(r"\b(?:chehra|face)\b.{0,30}?\b(?:tedha|droop|latak)\b|\bslurred\s+speech\b|\bparalyz(?:ed|is)\b|\bbol\s+nahi\s+pa\b|\bbehosh\b|\bunconscious\b|\bstroke\b|\blakwa\b|\bmirgi\b|\b(?:seizure|convuls(?:ing|ion)|epilep|status\s+epilepticus)\b|\bthunderclap(?:\s+headache)?\b|\bworst\s+headache\b|\bunresponsive\b|\bpassed\s+out\b|चेहरा.{0,20}?टेढ़ा|लकवा|बेहोश|अचेत|मिर्गी", re.I), "NEUROLOGICAL"),
            ("crisis regex", re.compile(r"\bsuicide\b|\bkill\s+myself\b|\bend\s+my\s+life\b|\bself\s+harm\b|\bwant\s+to\s+die\b|\bkhudkushi\b|\bjaan\s+(?:dena|lena)\b|\bzeher\b|\bpoison\b|\bfaansi\b|\bfaasi\b|\b(?:overdose|sleeping\s+pills?|pesticide|rat\s+poison|cut(?:ting)?\s+(?:my\s+)?wrists?|hang(?:ing)?\s+myself)\b|\bneend\s+ki\s+.*goli|\b(?:tezaab|acid)\b.{0,20}?\b(?:pi|drank|pee)\b|आत्महत्या|खुदकुशी|ज़हर|फांसी|नींद\s+की.*गोली", re.I), "CRISIS"),
            ("trauma regex", re.compile(r"\b(?:khoon|blood|internal|abdominal|acute|arterial|massive)\b.{0,30}?\b(?:ulti|vomit|beh|nikal|heavy|arterial|bleeding|hemorrhage|haemorrhage|loss)\b|\b(?:hypovolemic|septic|cardiogenic)\s+shock\b|\b(?:in\s+shock|patient\s+is\s+in\s+shock)\b|\bextensive\s+burn\b|\bsevere\s+burn\b|\bhead\s+injury\b|\bgoli\s+lag\b|\bchaku\s+lag\b|\b(?:bleeding\s+uncontrollably|stabbed|stab\s+wound|gunshot(?:\s+wound)?|coughing\s+(?:up\s+)?blood|hemoptysis|hematemesis)\b|\b(?:chaku|goli)\b.{0,25}?(?:lag|mar|lagi|mara)\b|खून\s+(?:की\s+उल्टी|बह|निकल)|चाकू|गोली", re.I), "TRAUMA"),
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
        # Dual-pass zero-width normalization: handles both word separation and intra-word obfuscation
        stripped_zw = re.sub(r"[\u200b-\u200f\ufeff\u00ad\u2060-\u206f]", "", text)
        cleaned = re.sub(r"[\u200b-\u200f\ufeff\u00ad\u2060-\u206f]", " ", text)
        spaced = re.sub(r"[-_/.,;:!?।]+", " ", cleaned)
        spaced_no_zw = re.sub(r"[-_/.,;:!?।]+", " ", stripped_zw)
        raw = " ".join(unicodedata.normalize("NFKC", spaced).casefold().split())
        raw_no_zw = " ".join(unicodedata.normalize("NFKC", spaced_no_zw).casefold().split())

        candidates = (raw,) if raw == raw_no_zw else (raw, raw_no_zw)
        for candidate in candidates:
            found = self._automaton.find(candidate)
            if found:
                category, phrase = found
                if phrase == "blackout" and re.search(r"\bblackout\s+(?:curtains?|shades?|blinds?|drapes?|window)\b", candidate):
                    pass
                else:
                    return self._result(started, category, phrase)
            for phrase, pattern, category in self._regexes:
                match = pattern.search(candidate)
                if match:
                    return self._result(started, category, match.group(0) or phrase)
        return BreakerResult(False, elapsed_ms=(time.perf_counter_ns() - started) / 1_000_000)

    def _result(self, started: int, category: str, matched: str) -> BreakerResult:
        return BreakerResult(
            True, category, matched,
            self.scripts.get(category, "Yeh emergency ho sakti hai. Abhi 112 par call karein."),
            (time.perf_counter_ns() - started) / 1_000_000,
        )

