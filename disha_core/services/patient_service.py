"""Patient profile and diet/PEP aggregation service for Disha AI Core."""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException


def _pep_val(row: Any, key: str, default: Any = None) -> Any:
    if not row:
        return default
    try:
        val = row[key]
        return val if val is not None else default
    except (KeyError, IndexError, TypeError):
        return default


async def fetch_patient_profile(pool: Any, patient_id: str, day: str) -> dict[str, Any]:
    """Fetch patient clinical profile, PEP bounds, and prescribed day diet."""
    if pool is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    async with pool.acquire() as conn:
        profile_row = await conn.fetchrow(
            """SELECT name, age, gender, height_cm, weight_kg, dietary_preference, health_goals,
                      language, health_focuses, health_focus_other, health_conditions
               FROM patient_profiles WHERE patient_id = $1""",
            patient_id,
        )
        pep_row = await conn.fetchrow(
            """SELECT hypertension_stage, gym_clearance, allowed_modalities, restricted_modalities,
                      primary_focus, secondary_focuses, user_reported_concerns, diagnosed_conditions
               FROM patient_pep WHERE patient_id = $1""",
            patient_id,
        )
        diet_rows = await conn.fetch(
            """SELECT meal_type, prescribed_items 
               FROM patient_diet_schedules
               WHERE patient_id = $1 AND day_of_week = $2
                 AND is_active = TRUE AND approval_status = 'approved'""",
            patient_id,
            day,
        )
        diet_map = {r["meal_type"]: r["prescribed_items"] for r in diet_rows}

        journey_row = await conn.fetchrow(
            """SELECT current_stage, stage_status, overall_status, last_completed_stage
               FROM patient_journey_state WHERE patient_id = $1""",
            patient_id,
        )

    name = (
        profile_row["name"]
        if profile_row
        else patient_id
    )

    return {
        "patient_id": patient_id,
        "patient_name": name,
        "day": day,
        "profile": dict(profile_row) if profile_row else None,
        "pep": {
            "hypertension_stage": _pep_val(pep_row, "hypertension_stage", "unknown"),
            "gym_clearance": _pep_val(pep_row, "gym_clearance"),
            "allowed_modalities": list(_pep_val(pep_row, "allowed_modalities", [])),
            "restricted_modalities": list(_pep_val(pep_row, "restricted_modalities", [])),
            "primary_focus": _pep_val(pep_row, "primary_focus", ""),
            "secondary_focuses": list(_pep_val(pep_row, "secondary_focuses", [])),
            "user_reported_concerns": _pep_val(pep_row, "user_reported_concerns", ""),
            "diagnosed_conditions": list(_pep_val(pep_row, "diagnosed_conditions", [])),
        },
        "today_diet": diet_map,
        "journey": dict(journey_row) if journey_row else {
            "current_stage": 1,
            "overall_status": "in_progress",
            "last_completed_stage": 0,
        },
    }


