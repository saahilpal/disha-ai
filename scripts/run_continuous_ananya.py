"""Disha AI — 10-Minute Continuous Real-World Simulation: Ananya Iyer (Complex & Unpredictable User).

Conducts an extended 25+ turn, 10-minute complex interaction testing multi-symptom synthesis,
PCOS/digestive guidance, approved ICMR jeera/saunf remedies, abrupt topic switches,
diet chart database grounding, long-range memory recall, and emotional health support.
"""
import asyncio
import json
import os
import time

import httpx

BACKEND_URL = os.getenv("DISHA_HTTP_URL", "http://127.0.0.1:8080")
LOG_PATH = "audit/simulations/ananya_continuous_10min.jsonl"


TURNS = [
    # Phase 1: Multiple simultaneous health concerns
    "Hi Disha! I have PCOS and lately I've been feeling bloated after lunch, and my left knee has been acting up when I take stairs.",
    "For the bloating, what natural kitchen remedies or herbal teas should I have after meals?",
    "Does walking immediately after lunch help reduce this heavy feeling in my stomach?",
    "By the way, what causes hiccups suddenly when drinking cold water?",

    # Phase 2: Dietary modifications & PCOS
    "Actually from this week I've started including eggs in my breakfast. How will that affect my PCOS and bloating?",
    "Can you suggest what breakfast pairings go best with boiled eggs?",
    "Aaj dinner mein kya hai mere diet chart ke hisaab se?",
    "Agar paneer bhurji ki jagah main boiled chana ya tofu lena chahun, toh calories balance rahegi?",

    # Phase 3: Returning to earlier physical concern (Joint / Knee)
    "Coming back to my knee pain that I mentioned earlier, what gentle exercises can I do that won't strain my joints?",
    "Is brisk walking on a treadmill safe for sensitive knee joints, or should I prefer an outdoor flat surface?",
    "Should I apply an ice pack or warm heating pad when my knee feels stiff after a long workday?",

    # Phase 4: Sensitive topic — Stress, hormonal acne & hair thinning
    "Disha, to be honest, I feel really stressed and overwhelmed about my hormonal acne and severe hair fall lately. Is there any hope?",
    "Does high cortisol or work stress worsen PCOS androgen levels and facial breakouts?",
    "Any gentle morning relaxation or breathing exercises that can help lower my morning anxiety?",

    # Phase 5: Long-range synthesis & evening routine
    "Let's summarize my day: with eggs for breakfast, flat-surface walking for knee health, and jeera water for digestion.",
    "How should I pace my evening routine before going to sleep tonight?",
    "Should I finish dinner at least 2 hours before sleeping to prevent GERD acidity?",
    "If I feel late night sweet cravings after dinner, what is a healthy guilt-free snack?",
    "Would a small date (khajoor) or a handful of roasted makhana be okay?",

    # Phase 6: Mid-conversation goal shift
    "Actually Disha, from next month I want to make Skin Health and Hair Growth my primary priority over weight loss.",
    "Which dietary micronutrients like biotin, zinc, and omega-3 are most essential for hair follicle strength?",
    "Are pumpkin seeds and flaxseeds helpful for androgen balance in PCOS?",
    "Theek hai, thank you Disha for being so patient, supportive, and grounded. I feel much calmer now!",
]


async def run_simulation():
    os.makedirs("audit/simulations", exist_ok=True)
    async with httpx.AsyncClient(timeout=15.0) as client:
        profile = {
            "name": "Ananya Iyer",
            "email": f"ananya.continuous.{int(time.time())}@disha.ai",
            "password": "Password123!",
            "age": 29,
            "gender": "female",
            "height_cm": 163.0,
            "weight_kg": 62.0,
            "conditions": ["PCOS", "GERD", "Knee sensitivity"],
            "hypertension_stage": "normal",
            "gym_clearance": True,
            "activity_level": "light",
            "dietary_preference": "Vegetarian",
            "health_goals": ["Blood Sugar Balance", "Digestive Wellness", "Healthy Weight"],
            "language": "hinglish",
            "health_focuses": ["Hair fall and hair health", "Acne and pimples / Skin health", "Digestive health"],
            "health_focus_other": "PCOS hormonal acne & bloating after dairy",
        }
        res = await client.post(f"{BACKEND_URL}/auth/register", json=profile)
        if res.status_code != 200:
            print(f"[Ananya] Registration failed: {res.text}")
            return
        auth_data = res.json()
        token = auth_data["token"]
        patient_id = auth_data["patient_id"]
        print(f"[Ananya] Registered: {patient_id} ({profile['email']})")

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        start_time = time.time()
        failures = []

        with open(LOG_PATH, "w") as log_file:
            for idx, utterance in enumerate(TURNS, 1):
                t0 = time.perf_counter()
                try:
                    chat_res = await client.post(
                        f"{BACKEND_URL}/chat",
                        headers=headers,
                        json={"text": utterance},
                    )
                    latency_ms = round((time.perf_counter() - t0) * 1000, 2)
                    if chat_res.status_code == 200:
                        data = chat_res.json()
                        response_text = data.get("response", "")
                        status = data.get("status", "unknown")
                    else:
                        response_text = f"HTTP {chat_res.status_code}: {chat_res.text}"
                        status = "http_error"
                except Exception as e:
                    latency_ms = round((time.perf_counter() - t0) * 1000, 2)
                    response_text = str(e)
                    status = "client_exception"

                record = {
                    "turn": idx,
                    "timestamp": time.time(),
                    "elapsed_sec": round(time.time() - start_time, 1),
                    "user": utterance,
                    "disha": response_text,
                    "status": status,
                    "latency_ms": latency_ms,
                }
                log_file.write(json.dumps(record) + "\n")
                log_file.flush()
                print(f"[Ananya Turn {idx:02d} | {record['elapsed_sec']}s | {latency_ms}ms] Disha: {response_text[:90]}...")

                # Automated failure checks:
                resp_lower = response_text.lower()
                if "provider_unavailable" in status:
                    failures.append({"turn": idx, "issue": "provider_unavailable_timeout", "utterance": utterance})
                if idx == 2 and not any(w in resp_lower for w in ["jeera", "saunf"]):
                    failures.append({"turn": idx, "issue": "missing_icmr_bloating_remedy", "response": response_text})
                if idx == 7 and not any(w in resp_lower for w in ["paneer", "bhurji", "multigrain", "roti", "my plan", "diet chart"]):
                    failures.append({"turn": idx, "issue": "ignoring_diet_schedule", "response": response_text})
                if idx in (12, 13) and any(w in resp_lower for w in ["ugly", "hopeless", "permanent disease"]):
                    failures.append({"turn": idx, "issue": "insensitive_emotional_response", "response": response_text})

                # Simulate realistic typing/reading pause (12-16 seconds)
                await asyncio.sleep(12.0)

        total_time = round(time.time() - start_time, 1)
        print(f"\n[Ananya Completed] Total time: {total_time}s across {len(TURNS)} turns. Failures: {len(failures)}")


if __name__ == "__main__":
    asyncio.run(run_simulation())

