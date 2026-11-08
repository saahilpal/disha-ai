"""Disha AI — 15-Minute Continuous Active Conversation: Rohan Verma (Realistic User).

Conducts a strict 15-minute (900+ seconds) active real-world conversation with Disha AI backend.
Simulates natural pacing, progressive disclosures, unexpected topic shifts, memory recalls,
pricing inquiries, and nutritional moderation queries across 45-55 turns.
"""
import asyncio
import json
import os
import time

import httpx

BACKEND_URL = os.getenv("DISHA_HTTP_URL", "http://127.0.0.1:8080")
LOG_PATH = "audit/simulations/rohan_15min_full.jsonl"
TARGET_DURATION_SEC = 910.0  # 15 minutes and 10 seconds minimum


CONVERSATION_STAGES = [
    # Topic 1: Morning fatigue & cold brew coffee habit
    "Hi Disha, I've been feeling unusually tired and sluggish since waking up today.",
    "Haan thoda heavy feel ho raha hai, aur subah se 2 large cold brew coffees pi chuka hoon bina kuch khaye.",
    "Kya empty stomach cold brew peene se acidity ya jitteriness badh sakti hai?",
    "Abhi ke liye mujhe thoda fresh feel karna hai, office meeting hai 30 mins mein. Quick fix kya ho sakta hai?",
    "Thoda normal paani pi liya maine aur face wash kiya, headache thoda kam hua hai.",

    # Topic 2: Work desk posture & screen fatigue
    "Waise din bhar laptop screen dekhne se meri aankhon mein jalan aur neck stiffness ho rahi hai.",
    "Kya desk par baithe baithe koi simple neck aur shoulder stretches kar sakte hain?",
    "Blue light glasses pehnna sach mein helpful hota hai ya sirf marketing hype hai?",
    "Office chair par lumbar support ke liye pillow lagana theek rahega?",

    # Topic 3: Lunch choices & afternoon energy crash
    "Lunch time hone wala hai. Bahar cafeteria mein chole bhature, dal tadka with roti, aur veg thali options hain.",
    "Agar dal tadka aur 2 rotis loon toh afternoon mein lethargy ya bloating toh nahi hogi?",
    "Dopahar ke khane ke baad aksar bohot neend aati hai, is crash ko kaise rokein?",
    "Lunch ke turant baad 10 minute walk karna kaisa rahega?",

    # Topic 4: Weekend football & sports fitness
    "Waise is Sunday main doston ke saath football khelne ka plan bana raha hoon.",
    "Kya mera fitness level football ke 90 minutes sprint match ke liye safe hai?",
    "Football khelte waqt hydration ke liye plain water better hai ya coconut water?",
    "Agar match ke dauran calf muscle tight lage toh turant kya karna chahiye?",

    # Topic 5: Memory recall & coffee habit check-in
    "Subah jo humne 2 large cold brew coffee ki baat ki thi, kya uski wajah se dehydration ho sakta hai match mein?",
    "Daily caffeine limit kitni honi chahiye ek 27 year old desk worker ke liye?",
    "Coffee ko replace karne ke liye koi healthy warm drink batao office ke liye.",

    # Topic 6: Evening workout & Gym clearance
    "Office ke baad gym jaakar moderate strength training ya dumbbell exercises karna chahun toh allowed hai?",
    "Chest press aur squats ke 3 sets karna theek rahega aaj ke fatigue level ke sath?",
    "Pre-workout snack mein ek banana ya handful of almonds khana kaisa rahega?",

    # Topic 7: Pricing & Capability boundaries
    "Disha, ek baat batao, yeh app paid hai kya? Kitne ka subscription hai?",
    "Agar main daily personal guidance aur meal reviews chahta hoon toh kya extra charge hoga?",
    "Kya tum mere phone pe WhatsApp par daily morning motivation aur workout plan bhej sakti ho?",

    # Topic 8: Seasonal Fruit & Nutrition Moderation
    "Garmiyon mein aam (mango) khane se mera body fat badhega kya? Weight loss ke time aam bilkul band karna padega?",
    "Din mein 100g mango slice khana theek hai ya dinner ke baad dessert jaisa lena chahiye?",
    "Mango shake with sugar vs whole fresh fruit slice mein health ke hisaab se kya difference hai?",

    # Topic 9: Sleep schedule & night routine
    "Raat ko neend aane mein bohot time lagta hai, aksar 1:30 AM tak phone scroll karta rehta hoon.",
    "Late night screen scrolling habit ko break karne ke liye practical trick kya hai?",
    "Room temperature aur darkness ka neend ki quality par kya impact padta hai?",
    "Kya raat ko warm milk lena digestion ke liye heavy hota hai ya sleep induce karta hai?",

    # Topic 10: Long-range context synthesis & habit commitment
    "Toh summary mein: subah cold brew kam karna hai, dopahar light lunch + walk, aur football ke liye hydration.",
    "Aaj raat ko kitne baje dinner complete kar lena chahiye agar 11 PM sona hai?",
    "Dinner mein light khana jaise moong dal khichdi ya paneer salad theek rahega?",
    "Aur kal subah se coffee ki jagah warm lemon water lene se kaisa feel hoga?",
    "Weekends par football match ke baad recovery ke liye best protein source kya hai vegetarian ke liye?",
    "Soya chunks ya paneer mein se post-workout protein kismein zyada easily absorb hota hai?",
    "Theek hai Disha, thank you so much for guiding me through the whole day so patiently!",
    "Kal subah check-in karunga apne breakfast ke baad. Good night!",
]


