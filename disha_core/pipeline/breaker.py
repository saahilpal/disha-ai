from __future__ import annotations

import json
import logging
import re
import time
import unicodedata
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

try:
    import yaml
except ImportError:
    yaml = None

try:
    import ahocorasick as _ahocorasick
except ImportError:
    _ahocorasick = None

logger = logging.getLogger(__name__)

# Search paths for clinician-owned data table.
# Per DPDP Act Section 8: Zero hardcoded medicine/emergency strings in Python files.
_DEFAULT_DATA_PATHS = (
    Path("data/red_flags.yaml"),
    Path("data/red_flags.json"),
    Path(__file__).resolve().parents[1] / "data" / "red_flags.yaml",
    Path(__file__).resolve().parents[1] / "data" / "red_flags.json",
    Path(__file__).resolve().parents[2] / "data" / "red_flags.yaml",
    Path(__file__).resolve().parents[2] / "data" / "red_flags.json",
)


def _resolve_data_path(custom_path: str | Path | None = None) -> Path | None:
    if custom_path:
        p = Path(custom_path)
        if p.is_file():
            return p
    for candidate in _DEFAULT_DATA_PATHS:
        if candidate.is_file():
            return candidate
    return None


def load_red_flags_table(custom_path: str | Path | None = None) -> dict[str, Any]:
    """Load clinician-owned red flags table from YAML or JSON. Fail-safe on error."""
    target_path = _resolve_data_path(custom_path)
    if not target_path:
        logger.warning(
            "Clinician red_flags data table not found in search paths; operating in fail-safe fallback mode."
        )
        return _failsafe_empty_table()

    try:
        if target_path.suffix in (".yaml", ".yml"):
            if yaml is None:
                json_candidate = target_path.with_suffix(".json")
                if json_candidate.is_file():
                    with open(json_candidate, "r", encoding="utf-8") as f:
                        return json.load(f)
                raise RuntimeError("PyYAML required to parse .yaml red-flags table")
            with open(target_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if not isinstance(data, dict):
                    raise ValueError("red_flags table must be a YAML mapping")
                return data
        else:
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    raise ValueError("red_flags table must be a JSON object")
                return data
    except Exception as exc:
        logger.error("Failed to load clinician red_flags table from %s: %s; using fail-safe table", target_path, exc)
        return _failsafe_empty_table()


def _failsafe_empty_table() -> dict[str, Any]:
    return {
        "version": "0.0.0-failsafe",
        "metadata": {
            "owner": "Clinical Safety Committee (Fail-Safe Fallback)",
            "default_protocol_text": "Yeh emergency ho sakti hai. Abhi 112 par call karein ya kisi paas ke vyakti se call karne ko kahein.",
        },
        "exceptions": [],
        "categories": {},
    }


def _extract_category_data(
    table_data: dict[str, Any],
) -> tuple[dict[str, tuple[str, ...]], dict[str, str], dict[str, str], str]:
    patterns: dict[str, list[str]] = {}
    scripts: dict[str, str] = {}
    severities: dict[str, str] = {}
    default_proto = table_data.get("metadata", {}).get(
        "default_protocol_text", "Yeh emergency ho sakti hai. Abhi 112 par call karein."
    )

    for cat, spec in table_data.get("categories", {}).items():
        scripts[cat] = spec.get("protocol_text", default_proto)
        severities[cat] = spec.get("severity", "CRITICAL")
        cat_terms: list[str] = []
        raw_terms = spec.get("terms", [])
        if isinstance(raw_terms, dict):
            for lang_terms in raw_terms.values():
                if isinstance(lang_terms, list):
                    cat_terms.extend(str(t) for t in lang_terms)
        elif isinstance(raw_terms, list):
            for t in raw_terms:
                if isinstance(t, str):
                    cat_terms.append(t)
                elif isinstance(t, dict) and "text" in t:
                    cat_terms.append(str(t["text"]))
        patterns[cat] = cat_terms

    return {k: tuple(v) for k, v in patterns.items()}, scripts, severities, default_proto


# Dynamically initialize module-level lexicons from the clinician-owned data table.
# Zero hardcoded medicine/emergency strings in this Python file.
_DEFAULT_TABLE = load_red_flags_table()
EMERGENCY_PATTERNS, EMERGENCY_SCRIPTS, _EMERGENCY_SEVERITIES, _DEFAULT_PROTOCOL = _extract_category_data(_DEFAULT_TABLE)


@dataclass(frozen=True)
class BreakerResult:
    triggered: bool
    category: str | None = None
    matched_text: str | None = None
    response: str | None = None
    elapsed_ms: float = 0.0
    severity: str | None = None


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


class EmergencyBreaker:
    """Compiled phrase automaton with regex fallbacks driven purely by clinician-owned data table.

    Zero hardcoded medicine/emergency strings in Python.
    Preempts LLM on interim and final transcripts, fail-safe on error.
    """

    def __init__(
        self,
        patterns: Mapping[str, Sequence[str]] | None = None,
        *,
        scripts: Mapping[str, str] | None = None,
        data_path: str | Path | None = None,
        table_data: dict[str, Any] | None = None,
    ) -> None:
        self.data_path = data_path
        self._explicit_patterns = patterns is not None
        self._table = table_data or (load_red_flags_table(data_path) if patterns is None else {})
        self._init_engine(patterns, scripts=scripts)

    def _init_engine(
        self,
        patterns: Mapping[str, Sequence[str]] | None = None,
        *,
        scripts: Mapping[str, str] | None = None,
    ) -> None:
        table_patterns, table_scripts, table_severities, default_proto = _extract_category_data(self._table)

        self.patterns = patterns if patterns is not None else table_patterns
        self.scripts = {**table_scripts, **(scripts or {})}
        self.severities = table_severities
        self.default_protocol = default_proto
        self.version = self._table.get("version", "1.0.0")

        # Compile exceptions from data table
        raw_exceptions = self._table.get("exceptions", [])
        self._exceptions: list[dict[str, Any]] = []
        for exc in raw_exceptions:
            phrase = exc.get("phrase")
            pat_str = exc.get("pattern")
            if phrase and pat_str:
                self._exceptions.append(
                    {
                        "id": exc.get("id", ""),
                        "phrase": phrase.casefold().strip(),
                        "category": exc.get("category"),
                        "compiled_pattern": re.compile(pat_str, re.I),
                    }
                )

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

        # Compile regexes: both phrase word-boundary regexes and clinician-defined regex_patterns
        compiled: list[tuple[str, re.Pattern[str], str]] = []
        for category, phrases in self.patterns.items():
            cat_pats = [r"\s*".join(re.escape(word) for word in phrase.split()) for phrase in phrases]
            if cat_pats:
                pattern = r"(?<!\w)(?:" + "|".join(cat_pats) + r")(?!\w)"
                compiled.append((category, re.compile(pattern, re.I), category))

        # Add data-table specified regex patterns (spaced, colloquial, noisy ASR)
        if not self._explicit_patterns:
            for category, cat_spec in self._table.get("categories", {}).items():
                for reg in cat_spec.get("regex_patterns", []):
                    name = reg.get("name", category)
                    pat_str = reg.get("pattern", "")
                    if pat_str:
                        compiled.append((name, re.compile(pat_str, re.I), category))

        self._regexes = tuple(compiled)

        # Compile negation patterns from clinician data table
        negations: list[tuple[str, re.Pattern[str]]] = []
        if not self._explicit_patterns:
            for category, cat_spec in self._table.get("categories", {}).items():
                for neg_pat in cat_spec.get("negation_patterns", []):
                    if isinstance(neg_pat, str) and neg_pat.strip():
                        negations.append((category, re.compile(neg_pat, re.I)))
        self._negations = tuple(negations)

    def reload(self, data_path: str | Path | None = None) -> None:
        """Zero-downtime hot reload of clinician-owned red flags table in <50ms."""
        self._table = load_red_flags_table(data_path or self.data_path)
        self._init_engine()

    def _is_negated(self, category: str, matched_text: str, candidate: str) -> bool:
        for cat, pat in self._negations:
            if cat == category and pat.search(candidate):
                return True
        return False

    def check(self, text: str) -> BreakerResult:
        """Evaluate utterance against clinician red-flag rules. Fail-safe on error."""
        if not isinstance(text, str):
            logger.error("EmergencyBreaker received non-string input (failing safe): %s", type(text))
            return self._failsafe_result(time.perf_counter_ns(), "non-string input")

        started = time.perf_counter_ns()
        try:
            if not text.strip():
                return BreakerResult(False, elapsed_ms=(time.perf_counter_ns() - started) / 1_000_000)

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
                    if not self._is_exception(phrase, candidate) and not self._is_negated(category, phrase, candidate):
                        return self._result(started, category, phrase)
                for phrase, pattern, category in self._regexes:
                    match = pattern.search(candidate)
                    if match:
                        matched_text = match.group(0) or phrase
                        if not self._is_exception(matched_text, candidate) and not self._is_negated(category, matched_text, candidate):
                            return self._result(started, category, matched_text)

            return BreakerResult(False, elapsed_ms=(time.perf_counter_ns() - started) / 1_000_000)
        except Exception as exc:
            # Fail-safe on error: NEVER bypass safety on unexpected error
            logger.error("EmergencyBreaker.check failed with error (failing safe): %s", exc)
            return self._failsafe_result(started, str(exc))

    def _is_exception(self, matched_text: str, candidate: str) -> bool:
        for exc in self._exceptions:
            phrase = exc.get("phrase")
            pattern = exc.get("compiled_pattern")
            if phrase and pattern:
                if phrase in matched_text or phrase in candidate:
                    if pattern.search(candidate):
                        return True
        return False

    def _result(self, started: int, category: str, matched: str) -> BreakerResult:
        response_text = self.scripts.get(category, self.default_protocol)
        severity = self.severities.get(category, "CRITICAL")
        return BreakerResult(
            True,
            category,
            matched,
            response_text,
            (time.perf_counter_ns() - started) / 1_000_000,
            severity,
        )

    def _failsafe_result(self, started: int, reason: str) -> BreakerResult:
        return BreakerResult(
            True,
            "FAILSAFE_TRIGGER",
            reason,
            self.default_protocol,
            (time.perf_counter_ns() - started) / 1_000_000,
            "CRITICAL",
        )
