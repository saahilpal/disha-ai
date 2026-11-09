"""Disha AI — 10-Minute Continuous Real-World Simulation: Aarav Sharma (Realistic User).

Conducts an extended 25+ turn, 10-minute real-world conversation with Disha AI backend.
Simulates natural pacing, progressive disclosures, unexpected topic shifts, memory recalls,
pricing inquiries, and nutritional moderation queries.
"""
import asyncio
import json
import os
import time

import httpx

BACKEND_URL = os.getenv("DISHA_HTTP_URL", "http://127.0.0.1:8080")
LOG_PATH = "audit/simulations/aarav_continuous_10min.jsonl"


TURNS = [
    # Phase 1: Vague fatigue & office context
    "Hi Disha, I've been feeling a bit weird since this morning.",
    "Haan thoda fatigue lag raha hai, aur aaj office mein 5 cups chai pi li hai maine.",
    "Mujhe kya karna chahiye abhi fresh feel karne ke liye?",
    "Thoda paani pi liya maine, but headache jaisa bhi lag raha hai halka sa.",
    "Kya screens zyada dekhne se bhi fatigue badh sakti hai?",

    # Phase 2: Weekend plans & sudden topic shift
    "Waise weekend pe main doston ke saath cricket khelne ka soch raha tha, kya khel sakta hoon?",
    "Kya woh acidity aur 5 cup chai wala issue cricket match ko affect karega?",
    "Cricket ke dauran hydration ke liye ORS ya nimbu paani lena theek rahega?",
    "Agar match dopahar 2 baje ho jab dhoop zyada hoti hai, toh heat exhaustion se kaise bachein?",
    "Waise kal raat meri neend theek se nahi hui thi, lagbhag 4 ghante hi so paaya tha.",

    # Phase 3: Sleep hygiene & digital habits
    "Raat ko neend na aane ka ek main reason late night mobile scrolling hai mera. Isko kaise control karun?",
    "Koi relaxing bedtime drink suggest kar sakte ho bina sugar ke?",
    "Chamomile tea ya warm turmeric milk mein se kya better rahega?",

    # Phase 4: Nutrition, Pricing & Seasonal moderation
    "Waise Disha, yeh app paid hai kya? Kitne ka subscription hai?",
    "Mujhe weight loss bhi shuru karna hai, kya garmiyon ke dauran aam (mango) khana completely band karna padega ya moderation mein allowed hai?",
    "Aam ko dopahar mein khana theek hai ya raat ke dessert ke time?",
    "Office lunch mein aksar bahar ka khana padta hai, oily gravies avoid karne ke liye safe options kya hain?",
    "Subah breakfast mein kya light aur energy-giving rahega mere desk job ke liye?",

    # Phase 5: Recalling earlier conversation & synthesis
    "Subah jo humne 5 cup chai ki baat ki thi, kal se main max 2 cups pe limit karne ka plan kar raha hoon.",
    "Chai ki jagah agar green tea ya warm water with lemon loon toh acidity kam hogi?",
    "Aur cricket match ke din subah ka breakfast kaisa hona chahiye?",
    "Pacing aur rest breaks ke baare mein kuch tips batao.",
    "Agar beech mein halka sa muscle cramp lage khelte waqt toh turant kya karna chahiye?",
    "Aaj shaam ko thoda walk kar loon office ke baad fresh feel karne ke liye?",
    "Theek hai Disha, thank you so much for the practical guidance. Aaj raat jaldi sounga!",
]


async def run_simulation():
    os.makedirs("audit/simulations", exist_ok=True)
    async with httpx.AsyncClient(timeout=15.0) as client:
        # 1. Register synthetic user
        profile = {
            "name": "Aarav Sharma",
            "email": f"aarav.continuous.{int(time.time())}@disha.ai",
            "password": "Password123!",
            "age": 32,
            "gender": "male",
            "height_cm": 174.0,
            "weight_kg": 76.0,
            "conditions": ["Mild Fatigue"],
            "hypertension_stage": "normal",
            "gym_clearance": True,
            "activity_level": "moderate",
            "dietary_preference": "Vegetarian",
            "health_goals": ["Energy & Daily Stamina", "Sleep & Recovery"],
            "language": "hinglish",
            "health_focuses": ["Fitness and general wellness", "Sleep and fatigue", "Digestive health"],
            "health_focus_other": "",
        }
        res = await client.post(f"{BACKEND_URL}/auth/register", json=profile)
        if res.status_code != 200:
            print(f"[Aarav] Registration failed: {res.text}")
            return
        auth_data = res.json()
        token = auth_data["token"]
        patient_id = auth_data["patient_id"]
        print(f"[Aarav] Registered: {patient_id} ({profile['email']})")

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
                print(f"[Aarav Turn {idx:02d} | {record['elapsed_sec']}s | {latency_ms}ms] Disha: {response_text[:90]}...")

                # Automated failure checks:
                resp_lower = response_text.lower()
                if "provider_unavailable" in status or "jawab nahi de paa rahi" in resp_lower:
                    failures.append({"turn": idx, "issue": "provider_unavailable_timeout", "utterance": utterance})
                if idx == 14 and ("1499" not in resp_lower or "0" not in resp_lower):
                    if "free" not in resp_lower and "₹0" not in resp_lower:
                        failures.append({"turn": idx, "issue": "pricing_hallucination", "response": response_text})
                if idx == 15 and not any(w in resp_lower for w in ["moderation", "100g", "aam", "mango"]):
                    failures.append({"turn": idx, "issue": "mango_moderation_unsupported", "response": response_text})

                # Simulate realistic thinking/reading pause (12-16 seconds per turn to span 10 minutes)
                await asyncio.sleep(12.0)

        total_time = round(time.time() - start_time, 1)
        print(f"\n[Aarav Completed] Total time: {total_time}s across {len(TURNS)} turns. Failures: {len(failures)}")


if __name__ == "__main__":
    asyncio.run(run_simulation())