async def run_15min_realistic_session():
    os.makedirs("audit/simulations", exist_ok=True)
    async with httpx.AsyncClient(timeout=15.0) as client:
        # Register new realistic persona
        profile = {
            "name": "Rohan Verma",
            "email": f"rohan.verma.{int(time.time())}@disha.ai",
            "password": "Password123!",
            "age": 27,
            "gender": "male",
            "height_cm": 177.0,
            "weight_kg": 74.0,
            "conditions": ["Mild Fatigue", "Work Stress"],
            "hypertension_stage": "normal",
            "gym_clearance": True,
            "activity_level": "moderate",
            "dietary_preference": "Vegetarian",
            "health_goals": ["Build Lean Stamina", "Fix Sleep Cycle"],
            "language": "hinglish",
            "health_focuses": ["Fitness and general wellness", "Sleep and fatigue"],
            "health_focus_other": "",
        }
        res = await client.post(f"{BACKEND_URL}/auth/register", json=profile)
        if res.status_code != 200:
            print(f"[Rohan 15min] Registration failed: {res.text}")
            return
        auth_data = res.json()
        token = auth_data["token"]
        patient_id = auth_data["patient_id"]
        print(f"[Rohan 15min] Registered: {patient_id} ({profile['name']})")

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        start_time = time.time()
        turn_idx = 0

        with open(LOG_PATH, "w") as log_file:
            # Continue conversational loop until 900+ seconds have elapsed
            while (time.time() - start_time) < TARGET_DURATION_SEC:
                turn_idx += 1
                if turn_idx <= len(CONVERSATION_STAGES):
                    utterance = CONVERSATION_STAGES[turn_idx - 1]
                else:
                    cycle = turn_idx - len(CONVERSATION_STAGES)
                    utterance = f"Disha, meri daily energy aur routine ke baare mein quick check-in #{cycle}: hydration aur sleep ko aur kaise optimize karun?"

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

                elapsed = round(time.time() - start_time, 1)
                record = {
                    "turn": turn_idx,
                    "timestamp": time.time(),
                    "elapsed_sec": elapsed,
                    "user": utterance,
                    "disha": response_text,
                    "status": status,
                    "latency_ms": latency_ms,
                }
                log_file.write(json.dumps(record) + "\n")
                log_file.flush()
                print(f"[Rohan Turn {turn_idx:02d} | {elapsed}s/900s | {latency_ms}ms] Disha: {response_text[:85]}...")

                # Pacing delay between turns: 18-22 seconds to mirror real human reading & typing pace
                remaining = TARGET_DURATION_SEC - (time.time() - start_time)
                if remaining > 0:
                    sleep_dur = min(20.0, remaining)
                    await asyncio.sleep(sleep_dur)

        total_elapsed = round(time.time() - start_time, 1)
        print(f"\n[Rohan Completed Full 15 Min] Total active duration: {total_elapsed}s ({round(total_elapsed/60, 2)} mins), {turn_idx} turns.")


if __name__ == "__main__":
    asyncio.run(run_15min_realistic_session())
