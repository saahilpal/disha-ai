"""Hot-reloading policy loader for Disha AI Situation Policy Pack.

Enforces zero-restart updates, thread-safe atomic caching, Last Known Good (LKG)
resilience on syntax errors, and structured contextual prompt injection.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any, Mapping

import yaml  # type: ignore[import-untyped]

from disha_core.policies.schema import (
    ExampleLanguage,
    ExampleType,
    PolicyExample,
    PolicyPack,
    SituationPolicy,
)

logger = logging.getLogger("disha_core.policies.loader")


class PolicyPackError(Exception):
    """Base exception for policy pack operations."""


class PolicyNotFoundError(PolicyPackError):
    """Raised when the requested policy situation ID is not found."""


class PolicyValidationError(PolicyPackError):
    """Raised when policy pack fails schema validation."""


class PolicyPackLoader:
    """Thread-safe loader and cache for Situation Policy Pack with hot-reload capabilities."""

    DEFAULT_CANDIDATE_PATHS = [
        Path("data/behavior_policies.yaml"),
        Path("disha_core/data/behavior_policies.yaml"),
        Path(__file__).resolve().parent.parent / "data" / "behavior_policies.yaml",
        Path(__file__).resolve().parent.parent.parent / "data" / "behavior_policies.yaml",
    ]

    def __init__(self, policy_path: str | Path | None = None, auto_load: bool = True) -> None:
        self._custom_path: Path | None = Path(policy_path) if policy_path else None
        self._resolved_path: Path | None = None
        self._lock = threading.RLock()
        self._pack: PolicyPack | None = None
        self._policies_by_id: dict[str, SituationPolicy] = {}
        self._last_mtime: float = 0.0
        self._last_hash: str = ""
        self._last_error: Exception | None = None

        if auto_load:
            self.load()

    @property
    def path(self) -> Path:
        """Return the resolved path to behavior_policies.yaml."""
        if self._resolved_path is not None and self._resolved_path.exists():
            return self._resolved_path

        if self._custom_path is not None:
            if self._custom_path.exists():
                self._resolved_path = self._custom_path.resolve()
                return self._resolved_path
            raise FileNotFoundError(f"Configured policy file does not exist: {self._custom_path}")

        env_path = os.environ.get("DISHA_POLICY_PATH")
        if env_path:
            p = Path(env_path)
            if p.exists():
                self._resolved_path = p.resolve()
                return self._resolved_path

        for candidate in self.DEFAULT_CANDIDATE_PATHS:
            if candidate.exists():
                self._resolved_path = candidate.resolve()
                return self._resolved_path

        # If none found, fallback to first default candidate
        fallback = self.DEFAULT_CANDIDATE_PATHS[0].resolve()
        self._resolved_path = fallback
        return fallback

    def _calculate_file_hash(self, file_path: Path) -> str:
        """Compute SHA256 checksum of the policy file."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    def load(self, raise_on_error: bool = True) -> bool:
        """Load and validate policy pack from disk.

        If raise_on_error is False and an existing valid pack exists, preserves LKG on error.
        """
        with self._lock:
            target_path = self.path
            if not target_path.exists():
                err = FileNotFoundError(f"Policy pack file not found at {target_path}")
                self._last_error = err
                if raise_on_error:
                    raise err
                logger.error("Failed to load policy pack: %s", err)
                return False

            try:
                raw_mtime = os.path.getmtime(target_path)
                file_hash = self._calculate_file_hash(target_path)

                with open(target_path, "r", encoding="utf-8") as f:
                    raw_data = yaml.safe_load(f)

                if not isinstance(raw_data, dict):
                    raise PolicyValidationError(
                        f"Expected YAML mapping at root of policy file, got {type(raw_data).__name__}"
                    )

                pack = PolicyPack.model_validate(raw_data)
                policies_by_id = {p.situation_id: p for p in pack.policies}

                # Atomic swap
                self._pack = pack
                self._policies_by_id = policies_by_id
                self._last_mtime = raw_mtime
                self._last_hash = file_hash
                self._last_error = None
                logger.info(
                    "Successfully loaded %d situation policies (version %s) from %s",
                    len(policies_by_id),
                    pack.version,
                    target_path,
                )
                return True

            except Exception as e:
                self._last_error = e
                logger.error(
                    "Error parsing or validating policy pack from %s: %s",
                    target_path,
                    e,
                    exc_info=True,
                )
                if raise_on_error and self._pack is None:
                    if isinstance(e, (PolicyPackError, FileNotFoundError)):
                        raise
                    raise PolicyValidationError(f"Failed to validate policy pack: {e}") from e
                return False

    def reload(self, force: bool = False, raise_on_error: bool = False) -> bool:
        """Reload policy pack. If force is False, only reloads if file was modified."""
        with self._lock:
            if not force and not self.is_modified():
                return False
            return self.load(raise_on_error=raise_on_error)

    def reload_if_modified(self) -> bool:
        """Check mtime/hash and reload if file has changed. Preserves LKG on failure."""
        return self.reload(force=False, raise_on_error=False)

    def is_modified(self) -> bool:
        """Check if policy file on disk has changed since last load."""
        with self._lock:
            try:
                target_path = self.path
                if not target_path.exists():
                    return False
                current_mtime = os.path.getmtime(target_path)
                if current_mtime != self._last_mtime:
                    current_hash = self._calculate_file_hash(target_path)
                    return current_hash != self._last_hash
                return False
            except OSError:
                return False

    def get_policy(self, situation_id: str, auto_reload: bool = True) -> SituationPolicy | None:
        """Retrieve a situation policy by unique ID."""
        if auto_reload:
            self.reload_if_modified()

        with self._lock:
            return self._policies_by_id.get(situation_id)

    def require_policy(self, situation_id: str, auto_reload: bool = True) -> SituationPolicy:
        """Retrieve a situation policy by unique ID or raise PolicyNotFoundError."""
        policy = self.get_policy(situation_id, auto_reload=auto_reload)
        if policy is None:
            raise PolicyNotFoundError(f"Situation policy '{situation_id}' not found")
        return policy

    def get_all_policies(self, auto_reload: bool = True) -> dict[str, SituationPolicy]:
        """Return a mapping of all active situation policies."""
        if auto_reload:
            self.reload_if_modified()

        with self._lock:
            return dict(self._policies_by_id)

    def list_situations(self, auto_reload: bool = True) -> list[str]:
        """Return list of all situation IDs."""
        if auto_reload:
            self.reload_if_modified()

        with self._lock:
            return list(self._policies_by_id.keys())

    def get_examples(
        self,
        situation_id: str,
        example_type: str | ExampleType | None = None,
        language: str | ExampleLanguage | None = None,
        auto_reload: bool = True,
    ) -> list[PolicyExample]:
        """Retrieve filtered examples for a situation."""
        policy = self.get_policy(situation_id, auto_reload=auto_reload)
        if not policy:
            return []

        examples = policy.examples
        if example_type is not None:
            target_type = ExampleType(example_type) if isinstance(example_type, str) else example_type
            examples = [ex for ex in examples if ex.type == target_type]

        if language is not None:
            target_lang = ExampleLanguage(language) if isinstance(language, str) else language
            examples = [ex for ex in examples if ex.language == target_lang]

        return examples

    def match_situation(
        self,
        text: str,
        context: Mapping[str, Any] | None = None,
        auto_reload: bool = True,
    ) -> SituationPolicy | None:
        """Heuristic trigger matcher to map user utterance to a situation card.

        Evaluates emergency and safety-critical cards first, followed by specific intents.
        """
        if auto_reload:
            self.reload_if_modified()

        if not text or not text.strip():
            return self.get_policy("incomplete_message", auto_reload=False)

        normalized = text.strip().lower()

        # Check silence or extremely brief cutoff
        if len(normalized) <= 2 and normalized not in {"hi", "ha", "ok", "no", "ji"}:
            return self.get_policy("incomplete_message", auto_reload=False)

        # High-priority priority order for safety
        priority_checks = [
            "crisis_self_harm",
            "red_flag",
            "abusive_user",
            "medication_dose",
            "privacy_request",
        ]

        with self._lock:
            # 1. Evaluate high priority situations first
            for sit_id in priority_checks:
                policy = self._policies_by_id.get(sit_id)
                if policy and self._triggers_match(policy.triggers, normalized):
                    return policy

            # 2. Evaluate remaining situations
            for sit_id, policy in self._policies_by_id.items():
                if sit_id in priority_checks:
                    continue
                if self._triggers_match(policy.triggers, normalized):
                    return policy

        return None

    def _triggers_match(self, triggers: list[str], text: str) -> bool:
        """Check if any trigger pattern matches normalized text."""
        for trig in triggers:
            trig_clean = trig.strip().lower()
            if not trig_clean:
                continue
            # Regex trigger
            if trig_clean.startswith("^") or trig_clean.endswith("$") or "[" in trig_clean:
                try:
                    if re.search(trig_clean, text, re.IGNORECASE):
                        return True
                except re.error:
                    pass
            # Substring / keyword trigger
            if trig_clean in text:
                return True
        return False

    def format_situation_prompt(
        self,
        situation_id: str,
        include_examples: bool = True,
        max_examples: int = 2,
        language_filter: str | None = None,
        auto_reload: bool = True,
    ) -> str:
        """Format a situation card into lean, actionable XML prompt instructions for the LLM.

        Examples are retrieved strictly on-demand per situation and never hardcoded in SYSTEM_PROMPT.
        """
        policy = self.get_policy(situation_id, auto_reload=auto_reload)
        if not policy:
            return ""

        must_lines = "\n".join(f"    - MUST: {m}" for m in policy.must)
        must_not_lines = "\n".join(f"    - MUST NOT: {mn}" for mn in policy.must_not)
        moves_lines = "\n".join(f"    - {cm}" for cm in policy.coach_moves)

        parts = [
            f'<SITUATION_POLICY id="{policy.situation_id}" owner="{policy.owner}" version="{policy.version}">',
            f"  <OBJECTIVE>{policy.objective}</OBJECTIVE>",
            f"  <RESPONSE_SHAPE>{policy.response_shape}</RESPONSE_SHAPE>",
            "  <RULES>",
            must_lines,
            must_not_lines,
            "  </RULES>",
            "  <RECOMMENDED_COACH_MOVES>",
            moves_lines,
            "  </RECOMMENDED_COACH_MOVES>",
        ]

        if include_examples:
            good_examples = self.get_examples(
                situation_id,
                example_type=ExampleType.GOOD,
                language=language_filter,
                auto_reload=False,
            )
            selected_examples = good_examples[:max_examples]
            if selected_examples:
                parts.append("  <FEW_SHOT_GUIDANCE>")
                for idx, ex in enumerate(selected_examples, start=1):
                    parts.append(f'    <EXAMPLE id="{idx}" lang="{ex.language.value}">')
                    parts.append(f"      <PATIENT>{ex.user_input}</PATIENT>")
                    parts.append(f"      <COACH>{ex.response}</COACH>")
                    parts.append(f"      <RATIONALE>{ex.critique}</RATIONALE>")
                    parts.append("    </EXAMPLE>")
                parts.append("  </FEW_SHOT_GUIDANCE>")

        parts.append("</SITUATION_POLICY>")
        return "\n".join(parts)


_GLOBAL_LOADER: PolicyPackLoader | None = None
_GLOBAL_LOCK = threading.Lock()


def get_policy_loader(
    policy_path: str | Path | None = None,
    force_new: bool = False,
) -> PolicyPackLoader:
    """Retrieve or initialize the global singleton PolicyPackLoader."""
    global _GLOBAL_LOADER
    with _GLOBAL_LOCK:
        if _GLOBAL_LOADER is None or force_new:
            _GLOBAL_LOADER = PolicyPackLoader(policy_path=policy_path)
        return _GLOBAL_LOADER


def reset_policy_loader() -> None:
    """Reset the global singleton policy loader (useful in test teardowns)."""
    global _GLOBAL_LOADER
    with _GLOBAL_LOCK:
        _GLOBAL_LOADER = None
