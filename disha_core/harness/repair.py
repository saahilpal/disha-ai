"""Repair Loop and Constrained Fallback Engine.

Re-prompts the model with specific feedback up to 2 times upon verification failure.
If still non-compliant after 2 attempts, applies deterministic constrained fallbacks.
Clearly labels system errors without generating fake Disha utterances.
"""

from __future__ import annotations

import logging
from typing import Any

from disha_core.harness.verifier import VerificationResult, VerificationViolation, verify_response

logger = logging.getLogger("disha_core.harness.repair")


def format_system_error(category: str, message: str = "Kripya thodi der baad koshish karein.") -> str:
    """Format clearly labeled system errors, never disguising as Disha utterances."""
    return f"[System Error: {category}. {message}]"


def apply_constrained_fallback(
    text: str,
    violations: tuple[VerificationViolation, ...] | list[VerificationViolation],
    context: dict[str, Any],
) -> str:
    """Apply deterministic fallback replacements when repairs fail."""
    current = text
    for v in violations:
        if v.replacement_text:
            current = v.replacement_text
            break
    # If no replacement text, return sanitized text
    res = verify_response(current, context)
    return res.sanitized_text


async def repair_turn(
    llm_client: Any,
    prompt: str,
    draft_text: str,
    verification: VerificationResult,
    context: dict[str, Any],
    messages: list[dict[str, str]] | None = None,
    system_prompt: str | None = None,
    max_attempts: int = 2,
) -> tuple[str, bool, list[str]]:
    """Execute the repair loop re-prompting model up to max_attempts with specific feedback."""
    if verification.is_valid:
        return draft_text, True, []

    current_text = draft_text
    violations = list(verification.violations)
    repaired_violations: list[str] = [v.check_name for v in violations]

    for attempt in range(1, max_attempts + 1):
        feedback_bullets = "\n".join(f"- {v.specific_feedback}" for v in violations)
        repair_prompt = (
            f"{prompt}\n\n"
            f"[REVISION REQUIRED - ATTEMPT {attempt}/{max_attempts}]\n"
            f"Your previous response had the following rule violations:\n"
            f"{feedback_bullets}\n"
            f"Regenerate your response completely to strictly comply with these rules. Return plain text only."
        )

        try:
            chunks: list[str] = []
            try:
                stream_iter = llm_client.stream(repair_prompt, messages=messages, system_prompt=system_prompt)
            except TypeError:
                try:
                    stream_iter = llm_client.stream(repair_prompt, messages=messages)
                except TypeError:
                    stream_iter = llm_client.stream(repair_prompt)

            async for chunk in stream_iter:
                if chunk:
                    chunks.append(chunk)

            candidate_text = "".join(chunks).strip()
            if candidate_text:
                candidate_res = verify_response(candidate_text, context)
                if candidate_res.is_valid:
                    logger.info("Response successfully repaired on attempt %d", attempt)
                    return candidate_text, True, repaired_violations
                violations = list(candidate_res.violations)
                current_text = candidate_text
        except Exception as exc:
            logger.warning("LLM call during repair attempt %d failed: %s", attempt, exc)
            break

    fallback = apply_constrained_fallback(current_text, violations, context)
    return fallback, False, repaired_violations
