"""Patient Journey State Machine and Progression Engine.

Manages persistent multi-stage onboarding state, field completion tracking,
stage transitions, database synchronization, and cross-channel persistence.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg

from disha_core.journey.fields import (
    JOURNEY_FIELDS,
    FieldDestination,
    get_required_fields_by_stage,
)
from disha_core.journey.question_bank import (
    QUESTION_BY_FIELD,
    QUESTION_BY_ID,
)
from disha_core.pep.habits_engine import commit_habit_slot

logger = logging.getLogger("disha_core.journey.state_machine")


async def sync_known_fields_from_db(patient_id: str, conn: asyncpg.Connection) -> dict[str, Any]:
    """Scan existing database records across profile, PEP, habits, and temporal facts.

    Returns a dictionary of all currently known fields and their values.
    """
    known: dict[str, Any] = {}

    # 1. patient_profiles
    p_row = await conn.fetchrow(
        """SELECT name, age, gender, height_cm, weight_kg, language,
                  dietary_preference, health_goals, health_conditions
           FROM patient_profiles WHERE patient_id = $1""",
        patient_id,
    )
    if p_row:
        if p_row["name"]:
            known["name"] = p_row["name"]
        if p_row["age"]:
            known["age"] = p_row["age"]
        if p_row["gender"]:
            known["gender"] = p_row["gender"]
        if p_row["height_cm"]:
            known["height_cm"] = float(p_row["height_cm"])
        if p_row["weight_kg"]:
            known["weight_kg"] = float(p_row["weight_kg"])
        if p_row["language"]:
            known["language"] = p_row["language"]
        if p_row["dietary_preference"]:
            known["dietary_preference"] = p_row["dietary_preference"]
        if p_row["health_goals"]:
            known["primary_health_goal"] = p_row["health_goals"]
        if p_row["health_conditions"]:
            known["diagnosed_conditions"] = list(p_row["health_conditions"])

    # 2. patient_pep
    pep_row = await conn.fetchrow(
        """SELECT hypertension_stage, gym_clearance, allowed_modalities, restricted_modalities,
                  primary_focus, secondary_focuses, user_reported_concerns, diagnosed_conditions,
                  dietary_preference, language, habits
           FROM patient_pep WHERE patient_id = $1""",
        patient_id,
    )
    if pep_row:
        if pep_row["diagnosed_conditions"] and not known.get("diagnosed_conditions"):
            known["diagnosed_conditions"] = list(pep_row["diagnosed_conditions"])
        if pep_row["primary_focus"] and not known.get("primary_health_goal"):
            known["primary_health_goal"] = pep_row["primary_focus"]
        if pep_row["secondary_focuses"]:
            known["secondary_health_goals"] = list(pep_row["secondary_focuses"])
        if pep_row["dietary_preference"] and not known.get("dietary_preference"):
            known["dietary_preference"] = pep_row["dietary_preference"]
        if pep_row["gym_clearance"] is not None:
            known["exercise_clearance"] = pep_row["gym_clearance"]

    # 3. habit_current_state
    habit_rows = await conn.fetch(
        """SELECT slot_key, value_norm FROM habit_current_state
           WHERE patient_id = $1 AND valid_to IS NULL""",
        patient_id,
    )
    for hr in habit_rows:
        sk = hr["slot_key"]
        val = hr["value_norm"]
        if sk == "wake_time":
            known["wake_time"] = val
        elif sk == "sleep_time":
            known["sleep_time"] = val
        elif sk == "work_schedule":
            known["work_schedule"] = val
        elif sk == "water_intake_target":
            try:
                known["water_intake_target"] = float(val)
            except Exception:
                known["water_intake_target"] = val
        elif sk == "daily_steps_target":
            try:
                known["daily_movement_level"] = int(val)
            except Exception:
                known["daily_movement_level"] = val
        elif sk == "dietary_restrictions":
            try:
                known["allergies_intolerances"] = json.loads(val) if val.startswith("[") else [val]
            except Exception:
                known["allergies_intolerances"] = [val]
        elif sk == "tea_coffee_frequency":
            try:
                known["tea_coffee_frequency"] = json.loads(val) if val.startswith("{") else val
            except Exception:
                known["tea_coffee_frequency"] = val

    # 4. patient_temporal_facts
    fact_rows = await conn.fetch(
        """SELECT fact_key, fact_value FROM patient_temporal_facts
           WHERE patient_id = $1 AND epistemic_status = 'active'""",
        patient_id,
    )
    for fr in fact_rows:
        fk = fr["fact_key"]
        fv = fr["fact_value"]
        if "dislike" in fk or "disliked" in fk:
            known["disliked_foods"] = [fv]
        elif "medication" in fk:
            known["medications"] = [fv]
        elif "injury" in fk or "limitation" in fk:
            known["injuries_or_limitations"] = [fv]
        elif "cuisine" in fk:
            known["cultural_regional_preferences"] = fv

    # 5. Check answered questions in journey_question_history
    try:
        answered_q_rows = await conn.fetch(
            """SELECT DISTINCT target_field, extracted_value FROM journey_question_history
               WHERE patient_id = $1 AND status = 'answered'""",
            patient_id,
        )
        for aq in answered_q_rows:
            tf = aq["target_field"]
            if tf and tf not in known:
                ev = aq["extracted_value"]
                if ev is not None:
                    if isinstance(ev, dict) and "value" in ev:
                        known[tf] = ev["value"]
                    elif isinstance(ev, list) and len(ev) == 0:
                        known[tf] = ["none"]
                    else:
                        known[tf] = ev
                else:
                    known[tf] = ["none"] if tf == "diagnosed_conditions" else True
    except Exception as exc:
        logger.debug("Could not sync answered questions from history: %s", exc)

    return known


async def load_or_create_journey(
    patient_id: str,
    conn: asyncpg.Connection,
    channel: str = "chat",
) -> dict[str, Any]:
    """Load the current journey state from PostgreSQL, syncing with known DB fields.

    Calculates stage coverage, missing fields, and stage transitions.
    """
    try:
        known_fields = await sync_known_fields_from_db(patient_id, conn)
    except Exception as exc:
        logger.warning("Database unavailable in sync_known_fields_from_db: %s", exc)
        return {
            "patient_id": patient_id,
            "current_stage": 1,
            "stage_status": {},
            "overall_status": "in_progress",
            "completed_fields": [],
            "skipped_fields": [],
            "known_fields": {},
            "last_completed_stage": None,
            "channel": channel,
        }

    completed_keys = set(known_fields.keys())

    # Calculate stage coverage
    req_by_stage = get_required_fields_by_stage()
    stage_status: dict[str, Any] = {}
    current_stage = 1
    last_completed = 0

    for s in range(1, 6):
        s_key = f"stage_{s}"
        s_reqs = set(req_by_stage.get(s, []))
        s_completed = s_reqs.intersection(completed_keys)
        s_missing = s_reqs - completed_keys

        is_done = len(s_missing) == 0 and len(s_reqs) > 0
        stage_status[s_key] = {
            "stage_number": s,
            "status": "completed" if is_done else "in_progress",
            "required_fields": list(s_reqs),
            "completed_fields": list(s_completed),
            "missing_fields": list(s_missing),
        }
        if is_done and last_completed == s - 1:
            last_completed = s

    # Current stage is lowest non-completed stage
    for s in range(1, 5):
        if stage_status[f"stage_{s}"]["status"] != "completed":
            current_stage = s
            break
    else:
        current_stage = 5

    # Overall status
    if last_completed >= 4:
        overall_status = (
            "completed"
            if current_stage == 5 and len(stage_status["stage_5"]["missing_fields"]) == 0
            else "post_onboarding"
        )
    else:
        overall_status = "in_progress"

    now = datetime.now(timezone.utc)

    skipped_fields = []
    try:
        # Upsert into patient_journey_state
        await conn.execute(
            """
            INSERT INTO patient_journey_state (
                patient_id, current_stage, stage_status, overall_status,
                completed_fields, missing_fields, last_interaction_ts,
                last_interaction_channel, last_completed_stage, updated_at
            )
            VALUES ($1, $2, $3::jsonb, $4, $5, $6, $7, $8, $9, $7)
            ON CONFLICT (patient_id) DO UPDATE SET
                current_stage = EXCLUDED.current_stage,
                stage_status = EXCLUDED.stage_status,
                overall_status = EXCLUDED.overall_status,
                completed_fields = EXCLUDED.completed_fields,
                missing_fields = EXCLUDED.missing_fields,
                last_interaction_ts = EXCLUDED.last_interaction_ts,
                last_interaction_channel = EXCLUDED.last_interaction_channel,
                last_completed_stage = EXCLUDED.last_completed_stage,
                updated_at = EXCLUDED.updated_at
            """,
            patient_id,
            current_stage,
            json.dumps(stage_status),
            overall_status,
            list(completed_keys),
            list(set(JOURNEY_FIELDS.keys()) - completed_keys),
            now,
            channel,
            last_completed,
        )

        skipped_row = await conn.fetchval(
            "SELECT skipped_fields FROM patient_journey_state WHERE patient_id = $1",
            patient_id,
        )
        skipped_fields = list(skipped_row or [])
    except Exception as exc:
        logger.warning("Database error during journey upsert: %s", exc)

    # Calculate granular field states & pending question
    pending_question: dict[str, Any] | None = None
    recent_question: dict[str, Any] | None = None
    field_history_status: dict[str, str] = {}
    try:
        q_rows = await conn.fetch(
            """SELECT id, question_id, target_field, status, question_text, asked_at
               FROM journey_question_history
               WHERE patient_id = $1
               ORDER BY asked_at DESC LIMIT 25""",
            patient_id,
        )
        if q_rows:
            recent_question = {
                "question_id": q_rows[0]["question_id"],
                "target_field": q_rows[0]["target_field"],
                "question_text": q_rows[0]["question_text"],
                "status": q_rows[0]["status"],
            }
            for qr in q_rows:
                tf = qr["target_field"]
                if tf and tf not in field_history_status:
                    field_history_status[tf] = qr["status"]
                if qr["status"] == "asked" and pending_question is None:
                    pending_question = {
                        "question_id": qr["question_id"],
                        "target_field": qr["target_field"],
                        "question_text": qr["question_text"],
                    }
    except Exception as exc:
        logger.debug("Could not fetch question history for journey state: %s", exc)

    field_states: dict[str, str] = {}
    for f_name in JOURNEY_FIELDS:
        if f_name in known_fields:
            val = known_fields[f_name]
            if val in (["none"], "none", []):
                field_states[f_name] = "answered_negatively"
            else:
                field_states[f_name] = "answered_positively"
        elif field_history_status.get(f_name) == "asked":
            field_states[f_name] = "asked_unanswered"
        elif field_history_status.get(f_name) == "needs_clarification":
            field_states[f_name] = "needs_clarification"
        else:
            field_states[f_name] = "not_asked"

    return {
        "patient_id": patient_id,
        "current_stage": current_stage,
        "stage_status": stage_status,
        "overall_status": overall_status,
        "completed_fields": list(completed_keys),
        "skipped_fields": skipped_fields,
        "known_fields": known_fields,
        "field_states": field_states,
        "pending_question": pending_question,
        "recent_question": recent_question,
        "last_completed_stage": last_completed,
        "channel": channel,
    }


async def record_question_asked(
    patient_id: str,
    question_id: str,
    channel: str,
    question_text: str,
    conn: asyncpg.Connection,
) -> int:
    """Record that a question was asked to the patient in chat or voice."""
    q_def = QUESTION_BY_ID.get(question_id)
    stage = q_def.stage if q_def else 1
    target_field = q_def.target_field if q_def else "unknown"

    now = datetime.now(timezone.utc)

    # Check previous attempts
    prev_attempts = (
        await conn.fetchval(
            """SELECT attempts FROM journey_question_history
           WHERE patient_id = $1 AND question_id = $2
           ORDER BY created_at DESC LIMIT 1""",
            patient_id,
            question_id,
        )
        or 0
    )

    row_id = await conn.fetchval(
        """
        INSERT INTO journey_question_history (
            patient_id, question_id, stage, target_field, channel,
            status, question_text, asked_at, attempts
        )
        VALUES ($1, $2, $3, $4, $5, 'asked', $6, $7, $8)
        RETURNING id
        """,
        patient_id,
        question_id,
        stage,
        target_field,
        channel,
        question_text,
        now,
        prev_attempts + 1,
    )

    await conn.execute(
        """UPDATE patient_journey_state
           SET last_interaction_ts = $2, last_interaction_channel = $3
           WHERE patient_id = $1""",
        patient_id,
        now,
        channel,
    )

    return row_id


async def record_field_answer(
    patient_id: str,
    field_id: str,
    raw_value: Any,
    raw_text: str,
    channel: str,
    conn: asyncpg.Connection,
    lang: str = "hinglish",
) -> dict[str, Any]:
    """Store extracted patient disclosure into its target PEP/profile destination and update journey.

    Supports capturing future stage fields immediately.
    """
    field_def = JOURNEY_FIELDS.get(field_id)
    if not field_def:
        logger.warning("Unrecognized journey field '%s'", field_id)
        return {"status": "error", "message": f"Unknown field {field_id}"}

    # Normalize value
    val = raw_value
    if field_def.validator:
        try:
            val = field_def.validator(raw_value, lang)
        except Exception as e:
            logger.debug("Validation error on %s: %s; using raw", field_id, e)
            val = raw_value

    now = datetime.now(timezone.utc)

    # 1. Dispatch to storage destination
    dest = field_def.destination
    if dest == FieldDestination.PROFILE:
        email = f"{patient_id}@disha.internal"
        exists = await conn.fetchval("SELECT 1 FROM patient_profiles WHERE patient_id = $1", patient_id)
        if exists:
            await conn.execute(
                f"UPDATE patient_profiles SET {field_def.dest_column} = $2 WHERE patient_id = $1",
                patient_id,
                val,
            )
        else:
            default_name = (
                val
                if field_def.dest_column == "name"
                else ("Aarav Sharma" if patient_id == "pt_test_01" else patient_id)
            )
            await conn.execute(
                f"""INSERT INTO patient_profiles (patient_id, {field_def.dest_column}, name, email, password_hash, created_at)
                    VALUES ($1, $2, $3, $4, 'pass_hash', $5)
                    ON CONFLICT (patient_id) DO UPDATE SET
                    {field_def.dest_column} = EXCLUDED.{field_def.dest_column}""",
                patient_id,
                val,
                default_name,
                email,
                now,
            )
    elif dest == FieldDestination.PEP_CORE:
        if field_def.dest_column == "diagnosed_conditions":
            cond_list = val if isinstance(val, list) else [str(val)]
            await conn.execute(
                """INSERT INTO patient_pep (patient_id, diagnosed_conditions, updated_at)
                   VALUES ($1, $2, $3)
                   ON CONFLICT (patient_id) DO UPDATE SET
                   diagnosed_conditions = EXCLUDED.diagnosed_conditions, updated_at = $3""",
                patient_id,
                cond_list,
                now,
            )
            await conn.execute(
                """UPDATE patient_profiles SET health_conditions = $2 WHERE patient_id = $1""",
                patient_id,
                cond_list,
            )
        elif field_def.dest_column == "primary_focus":
            await conn.execute(
                """INSERT INTO patient_pep (patient_id, primary_focus, updated_at)
                   VALUES ($1, $2, $3)
                   ON CONFLICT (patient_id) DO UPDATE SET
                   primary_focus = EXCLUDED.primary_focus, updated_at = $3""",
                patient_id,
                str(val),
                now,
            )
        elif field_def.dest_column == "dietary_preference":
            await conn.execute(
                """INSERT INTO patient_pep (patient_id, dietary_preference, updated_at)
                   VALUES ($1, $2, $3)
                   ON CONFLICT (patient_id) DO UPDATE SET
                   dietary_preference = EXCLUDED.dietary_preference, updated_at = $3""",
                patient_id,
                str(val),
                now,
            )
            # Also keep patient_profiles synchronized with updated dietary preference
            await conn.execute(
                """UPDATE patient_profiles SET dietary_preference = $2 WHERE patient_id = $1""",
                patient_id,
                str(val),
            )
    elif dest == FieldDestination.HABIT_SLOT:
        slot_key = field_def.dest_column
        await commit_habit_slot(
            patient_id=patient_id,
            slot_key=slot_key,
            raw_value=val,
            raw_text=raw_text,
            lang=lang,
            source=channel,
            evidence_ref=f"journey:{channel}:{field_id}",
            conn=conn,
        )
    elif dest == FieldDestination.HABIT_EPISODE:
        # Transient symptom
        await conn.execute(
            """INSERT INTO habit_episodes 
               (patient_id, episode_type, description, status, due_at, expires_at, evidence_ref)
               VALUES ($1, 'symptom_transient', $2, 'active', $3, $4, $5)""",
            patient_id,
            str(raw_text or val),
            now,
            now + timedelta(hours=48),
            f"journey:{channel}:{field_id}",
        )
    elif dest == FieldDestination.TEMPORAL_FACT:
        val_str = json.dumps(val) if isinstance(val, (list, dict)) else str(val)
        await conn.execute(
            """INSERT INTO patient_temporal_facts (patient_id, fact_key, category, fact_value, source, created_at)
               VALUES ($1, $2, $3, $4, $5, $6)""",
            patient_id,
            field_def.dest_column,
            f"stage_{field_def.stage}",
            val_str,
            channel,
            now,
        )

    # 2. Mark matching pending questions as answered
    val_json = json.dumps(val) if isinstance(val, (dict, list)) else json.dumps({"value": val})
    q_def = QUESTION_BY_FIELD.get(field_id)
    qid = q_def.question_id if q_def else ""
    await conn.execute(
        """UPDATE journey_question_history
           SET status = 'answered', answered_at = $3, response_text = $4, extracted_value = $5::jsonb
           WHERE patient_id = $1 AND (question_id = $2 OR target_field = $6) AND status = 'asked'""",
        patient_id,
        qid,
        now,
        raw_text,
        val_json,
        field_id,
    )

    # 3. Reload journey state
    updated_journey = await load_or_create_journey(patient_id, conn, channel=channel)
    return {
        "status": "success",
        "field_id": field_id,
        "value": val,
        "stage": field_def.stage,
        "journey": updated_journey,
    }


async def record_question_skipped(
    patient_id: str,
    question_id: str,
    reason: str,
    channel: str,
    conn: asyncpg.Connection,
) -> None:
    """Mark a question as skipped without blocking the journey."""
    q_def = QUESTION_BY_ID.get(question_id)
    target_field = q_def.target_field if q_def else "unknown"

    now = datetime.now(timezone.utc)
    await conn.execute(
        """UPDATE journey_question_history
           SET status = 'skipped', skip_reason = $3
           WHERE patient_id = $1 AND question_id = $2 AND status = 'asked'""",
        patient_id,
        question_id,
        reason,
    )

    await conn.execute(
        """UPDATE patient_journey_state
           SET skipped_fields = array_append(skipped_fields, $2),
               last_interaction_ts = $3, last_interaction_channel = $4
           WHERE patient_id = $1 AND NOT ($2 = ANY(skipped_fields))""",
        patient_id,
        target_field,
        now,
        channel,
    )


async def record_question_deferred(
    patient_id: str,
    question_id: str,
    reason: str,
    channel: str,
    conn: asyncpg.Connection,
) -> dict[str, Any]:
    """Mark a question as deferred (postponed for later session) without permanently skipping."""
    now = datetime.now(timezone.utc)
    await conn.execute(
        """UPDATE journey_question_history
           SET skip_reason = $3, asked_at = $4
           WHERE patient_id = $1 AND question_id = $2 AND status = 'asked'""",
        patient_id,
        question_id,
        f"deferred: {reason}",
        now,
    )
    await conn.execute(
        """UPDATE patient_journey_state
           SET last_interaction_ts = $2, last_interaction_channel = $3
           WHERE patient_id = $1""",
        patient_id,
        now,
        channel,
    )
    return await load_or_create_journey(patient_id, conn, channel=channel)


async def record_slot_undo(
    patient_id: str,
    field_id: str,
    channel: str,
    conn: asyncpg.Connection,
) -> dict[str, Any]:
    """Revert the latest answer for a journey field and restore prior state."""
    field_def = JOURNEY_FIELDS.get(field_id)
    now = datetime.now(timezone.utc)

    # 1. Update history record to superseded
    q_def = QUESTION_BY_FIELD.get(field_id)
    if q_def:
        await conn.execute(
            """UPDATE journey_question_history
               SET status = 'superseded'
               WHERE patient_id = $1 AND question_id = $2 AND status = 'answered'""",
            patient_id,
            q_def.question_id,
        )

    # 2. Revert stored value depending on destination
    if field_def:
        dest = field_def.destination
        if dest == FieldDestination.PROFILE:
            await conn.execute(
                f"UPDATE patient_profiles SET {field_def.dest_column} = NULL WHERE patient_id = $1",
                patient_id,
            )
        elif dest == FieldDestination.PEP_CORE:
            if field_def.dest_column == "dietary_preference":
                await conn.execute(
                    "UPDATE patient_pep SET dietary_preference = NULL, updated_at = $2 WHERE patient_id = $1",
                    patient_id,
                    now,
                )
            elif field_def.dest_column == "primary_focus":
                await conn.execute(
                    "UPDATE patient_pep SET primary_focus = NULL, updated_at = $2 WHERE patient_id = $1",
                    patient_id,
                    now,
                )
        elif dest == FieldDestination.HABIT_SLOT:
            slot_key = field_def.dest_column
            active_row = await conn.fetchrow(
                "SELECT id, supersedes FROM habit_current_state WHERE patient_id = $1 AND slot_key = $2 AND valid_to IS NULL",
                patient_id,
                slot_key,
            )
            if active_row:
                await conn.execute(
                    "UPDATE habit_current_state SET valid_to = $2 WHERE id = $1",
                    active_row["id"],
                    now,
                )
                if active_row["supersedes"]:
                    await conn.execute(
                        "UPDATE habit_current_state SET valid_to = NULL WHERE id = $1",
                        active_row["supersedes"],
                    )
                await conn.execute("UPDATE patient_pep SET is_dirty = TRUE WHERE patient_id = $1", patient_id)
        elif dest == FieldDestination.TEMPORAL_FACT:
            await conn.execute(
                "DELETE FROM patient_temporal_facts WHERE patient_id = $1 AND fact_key = $2",
                patient_id,
                field_def.dest_column,
            )

    # 3. Reload journey state with recomputed completed/missing fields
    updated_journey = await load_or_create_journey(patient_id, conn, channel=channel)
    return {
        "status": "success",
        "action": "undo",
        "field_id": field_id,
        "journey": updated_journey,
    }