async def update_patient_profile(pool: Any, patient_id: str, updates: dict[str, Any], day: str) -> dict[str, Any]:
    """Update patient personal and health metrics, returning the refreshed profile."""
    if pool is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    async with pool.acquire() as conn:
        existing = await conn.fetchrow("SELECT 1 FROM patient_profiles WHERE patient_id = $1", patient_id)
        if existing:
            fields = []
            values = []
            idx = 1
            for key in (
                "name", "age", "gender", "height_cm", "weight_kg", "dietary_preference",
                "health_goals", "language", "health_focuses", "health_focus_other", "health_conditions"
            ):
                if key in updates and updates[key] is not None:
                    fields.append(f"{key} = ${idx}")
                    values.append(updates[key])
                    idx += 1
            if fields:
                values.append(patient_id)
                query = f"UPDATE patient_profiles SET {', '.join(fields)} WHERE patient_id = ${idx}"
                await conn.execute(query, *values)
        else:
            name = updates.get("name") or patient_id
            email = updates.get("email") or f"{patient_id}@disha.internal"
            password_hash = "placeholder_preseeded_token_auth"
            await conn.execute(
                """INSERT INTO patient_profiles (
                       patient_id, email, password_hash, name, age, gender, height_cm, weight_kg,
                       dietary_preference, health_goals, language, health_focuses, health_focus_other, health_conditions
                   )
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                   ON CONFLICT (patient_id) DO UPDATE SET
                     name = COALESCE(EXCLUDED.name, patient_profiles.name),
                     age = COALESCE(EXCLUDED.age, patient_profiles.age),
                     gender = COALESCE(EXCLUDED.gender, patient_profiles.gender),
                     height_cm = COALESCE(EXCLUDED.height_cm, patient_profiles.height_cm),
                     weight_kg = COALESCE(EXCLUDED.weight_kg, patient_profiles.weight_kg),
                     dietary_preference = COALESCE(EXCLUDED.dietary_preference, patient_profiles.dietary_preference),
                     health_goals = COALESCE(EXCLUDED.health_goals, patient_profiles.health_goals),
                     language = COALESCE(EXCLUDED.language, patient_profiles.language),
                     health_focuses = COALESCE(EXCLUDED.health_focuses, patient_profiles.health_focuses),
                     health_focus_other = COALESCE(EXCLUDED.health_focus_other, patient_profiles.health_focus_other),
                     health_conditions = COALESCE(EXCLUDED.health_conditions, patient_profiles.health_conditions)""",
                patient_id,
                email,
                password_hash,
                name,
                updates.get("age"),
                updates.get("gender"),
                updates.get("height_cm"),
                updates.get("weight_kg"),
                updates.get("dietary_preference"),
                updates.get("health_goals"),
                updates.get("language", "hinglish"),
                updates.get("health_focuses", []),
                updates.get("health_focus_other", ""),
                updates.get("health_conditions", []),
            )

        # Update PEP table
        pep_fields = []
        pep_values = []
        p_idx = 1

        # Check for focus priority updates
        primary_focus = updates.get("primary_focus")
        health_focuses = updates.get("health_focuses")
        if primary_focus is not None:
            pep_fields.append(f"primary_focus = ${p_idx}")
            pep_values.append(primary_focus)
            p_idx += 1
        elif health_focuses:
            pep_fields.append(f"primary_focus = ${p_idx}")
            pep_values.append(health_focuses[0])
            p_idx += 1

        if "secondary_focuses" in updates and updates["secondary_focuses"] is not None:
            pep_fields.append(f"secondary_focuses = ${p_idx}")
            pep_values.append(updates["secondary_focuses"])
            p_idx += 1
        elif health_focuses and len(health_focuses) > 1:
            pep_fields.append(f"secondary_focuses = ${p_idx}")
            pep_values.append(health_focuses[1:])
            p_idx += 1

        user_concerns = updates.get("user_reported_concerns") or updates.get("health_focus_other")
        if user_concerns is not None:
            pep_fields.append(f"user_reported_concerns = ${p_idx}")
            pep_values.append(user_concerns)
            p_idx += 1

        conditions = updates.get("health_conditions") or updates.get("diagnosed_conditions")
        if conditions is not None:
            pep_fields.append(f"diagnosed_conditions = ${p_idx}")
            pep_values.append(list(conditions))
            p_idx += 1

        if "hypertension_stage" in updates and updates["hypertension_stage"] is not None:
            pep_fields.append(f"hypertension_stage = ${p_idx}")
            pep_values.append(updates["hypertension_stage"])
            p_idx += 1
        elif conditions:
            cond_str = " ".join(str(c).casefold() for c in conditions)
            if "stage 2" in cond_str:
                stage = "stage 2"
            elif "hypertension" in cond_str or "high bp" in cond_str or "stage 1" in cond_str:
                stage = "stage 1"
            else:
                stage = "normal"
            pep_fields.append(f"hypertension_stage = ${p_idx}")
            pep_values.append(stage)
            p_idx += 1

        if "language" in updates and updates["language"] is not None:
            pep_fields.append(f"language = ${p_idx}")
            pep_values.append(str(updates["language"]).strip().lower())
            p_idx += 1

        if pep_fields:
            pep_fields.append("updated_at = NOW()")
            pep_values.append(patient_id)
            # Ensure row exists in patient_pep
            await conn.execute(
                """INSERT INTO patient_pep (patient_id, updated_at) VALUES ($1, NOW())
                   ON CONFLICT (patient_id) DO NOTHING""",
                patient_id,
            )
            update_sql = f"UPDATE patient_pep SET {', '.join(pep_fields)} WHERE patient_id = ${p_idx}"
            await conn.execute(update_sql, *pep_values)

        try:
            from disha_core.journey import sync_known_fields_from_db
            await sync_known_fields_from_db(patient_id, conn)
        except Exception:
            pass

    return await fetch_patient_profile(pool, patient_id, day)
