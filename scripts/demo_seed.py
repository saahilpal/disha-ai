#!/usr/bin/env python3
"""Disha AI — Show-Readiness Synthetic Demo Patient Seeder.

Seeds three realistic synthetic patient profiles:
1. Cardiac Stage 2: Vikram Malhotra [DEMO - Cardiac Stage 2]
   - Stage 2 HTN, CAD post-stent, strict gym contraindication, low-sodium DASH diet.
2. Type-2 Diabetic: Meera Sen [DEMO - Type-2 Diabetes]
   - T2D, glycemic instability, post-meal walking habit, low GI diet.
3. General Wellness: Kabir Deshmukh [DEMO - General Wellness]
   - Sedentary desk worker, physician gym clearance, 10k steps goal, posture care.

Demo mode is clearly indicated in patient names, records, and access tokens.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
from typing import Any

import asyncpg

DEFAULT_PG_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://disha:disha_secure_pass_123@127.0.0.1:5432/disha",
)

DEMO_PATIENTS = [
    {
        "patient_id": "pt_test_cardiac",
        "email": "cardiac@disha.ai",
        "alt_email": "demo.cardiac@disha.internal",
        "name": "Vikram Malhotra [DEMO - Cardiac Stage 2]",
        "password": "demo123",
        "age": 58,
        "gender": "Male",
        "height_cm": 174.0,
        "weight_kg": 82.5,
        "dietary_preference": "Vegetarian",
        "health_goals": [
            "Blood Pressure Moderation (<130/80)",
            "Safe Post-Stent Cardiac Rehabilitation",
            "Consistent Daily Morning Walking",
        ],
        "language": "hinglish",
        "health_focuses": ["Hypertension Management", "Cardiac Rehabilitation"],
        "health_focus_other": "Post-PCI stent monitoring and sodium control",
        "health_conditions": [
            "Hypertension Stage 2",
            "Coronary Artery Disease",
            "Post-PCI Stent (2024)",
        ],
        "pep": {
            "hypertension_stage": "Stage 2",
            "gym_clearance": False,
            "allowed_modalities": [
                "brisk walking",
                "gentle stretching",
                "pranayama (anulom vilom)",
                "light chair yoga",
            ],
            "restricted_modalities": [
                "heavy weightlifting",
                "heavy deadlifts",
                "valsalva maneuver",
                "high intensity sprinting",
                "hiit",
                "crossfit",
                "heavy gym machines",
            ],
            "primary_focus": "Blood Pressure Moderation & Cardiac Rehabilitation",
            "secondary_focuses": ["Sodium Reduction", "Symptom Monitoring"],
            "user_reported_concerns": "Post-PCI stent in LAD (2024); occasional mild breathlessness on stairs; baseline BP 142/92",
            "habits": {
                "morning_walk_mins": 25,
                "bp_monitoring_frequency": "daily_morning",
                "salt_intake": "strictly_low_sodium",
                "medication_adherence": "prescribed_beta_blockers",
            },
        },
        "habits_current": [
            ("morning_walk_mins", "25", "25 minute brisk walk in park", 12, 0.95),
            ("blood_pressure_systolic", "142", "142 mmHg measured at home", 15, 0.98),
            ("salt_restriction", "low_sodium", "strictly low-sodium home cooked meals", 8, 0.90),
        ],
        "habits_episodes": [
            (
                "cardiac_symptom_monitoring",
                "Mild dyspnea upon climbing two flights of stairs, resolves in 2 mins, no chest tightness at rest",
                "active",
            )
        ],
        "temporal_facts": [
            ("cardiac_history", json.dumps({"condition": "Coronary Artery Disease", "stent_year": 2024, "stent_location": "LAD", "gym_clearance": False})),
            ("last_bp_reading", json.dumps({"systolic": 142, "diastolic": 90, "measured_at": "yesterday morning", "device": "Omron Upper Arm Cuff"})),
            ("prescribed_medication", json.dumps({"class": "Beta Blocker & Statin", "note": "Disha does not alter dosage; patient adherent"})),
        ],
        "diet": {
            "breakfast": "2 moong dal chillas with fresh mint chutney (no added salt), 1 cup low-fat curd (approx 280 kcal)",
            "lunch": "1 bowl yellow moong dal (low salt), 2 whole wheat phulkas, steamed lauki sabzi, fresh cucumber slices (approx 420 kcal)",
            "dinner": "150g fresh low-fat paneer with tori sabzi, 2 multigrain phulkas, light bottle gourd soup (approx 390 kcal)",
        },
        "tokens": [
            "pt_test_cardiac_bearer_token",
            "demo_token_cardiac_stage2",
        ],
    },
    {
        "patient_id": "pt_test_diabetic",
        "email": "diabetic@disha.ai",
        "alt_email": "demo.diabetic@disha.internal",
        "name": "Meera Sen [DEMO - Type-2 Diabetes]",
        "password": "demo123",
        "age": 49,
        "gender": "Female",
        "height_cm": 161.0,
        "weight_kg": 69.0,
        "dietary_preference": "Vegetarian",
        "health_goals": [
            "Post-Prandial Glycemic Stability (<140 mg/dL)",
            "HbA1c Reduction from 7.4% to <6.8%",
            "Controlled Post-Meal Walking Habit",
        ],
        "language": "hinglish",
        "health_focuses": ["Type-2 Diabetes Management", "Glycemic Diet Care"],
        "health_focus_other": "Fasting blood sugar 138 mg/dL and post-lunch lethargy",
        "health_conditions": [
            "Type-2 Diabetes Mellitus",
            "Mild Dyslipidemia",
            "Hypertension Stage 1",
        ],
        "pep": {
            "hypertension_stage": "Stage 1",
            "gym_clearance": False,
            "allowed_modalities": [
                "brisk walking",
                "post-meal walking (15 min)",
                "hatha yoga",
                "light cycling",
                "gentle stretching",
            ],
            "restricted_modalities": [
                "unsupervised fasting workouts",
                "heavy deadlifts",
                "high-impact jumping",
                "intense heat yoga",
            ],
            "primary_focus": "Glycemic Control & Post-Prandial Blood Sugar Stability",
            "secondary_focuses": ["Post-Meal Activity", "Low GI Diet"],
            "user_reported_concerns": "Post-lunch energy crashes; fasting glucose 138 mg/dL; HbA1c 7.4%; mild knee tenderness",
            "habits": {
                "post_meal_walk_mins": 15,
                "fasting_blood_sugar": 138,
                "hba1c": 7.4,
                "evening_tea_sugar": "stopped",
            },
        },
        "habits_current": [
            ("post_meal_walk_mins", "15", "15 minute brisk walk after lunch and dinner", 10, 0.92),
            ("fasting_glucose", "138", "138 mg/dL morning fingerstick", 14, 0.96),
            ("sugar_intake", "zero_sugar_tea", "stopped sugar in morning and evening chai", 18, 0.95),
        ],
        "habits_episodes": [
            (
                "glycemic_trend",
                "Occasional post-lunch tiredness when eating refined carbohydrates; improving with sprouted salads",
                "active",
            )
        ],
        "temporal_facts": [
            ("glycemic_metrics", json.dumps({"hba1c": 7.4, "fasting_glucose": 138, "diagnosed_year": 2021, "target_hba1c": 6.8})),
            ("tea_sugar_status", json.dumps({"status": "eliminated refined sugar from morning and 5pm chai since last month"})),
        ],
        "diet": {
            "breakfast": "Sprouted methi and moong dal chilla with green coriander chutney and unsweetened almond curd (approx 290 kcal)",
            "lunch": "1 cup sprouted mung salad with lemon, 1 bowl dal tadka (1 tsp cold-pressed oil), 2 multigrain barley-wheat rotis, steamed palak (approx 440 kcal)",
            "dinner": "150g fresh tofu/paneer bhurji with capsicum, 2 small jowar rotis, clear tomato-cucumber soup (approx 380 kcal)",
        },
        "tokens": [
            "pt_test_diabetic_bearer_token",
            "demo_token_diabetic_type2",
        ],
    },
    {
        "patient_id": "pt_test_01",
        "email": "demo@disha.ai",
        "alt_email": "demo.wellness@disha.internal",
        "name": "Kabir Deshmukh [DEMO - General Wellness]",
        "password": "demo123",
        "age": 32,
        "gender": "Male",
        "height_cm": 178.0,
        "weight_kg": 75.0,
        "dietary_preference": "Vegetarian",
        "health_goals": [
            "10,000 Daily Step Count Habit",
            "Desk Posture Improvement & Back Ergonomics",
            "Sustained Afternoon Work Energy",
        ],
        "language": "hinglish",
        "health_focuses": ["General Fitness", "Preventive Wellness"],
        "health_focus_other": "Sedentary software developer sitting 9+ hours daily",
        "health_conditions": [
            "Sedentary Desk Fatigue",
            "Postural Upper Back Tightness",
        ],
        "pep": {
            "hypertension_stage": "Normal",
            "gym_clearance": True,
            "allowed_modalities": [
                "brisk walking",
                "jogging",
                "swimming",
                "bodyweight calisthenics",
                "moderate gym strength training",
                "cycling",
            ],
            "restricted_modalities": [
                "extreme unguided powerlifting",
            ],
            "primary_focus": "Cardiovascular Stamina & Posture Correction",
            "secondary_focuses": ["Daily Step Count", "Consistent Sleep Schedule"],
            "user_reported_concerns": "Sedentary lifestyle, sitting 9 hours at desk; lower back stiffness after coding sprints",
            "habits": {
                "daily_steps_target": 10000,
                "current_steps_avg": 6800,
                "sleep_hours": 6.8,
                "hydration_liters": 2.5,
            },
        },
        "habits_current": [
            ("daily_steps", "6800", "6,800 steps measured on smartphone pedometer", 20, 0.94),
            ("sleep_duration_hours", "6.8", "6 hours 45 minutes sleep recorded", 14, 0.90),
            ("desk_movement_breaks", "3", "3 micro-breaks taken during 9 hour workday", 7, 0.85),
        ],
        "habits_episodes": [
            (
                "posture_observation",
                "Upper trapezoid tightness after prolonged screen time, relieved by thoracic doorway stretches",
                "active",
            )
        ],
        "temporal_facts": [
            ("work_routine", json.dumps({"profession": "Software Engineer", "work_mode": "Hybrid", "sitting_hours": 9, "ergonomics": "Laptop stand with external keyboard"})),
            ("step_goal", json.dumps({"target": 10000, "current_avg": 6800, "preferred_reminder_window": "16:00 - 18:00"})),
        ],
        "diet": {
            "breakfast": "Rolled oats porridge cooked in skim milk with chia seeds, crushed almonds, and 1 bowl sprouted moong (approx 340 kcal)",
            "lunch": "1 bowl mixed vegetable dal, 2 multigrain rotis, fresh cucumber-curd raita, seasonal french beans sabzi (approx 480 kcal)",
            "dinner": "150g grilled paneer/soya chunks with sauteed broccoli, bell peppers, and 1 whole wheat phulka (approx 420 kcal)",
        },
        "tokens": [
            "pt_test_01_valid_bearer_token",
            "demo_token_general_wellness",
        ],
    },
]

DAYS_OF_WEEK = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _hash_password(password: str) -> str:
    iterations = 310_000
    salt = b"\x1b\x9a\x84\xce\x7f\x12\x3a\x9d\x01\xef\xaa\xbc\x44\x55\x66\x77"
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def access_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def seed_demo_patients(db_url: str = DEFAULT_PG_URL) -> dict[str, Any]:
    """Seed all 3 synthetic demo patients and their clinical dependencies."""
    print(f"[+] Connecting to PostgreSQL at {db_url}...")
    conn = await asyncpg.connect(db_url)
    stats: dict[str, Any] = {
        "patients_seeded": 0,
        "peps_seeded": 0,
        "meals_seeded": 0,
        "habits_seeded": 0,
        "tokens_seeded": 0,
    }

    try:
        async with conn.transaction():
            for p in DEMO_PATIENTS:
                pid = p["patient_id"]
                email = p["email"]
                name = p["name"]
                pwd_hash = _hash_password(p["password"])

                # 1. Upsert patient profile
                await conn.execute(
                    """INSERT INTO patient_profiles (
                           patient_id, email, password_hash, name, age, gender,
                           height_cm, weight_kg, dietary_preference, health_goals,
                           language, health_focuses, health_focus_other, health_conditions,
                           created_at
                       ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, NOW())
                       ON CONFLICT (patient_id) DO UPDATE SET
                           email = EXCLUDED.email,
                           password_hash = EXCLUDED.password_hash,
                           name = EXCLUDED.name,
                           age = EXCLUDED.age,
                           gender = EXCLUDED.gender,
                           height_cm = EXCLUDED.height_cm,
                           weight_kg = EXCLUDED.weight_kg,
                           dietary_preference = EXCLUDED.dietary_preference,
                           health_goals = EXCLUDED.health_goals,
                           language = EXCLUDED.language,
                           health_focuses = EXCLUDED.health_focuses,
                           health_focus_other = EXCLUDED.health_focus_other,
                           health_conditions = EXCLUDED.health_conditions""",
                    pid,
                    email,
                    pwd_hash,
                    name,
                    p["age"],
                    p["gender"],
                    p["height_cm"],
                    p["weight_kg"],
                    p["dietary_preference"],
                    p["health_goals"],
                    p["language"],
                    p["health_focuses"],
                    p["health_focus_other"],
                    p["health_conditions"],
                )
                stats["patients_seeded"] += 1

                # 2. Upsert PEP
                pep = p["pep"]
                await conn.execute(
                    """INSERT INTO patient_pep (
                           patient_id, hypertension_stage, gym_clearance,
                           allowed_modalities, restricted_modalities,
                           primary_focus, secondary_focuses, user_reported_concerns,
                           language, dietary_preference, habits, is_dirty, updated_at
                       ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, FALSE, NOW())
                       ON CONFLICT (patient_id) DO UPDATE SET
                           hypertension_stage = EXCLUDED.hypertension_stage,
                           gym_clearance = EXCLUDED.gym_clearance,
                           allowed_modalities = EXCLUDED.allowed_modalities,
                           restricted_modalities = EXCLUDED.restricted_modalities,
                           primary_focus = EXCLUDED.primary_focus,
                           secondary_focuses = EXCLUDED.secondary_focuses,
                           user_reported_concerns = EXCLUDED.user_reported_concerns,
                           language = EXCLUDED.language,
                           dietary_preference = EXCLUDED.dietary_preference,
                           habits = EXCLUDED.habits,
                           is_dirty = FALSE,
                           updated_at = NOW()""",
                    pid,
                    pep["hypertension_stage"],
                    pep["gym_clearance"],
                    pep["allowed_modalities"],
                    pep["restricted_modalities"],
                    pep["primary_focus"],
                    pep["secondary_focuses"],
                    pep["user_reported_concerns"],
                    p["language"],
                    p["dietary_preference"],
                    json.dumps(pep["habits"]),
                )
                stats["peps_seeded"] += 1

                # 3. Seed 7-Day Diet Schedules (21 distinct meal rows)
                diet = p["diet"]
                for day in DAYS_OF_WEEK:
                    for meal_type in ["breakfast", "lunch", "dinner"]:
                        items = diet[meal_type]
                        await conn.execute(
                            """INSERT INTO patient_diet_schedules (
                                   patient_id, day_of_week, meal_type, prescribed_items, is_active, approval_status
                               ) VALUES ($1, $2, $3, $4, TRUE, 'approved')
                               ON CONFLICT (patient_id, day_of_week, meal_type) DO UPDATE SET
                                   prescribed_items = EXCLUDED.prescribed_items,
                                   is_active = TRUE,
                                   approval_status = 'approved'""",
                            pid,
                            day,
                            meal_type,
                            items,
                        )
                        stats["meals_seeded"] += 1

                # 4. Upsert current-state habits
                for slot_key, val_norm, val_raw, count, conf in p["habits_current"]:
                    await conn.execute(
                        """DELETE FROM habit_current_state WHERE patient_id = $1 AND slot_key = $2""",
                        pid,
                        slot_key,
                    )
                    await conn.execute(
                        """INSERT INTO habit_current_state (
                               patient_id, slot_key, value_norm, value_raw, raw_lang,
                               first_seen_at, last_confirmed_at, confirm_count, confidence,
                               source, evidence_ref, valid_from, version, created_at
                           ) VALUES ($1, $2, $3, $4, 'hinglish', NOW() - INTERVAL '14 days', NOW(), $5, $6, 'call', 'clinician_onboarding_review', NOW() - INTERVAL '14 days', 1, NOW())""",
                        pid,
                        slot_key,
                        val_norm,
                        val_raw,
                        count,
                        conf,
                    )
                    stats["habits_seeded"] += 1

                # 5. Upsert habit episodes
                for ep_type, desc, ep_status in p["habits_episodes"]:
                    await conn.execute(
                        """INSERT INTO habit_episodes (
                               patient_id, episode_type, description, status, created_at
                           ) VALUES ($1, $2, $3, $4, NOW() - INTERVAL '7 days')""",
                        pid,
                        ep_type,
                        desc,
                        ep_status,
                    )

                # 6. Upsert patient temporal facts and memory items for cross-session recall
                for f_key, f_val in p["temporal_facts"]:
                    await conn.execute(
                        """DELETE FROM patient_temporal_facts WHERE patient_id = $1 AND fact_key = $2""",
                        pid,
                        f_key,
                    )
                    await conn.execute(
                        """INSERT INTO patient_temporal_facts (
                               patient_id, category, fact_key, fact_value, epistemic_status, source, valid_from, created_at
                           ) VALUES ($1, 'medical', $2, $3, 'active', 'voice', NOW() - INTERVAL '7 days', NOW() - INTERVAL '7 days')""",
                        pid,
                        f_key,
                        f_val,
                    )
                    # Also insert into memory_items so context_builder picks it up via both paths
                    await conn.execute(
                        """DELETE FROM memory_items WHERE patient_id = $1 AND slot_key = $2""",
                        pid,
                        f_key,
                    )
                    await conn.execute(
                        """INSERT INTO memory_items (
                               patient_id, slot_key, slot_value, category, source_authority,
                               epistemic_status, confidence, raw_quote, language, session_id,
                               valid_from, created_at, updated_at
                           ) VALUES ($1, $2, $3::jsonb, 'medical', 'PEP_DOCTOR', 'active', 1.000, $4, 'hinglish', 'prior_clinical_session', NOW() - INTERVAL '7 days', NOW() - INTERVAL '7 days', NOW() - INTERVAL '7 days')""",
                        pid,
                        f_key,
                        f_val if f_val.startswith("{") else json.dumps({"value": f_val}),
                        f_val,
                    )

                # 7. Upsert bearer access tokens
                for raw_tok in p["tokens"]:
                    t_hash = access_token_hash(raw_tok)
                    await conn.execute(
                        """INSERT INTO patient_access_tokens (
                               token_hash, patient_id, created_at, expires_at
                           ) VALUES ($1, $2, NOW(), NOW() + INTERVAL '365 days')
                           ON CONFLICT (token_hash) DO UPDATE SET
                               patient_id = EXCLUDED.patient_id,
                               expires_at = NOW() + INTERVAL '365 days',
                               revoked_at = NULL""",
                        t_hash,
                        pid,
                    )
                    stats["tokens_seeded"] += 1

        print("[✓] All 3 synthetic demo profiles seeded successfully into PostgreSQL!")
        print(f"    - Patients: {stats['patients_seeded']}")
        print(f"    - PEPs:     {stats['peps_seeded']}")
        print(f"    - Meals:    {stats['meals_seeded']}")
        print(f"    - Habits:   {stats['habits_seeded']}")
        print(f"    - Tokens:   {stats['tokens_seeded']}")
        return stats
    finally:
        await conn.close()


def print_demo_sheet():
    """Print the interactive terminal overview of demo personas."""
    print("\n" + "=" * 76)
    print("  DISHA AI — SHOW-READINESS SYNTHETIC DEMO PERSONAS")
    print("=" * 76)
    for p in DEMO_PATIENTS:
        print(f"\n[DEMO PERSONA]: {p['name']}")
        print(f"  • ID:          {p['patient_id']}")
        print(f"  • Email:       {p['email']}")
        print(f"  • Password:    {p['password']}")
        print(f"  • Conditions:  {', '.join(p['health_conditions'])}")
        print(f"  • PEP Focus:   {p['pep']['primary_focus']}")
        print(f"  • Gym Clear:   {'YES (Cleared)' if p['pep']['gym_clearance'] else 'NO (Strictly Contraindicated)'}")
        print(f"  • Allowed:     {', '.join(p['pep']['allowed_modalities'][:3])}")
        print(f"  • Restricted:  {', '.join(p['pep']['restricted_modalities'][:3]) if p['pep']['restricted_modalities'] else 'None'}")
        print(f"  • Token:       {p['tokens'][0]}")
    print("\n" + "=" * 76)


def main() -> int:
    try:
        stats = asyncio.run(seed_demo_patients())
        print_demo_sheet()
        return 0
    except Exception as exc:
        print(f"[-] Error seeding demo patients: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
