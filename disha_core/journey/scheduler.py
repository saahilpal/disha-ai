"""Intelligent Question Scheduler for Patient Journey.

Determines the single most useful next question based on current journey state,
missing information, clinical priorities, and cross-channel history.
Enforces strict deduplication and conversational naturalness.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import asyncpg

from disha_core.journey.question_bank import (
    QUESTION_CATALOG,
    JourneyQuestion,
)
from disha_core.journey.state_machine import record_question_asked

logger = logging.getLogger("disha_core.journey.scheduler")


@dataclass(frozen=True)
class ScheduledQuestion:
    question_id: str
    target_field: str
    stage: int
    priority: int
    text: str
    phrasings: dict[str, str]


def _relevance_score(question: JourneyQuestion, user_turn_text: str) -> int:
    """Prefer a missing detail that fits the current turn over stage order."""
    if not user_turn_text.strip():
        return 0
    turn_words = {
        word.casefold().strip(".,?!():;")
        for word in user_turn_text.replace("/", " ").replace("-", " ").split()
        if len(word.strip(".,?!():;")) > 2
    }
    question_words = {
        word.casefold().strip(".,?!():;")
        for word in f"{question.target_field} {question.phrasings.get('en', '')}".split()
        if len(word.strip(".,?!():;")) > 2
    }
    return len(turn_words & question_words)


async def select_next_question(
    patient_id: str,
    journey_state: dict[str, Any],
    user_turn_text: str = "",
    channel: str = "chat",
    is_emergency: bool = False,
    is_off_topic_query: bool = False,
    conn: asyncpg.Connection | None = None,
    preferred_lang: str = "hinglish",
    auto_record: bool = True,
) -> ScheduledQuestion | None:
    """Select the single best next question to advance the patient's journey.

    Rules:
    - 0 questions if is_emergency or patient is in distress.
    - 0 questions if user asked an off-topic educational query that should be answered cleanly without forcing a questionnaire.
    - Skip any question whose target field is ALREADY known or completed.
    - Skip any question already asked recently without user answering.
    - Sort candidates by clinical priority (1 highest to 6 lowest).
    """
    if is_emergency:
        logger.debug("Emergency active: suppressing onboarding questions.")
        return None

    if is_off_topic_query:
        logger.debug("Off-topic user inquiry: suppressing onboarding questions to answer naturally.")
        return None

    completed_fields = set(journey_state.get("completed_fields") or [])
    skipped_fields = set(journey_state.get("skipped_fields") or [])
    current_stage = journey_state.get("current_stage", 1)

    # 1. Fetch recent question history to prevent repeats
    asked_qids: set[str] = set()
    answered_qids: set[str] = set()
    answered_targets: set[str] = set()
    recent_asked_targets: list[str] = []
    if conn is not None:
        rows = await conn.fetch(
            """SELECT question_id, target_field, status FROM journey_question_history
               WHERE patient_id = $1
               ORDER BY asked_at DESC LIMIT 30""",
            patient_id,
        )
        for r in rows:
            qid = r["question_id"]
            tf = r["target_field"]
            st = r["status"]
            if st in ("asked", "skipped"):
                asked_qids.add(qid)
                if tf:
                    recent_asked_targets.append(tf)
            elif st == "answered":
                answered_qids.add(qid)
                if tf:
                    answered_targets.add(tf)

    # 2. Gather candidates
    candidates: list[JourneyQuestion] = []
    for q in QUESTION_CATALOG:
        target = q.target_field
        # Never ask if already known, completed, or answered in history
        if target in completed_fields or target in answered_targets or q.question_id in answered_qids:
            continue
        # Don't ask if skipped unless required safety field
        if target in skipped_fields and not q.required:
            continue
        # Never repeat if already asked recently or awaiting answer
        if q.question_id in asked_qids or target in recent_asked_targets[:5]:
            continue

        # Stages measure completeness only. A later field may surface when the
        # current turn makes it relevant; otherwise retain the current-stage fallback.
        if q.stage <= current_stage or _relevance_score(q, user_turn_text) > 0:
            candidates.append(q)

    if not candidates:
        # Check any remaining uncompleted required fields that have not been asked or answered
        for q in QUESTION_CATALOG:
            if (
                q.target_field not in completed_fields
                and q.target_field not in answered_targets
                and q.question_id not in asked_qids
                and q.question_id not in answered_qids
                and q.required
            ):
                candidates.append(q)

    if not candidates:
        logger.debug("No pending onboarding questions for patient %s", patient_id)
        return None

    # 3. Sort candidates: active current stage first, then by priority, then stage
    candidates.sort(
        key=lambda x: (
            -_relevance_score(x, user_turn_text),
            x.stage != current_stage,
            x.priority,
            x.stage,
        )
    )
    selected = candidates[0]

    # 4. Localize question text
    lang_key = "hi" if preferred_lang == "hi" else ("en" if preferred_lang == "en" else "hinglish")
    q_text = selected.phrasings.get(lang_key) or selected.phrasings.get("hinglish") or selected.phrasings["en"]

    # 5. Record asked question in history if connection provided and auto_record is True
    if conn is not None and auto_record:
        await record_question_asked(
            patient_id=patient_id,
            question_id=selected.question_id,
            channel=channel,
            question_text=q_text,
            conn=conn,
        )

    logger.info(
        "Scheduled next question for %s: %s (target=%s, stage=%d, priority=%d)",
        patient_id,
        selected.question_id,
        selected.target_field,
        selected.stage,
        selected.priority,
    )

    return ScheduledQuestion(
        question_id=selected.question_id,
        target_field=selected.target_field,
        stage=selected.stage,
        priority=selected.priority,
        text=q_text,
        phrasings=selected.phrasings,
    )
