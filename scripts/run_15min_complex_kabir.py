"""Disha AI — 15-Minute Continuous Active Conversation: Kabir Deshmukh (Complex & Multi-Concern User).

Conducts a strict 15-minute (900+ seconds) active real-world conversation with Disha AI backend.
Simulates multi-symptom overlaps (IBS + GERD + Night-Shift Fatigue), dietary transitions,
sensitive wellness questions (stress-induced performance anxiety), nicotine cravings,
and long-range contextual synthesis across 45-55 turns.
"""

import asyncio
import json
import os
import time

import httpx

BACKEND_URL = os.getenv("DISHA_HTTP_URL", "http://127.0.0.1:8080")
LOG_PATH = "audit/simulations/kabir_15min_full.jsonl"
TARGET_DURATION_SEC = 910.0  # 15 minutes and 10 seconds minimum


CONVERSATION_STAGES = [
    # Phase 1: Night-shift fatigue & erratic sleep schedule
    "Hi Disha, main Pune mein ek IT support role mein kaam karta hoon aur meri night shift rehti hai (8 PM se 5 AM).",
    "Pichhle 2 hafton se shift timing rotate ho gayi hai, jiski wajah se daytime mein bilkul gehri neend nahi aati.",
    "Din mein 3-4 ghante so paata hoon bas, phir achanak aankh khul jaati hai aur sar bhaari rehta hai.",
    "Kya shift workers ke liye melatonin supplements lena safe hota hai ya naturally circadian rhythm adjust karein?",
    "Morning 6 AM ghar aate waqt sunlight block karne ke liye dark sunglasses pehanna helpful rahega kya?",
    # Phase 2: IBS Flare-up & digestive distress
    "Ek aur problem hai Disha, mujhe doctor ne pehle IBS-M (alternating diarrhea and constipation) diagnose kiya tha.",
    "Night shift mein 2 AM cafeteria se spicy misal pav aur chai pi li thi, tab se pet mein cramps aur severe bloating hai.",
    "Har 2 ghante mein washroom bhagna pad raha hai, aur abdominal discomfort bilkul kam nahi ho raha.",
    "Kya ICMR guidelines ke hisaab se koi simple kitchen remedy hai jo turant cramps aur bloating shant kar sake?",
    "Saunf aur jeera ka warm water lene se IBS symptoms mein relief mil sakta hai kya?",
    # Phase 3: Acid Reflux (GERD) & Posture
    "Cramps ke saath saath chest mein sharp burning sensation (heartburn) bhi ho rahi hai jo throat tak aa rahi hai.",
    "Pata hai yeh GERD ka flare-up hai kyunki khana khate hi shift chair par aage jhuk kar baithna padta hai.",
    "Kya sofe par ya bed par sar ko 6-8 inches elevate karke sone se acid reflux backflow ruk sakta hai?",
    "Kya cold milk peene se heartburn temporarily relieve hota hai ya baad mein rebound acid create karta hai?",
    # Phase 4: Dietary changes — Whey Protein vs Tofu/Plant protein
    "Main gym restart karna chahta tha aur ek trainer ne mujhe Whey Protein Concentrate lene ko bola.",
    "Lekin jab bhi whey shake leta hoon, pet phool jata hai aur gas bohot zyada banne lagti hai.",
    "Kya IBS aur lactose sensitivity wale logon ke liye Whey Isolate ya plant-based pea/brown rice protein better hota hai?",
    "Agar main protein powder band karke tofu aur moong dal chilla par switch karun toh digest karna aasan hoga?",
    "Tofu ko cooked form mein lene se bloating ka risk raw tofu ke comparison mein kam hota hai kya?",
    # Phase 5: Sensitive health topic — Stress, fatigue & libido/performance anxiety
    "Disha, ek personal aur sensitive sawal poochna tha bina kisi judgement ke.",
    "Night shift ke chronic fatigue aur work deadlines ke pressure ki wajah se meri sex drive bilkul low ho gayi hai.",
    "Partner ke saath intimate moments mein severe performance anxiety hoti hai aur mood nahi banta.",
    "Kya chronic sleep deprivation aur elevated cortisol levels directly male testosterone aur libido ko suppress karte hain?",
    "Bina kisi OTC pills ke, lifestyle aur stress management se is anxiety ko normalize kaise kar sakte hain?",
    "Kya pelvic floor relaxation exercises ya mindful breathing intimacy se pehle tension reduce karne mein madad karegi?",
    # Phase 6: Nicotine reduction & withdrawal cravings
    "Night shift mein jaagte rehne ke liye main pichhle 3 saal se din mein 5-6 cigarettes peeta aa raha tha.",
    "Abhi 3 din pehle maine bilkul quit karne ka decide kiya hai, lekin withdrawal bohot tough ho raha hai.",
    "Raat ke 3 baje extreme restlessness hoti hai aur haath kaanpne lagte hain craving ki wajah se.",
    "Jab acute craving hit kare toh 5-10 minutes ka delay mechanism ya deep breathing kaise apply karein?",
    "Kya chewing clove (laung) ya cinnamon stick mouth diversion ke liye effective hai jab smoking urge aaye?",
    # Phase 7: Memory recall & Holistic synthesis
    "Disha, pehle humne jo baat ki thi: meri night shift neend, IBS ka trigger, aur smoking withdrawal — sab interlinked hain na?",
    "Jab stress badhta hai toh mera IBS flare hota hai, aur IBS flare se neend kharab hoti hai.",
    "Aap mere liye ek realistic 24-hour routine outline kar sakti ho jo meri 8 PM - 5 AM shift ko accommodate kare?",
    "Subah 5:30 AM shift end hone ke baad ghar aane par kya halka breakfast lena chahiye sone se pehle?",
    # Phase 8: Database Diet Schedule check & Meal timings
    "Aaj raat ke khane (dinner) ke liye meri IBS-safe diet schedule mein kya recommended hai?",
    "Agar main raat 1 AM lunch break mein 150g paneer bhurji aur 2 rotis ke sath boiled vegetables loon toh safe hai?",
    "Khane ke turant baad tea ya black coffee lene se digestion par kya asar padega?",
    # Phase 9: Hydration & Electrolytes on Night Shift
    "Shift ke dauran AC room mein dehydration notice nahi hota, phir morning mein dark urine aati hai.",
    "Pura din kitna paani peena chahiye aur timing kaise divide karein taaki neend ke dauran bar bar urine na jana pade?",
    "Electrolyte water ya ORS lene ki zaroorat hai ya plain water + coconut water enough hai?",
    # Phase 10: Long-term plan & Final check-in
    "Toh plan clear hai: morning dark room sleep, saunf-jeera water for cramps, plant protein, aur nicotine urge diversion.",
    "Agar agle 48 ghante mein IBS cramping kam na ho ya stool mein blood aaye toh turant gastroenterologist ko dikhana hoga na?",
    "Red flag symptoms clear samajh aa gaye hain mujhe.",
    "Disha, thank you so much for understanding my complicated schedule and multiple issues without overwhelming me.",
    "Main kal afternoon mein uthne ke baad apna update dunga. Take care!",
]


