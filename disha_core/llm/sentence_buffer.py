from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from disha_core.engine.anti_echo import (
    is_clinical_safety_statement,
)
from disha_core.pipeline.validator import MEAL_NOT_FOUND_REPLACEMENT


class SentenceBuffer:
    """Collect streamed text and return complete sentences at punctuation boundaries."""

    _BOUNDARIES = {".", "!", "?", "।"}

    def __init__(self) -> None:
        self._buffer = ""
        self._pending_period = False

    def feed(self, chunk: str) -> list[str]:
        complete: list[str] = []
        for index, char in enumerate(chunk):
            if self._pending_period:
                self._pending_period = False
                if not (char.isdigit() and len(self._buffer) > 1 and self._buffer[-2].isdigit()):
                    sentence, self._buffer = self._buffer.strip(), ""
                    if sentence:
                        complete.append(sentence)
            self._buffer += char
            if char not in self._BOUNDARIES:
                continue
            if char == "." and len(self._buffer) > 1 and self._buffer[-2].isdigit():
                if index + 1 == len(chunk):
                    self._pending_period = True
                    continue
                if chunk[index + 1].isdigit():
                    continue
            sentence, self._buffer = self._buffer.strip(), ""
            if sentence:
                complete.append(sentence)
        # If a deferred decimal point was followed by a digit, it belongs to the number.
        # If it was followed by anything else, the sentence was emitted above.
        return complete

    def flush(self) -> str | None:
        remainder, self._buffer = self._buffer.strip(), ""
        self._pending_period = False
        return remainder or None


async def validated_sentences(
    chunks: AsyncIterator[str], validator: Any, context: dict[str, Any] | None = None
) -> AsyncIterator[str]:
    """Yield validated sentences only; never expose raw model tokens to the caller."""
    context = context or {}

    if "GI_BLOATING" in (context.get("clinical_tags") or ()):
        result = validator.validate_turn("", context)
        await _close(chunks)
        yield validator.sanitize_for_tts(result.text)
        return

    intent = getattr(context.get("intent", ""), "value", context.get("intent", ""))
    if context.get("diet_status") == "NOT_FOUND" and str(intent).upper() in {"MEAL_QUERY", "RECIPE"}:
        result = validator.validate_sentence(MEAL_NOT_FOUND_REPLACEMENT, context)
        yield validator.sanitize_for_tts(result.text)
        await _close(chunks)
        return

    # Dynamic length targeting policy
    policy = context.get("length_policy")
    max_sentences: int = 4
    if policy is not None:
        val = getattr(policy, "max_sentences", None) or (
            policy.get("max_sentences") if isinstance(policy, dict) else None
        )
        if isinstance(val, int) and val > 0:
            max_sentences = val

    buffer = SentenceBuffer()
    first_sentence = True
    emitted = 0
    last_emitted: str | None = None

    async for chunk in chunks:
        for sentence in buffer.feed(chunk):
            result = (
                validator.validate_turn(sentence, context)
                if first_sentence
                else validator.validate_sentence(sentence, context)
            )
            sanitized = validator.sanitize_for_tts(result.text)
            if not sanitized or sanitized == last_emitted:
                continue

            first_sentence = False
            emitted += 1
            last_emitted = sanitized
            yield sanitized

            # If we've reached max_sentences, check if an essential clinical safety statement is pending
            if (
                emitted >= max_sentences
                or "remedy_assertion" in result.reasons
                or "remedy_not_configured" in result.reasons
            ):
                if "remedy_assertion" in result.reasons or "remedy_not_configured" in result.reasons:
                    await _close(chunks)
                    return

                # Before aborting, allow an essential clinical safety disclaimer if present next
                safety_sentence = None
                for pending in buffer.feed(""):
                    if is_clinical_safety_statement(pending):
                        safety_sentence = pending
                        break
                if not safety_sentence:
                    try:
                        async for next_chunk in chunks:
                            for next_s in buffer.feed(next_chunk):
                                if is_clinical_safety_statement(next_s):
                                    safety_sentence = next_s
                                break
                            if safety_sentence is not None:
                                break
                    except Exception:
                        pass
                if safety_sentence:
                    safety_res = validator.validate_sentence(safety_sentence, context)
                    safety_sanitized = validator.sanitize_for_tts(safety_res.text)
                    if safety_sanitized and safety_sanitized != last_emitted:
                        last_emitted = safety_sanitized
                        yield safety_sanitized

                await _close(chunks)
                return

    remainder = buffer.flush()
    if remainder:
        result = validator.validate_turn(remainder, context) if first_sentence else validator.validate_sentence(remainder, context)
        sanitized = validator.sanitize_for_tts(result.text)
        if sanitized and sanitized != last_emitted and (emitted < max_sentences or is_clinical_safety_statement(sanitized)):
            yield sanitized


async def _close(chunks: AsyncIterator[str]) -> None:
    close = getattr(chunks, "aclose", None)
    if close is not None:
        await close()
