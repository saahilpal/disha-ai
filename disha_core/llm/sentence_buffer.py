from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

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
    intent = getattr(context.get("intent", ""), "value", context.get("intent", ""))
    if context.get("diet_status") == "NOT_FOUND" and str(intent).upper() in {"MEAL_QUERY", "RECIPE"}:
        result = validator.validate_sentence(MEAL_NOT_FOUND_REPLACEMENT, context)
        yield validator.sanitize_for_tts(result.text)
        await _close(chunks)
        return

    buffer = SentenceBuffer()
    first_sentence = True
    emitted = 0
    async for chunk in chunks:
        for sentence in buffer.feed(chunk):
            result = (
                validator.validate_turn(sentence, context)
                if first_sentence else validator.validate_sentence(sentence, context)
            )
            first_sentence = False
            yield validator.sanitize_for_tts(result.text)
            emitted += 1
            if emitted == 3:
                await _close(chunks)
                return
    remainder = buffer.flush()
    if remainder:
        result = (
            validator.validate_turn(remainder, context)
            if first_sentence else validator.validate_sentence(remainder, context)
        )
        yield validator.sanitize_for_tts(result.text)


async def _close(chunks: AsyncIterator[str]) -> None:
    close = getattr(chunks, "aclose", None)
    if close is not None:
        await close()