async def run_15min_complex_session():
    os.makedirs("audit/simulations", exist_ok=True)
    async with httpx.AsyncClient(timeout=15.0) as client:
        profile = {
            "name": "Kabir Deshmukh",
            "email": f"kabir.deshmukh.{int(time.time())}@disha.ai",
            "password": "Password123!",
            "age": 36,
            "gender": "male",
            "height_cm": 174.0,
            "weight_kg": 76.0,
            "conditions": ["IBS", "GERD", "Shift Work Sleep Disorder"],
            "hypertension_stage": "normal",
            "gym_clearance": True,
            "activity_level": "moderate",
            "dietary_preference": "Vegetarian",
            "health_goals": ["Heal Gut & Acid Reflux", "Stabilize Night Shift Energy", "Overcome Nicotine Cravings"],
            "language": "hinglish",
            "health_focuses": ["Gut health and digestion", "Sleep and fatigue", "Stress and mental wellbeing"],
            "health_focus_other": "Rotating night shift schedule, IBS triggers, nicotine withdrawal",
        }
        res = await client.post(f"{BACKEND_URL}/auth/register", json=profile)
        if res.status_code != 200:
            print(f"[Kabir 15min] Registration failed: {res.text}")
            return
        auth_data = res.json()
        token = auth_data["token"]
        patient_id = auth_data["patient_id"]
        print(f"[Kabir 15min] Registered: {patient_id} ({profile['name']})")

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        start_time = time.time()
        turn_idx = 0

        with open(LOG_PATH, "w") as log_file:
            while (time.time() - start_time) < TARGET_DURATION_SEC:
                turn_idx += 1
                if turn_idx <= len(CONVERSATION_STAGES):
                    utterance = CONVERSATION_STAGES[turn_idx - 1]
                else:
                    cycle = turn_idx - len(CONVERSATION_STAGES)
                    utterance = f"Disha, meri night-shift routine aur gut health check-in #{cycle}: digestive comfort aur sleep pacing ko maintain karne ke liye aur koi simple tip?"

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
                print(f"[Kabir Turn {turn_idx:02d} | {elapsed}s/900s | {latency_ms}ms] Disha: {response_text[:85]}...")

                # Pacing delay between turns: 18-22 seconds to mirror real human reading & typing pace
                remaining = TARGET_DURATION_SEC - (time.time() - start_time)
                if remaining > 0:
                    sleep_dur = min(20.0, remaining)
                    await asyncio.sleep(sleep_dur)

        total_elapsed = round(time.time() - start_time, 1)
        print(
            f"\n[Kabir Completed Full 15 Min] Total active duration: {total_elapsed}s ({round(total_elapsed / 60, 2)} mins), {turn_idx} turns."
        )


if __name__ == "__main__":
    asyncio.run(run_15min_complex_session())
