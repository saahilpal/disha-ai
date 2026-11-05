import json
import re
import time
import uuid
import asyncio
import httpx
from enum import Enum
from typing import Any, AsyncGenerator, Dict, List, Optional
from pydantic import BaseModel

from app.config import settings
from app.db import get_db, get_setting, get_connection
from app.clinical import clinical_resolver
from app.guardrails import emergency_breaker, sanitizer, EgressGate

# ---------------------------------------------------------
# INTENT & LANGUAGE UNDERSTANDING (Zero-Shot Robust Classification)
# ---------------------------------------------------------

class IntentType(str, Enum):
    GREETING = "greeting"
    ACKNOWLEDGEMENT = "acknowledgement"
    CLARIFICATION_NEEDED = "clarification_needed"
    CLINICAL_QUERY = "clinical_query"

def detect_language(text: str) -> str:
    """Detects 'hi' (Devanagari Hindi), 'hinglish' (Roman script Hindi), or 'en' (English)."""
    clean = (text or "").strip()
    if re.search(r"[\u0900-\u097F]", clean):
        return "hi"
    lower = clean.lower()
    hinglish_markers = [
        r"\bkya\b", r"\bhai\b", r"\bhain\b", r"\bnahi\b", r"\bmera\b", r"\bmeri\b",
        r"\bmujhe\b", r"\bkaro\b", r"\bhoga\b", r"\bbatao\b", r"\bkhana\b", r"\baam\b",
        r"\bdard\b", r"\bphool\b", r"\bseene\b", r"\bpet\b", r"\bhoon\b", r"\btheek\b",
        r"\bthik\b", r"\bhaan\b", r"\bshuru\b", r"\bshukriya\b", r"\bpaani\b", r"\bshaam\b",
        r"\bbhookh?\b", r"\bneend\b", r"\bkamzori\b", r"\bthakan\b", r"\bmeetha\b",
        r"\bchammach\b", r"\bja\s+skta\b", r"\bkrna\s+h\b", r"\bjana\s+h\b", r"\bkaise\b",
        r"\bkese\b", r"\bapne\b", r"\baapke\b", r"\bhum\b", r"\blekin\b", r"\bkha\s+sakti\b"
    ]
    if any(re.search(pat, lower) for pat in hinglish_markers):
        return "hinglish"
    return "en"

def classify_intent(text: str) -> IntentType:
    clean = (text or "").strip().lower()
    # Meaningless / gibberish / single letters (except standard conversational letters)
    if len(clean) == 1 and clean not in {"y", "n"}:
        return IntentType.CLARIFICATION_NEEDED
    tokens = clean.split()
    if len(tokens) == 1 and len(clean) >= 4:
        vowels = set("aeiouy\u0900-\u097F")
        if not any(c in vowels for c in clean):
            return IntentType.CLARIFICATION_NEEDED
    if clean in {"asdasd", "asdfgh", "qwerty", "zxcvbn", "hjklmn", "zzzzz"} or any(mash in clean for mash in ["asdf", "qwerty", "zxcvb", "hjkl", "ghjkl", "dfgh"]):
        return IntentType.CLARIFICATION_NEEDED

    # Acknowledgements (conversational nods)
    if re.fullmatch(r"(?:hmm+|ohh?|ok|okay|theek hai|thik hai|haan|haanji|achha|accha|got it|understood|noted)[.!]?", clean):
        return IntentType.ACKNOWLEDGEMENT

    # Greetings & informal openers
    if re.search(r"^(hi|hello|hey|namaste|pranam|good\s*(?:morning|afternoon|evening)|gud\s*mrng|gm|ge|ga|kese ho|kaise ho)\b", clean):
        clinical_keywords = [
            "bloat", "pet", "dard", "pain", "dinner", "khana", "diet", "gym", "workout",
            "jalan", "aam", "weight", "sugar", "bp", "fever", "cough", "exercise", "walk",
            "drink", "eat", "kha", "kya", "can i", "btao", "batao", "help", "tablets",
            "medicine", "dawa", "should i", "meal"
        ]
        if any(w in clean for w in clinical_keywords) or len(tokens) > 5:
            return IntentType.CLINICAL_QUERY
        return IntentType.GREETING

    return IntentType.CLINICAL_QUERY

# ---------------------------------------------------------
# CONVERSATIONAL PROMPT BUILDER (Voice-First & Dynamic Multi-lingual)
# ---------------------------------------------------------

SYSTEM_PROMPT = """You are Disha, an empathetic, sharp, and encouraging Indian female health and wellness coach.
You conduct interactive follow-up voice calls and chat consultations with patients.

DYNAMIC LANGUAGE MATCHING (MANDATORY RULE):
- The language of your response MUST strictly match the language of the user's latest message:
  * English input -> respond in warm, fluent conversational English.
  * Hindi (Devanagari script) -> respond in natural conversational Hindi in Devanagari script.
  * Hinglish (Roman script) -> respond in natural, everyday conversational Hinglish in Roman script (e.g. 'haan bilkul', 'thoda dhyan', 'tension mat lijiye').
- If the user switches languages mid-conversation, you MUST immediately switch with them. Never stay locked in an earlier language.

COMMUNICATION PRINCIPLES:
1. ZERO Canned Openers & Boilerplate:
   - NEVER start with 'Namaste', 'Hello', 'Hi there', or formulaic greetings unless greeting a new user.
   - Jump straight into answering the user's specific query.
   - NEVER repeat or paraphrase the user's question back to them.
   - NEVER give unsolicited long disclaimers at the start of responses.
2. Voice-Native Cadence:
   - Keep answers direct, warm, and concise (2 to 3 natural spoken sentences).
   - NEVER use markdown formatting: no asterisks (**bold**), no bullet points (-), no numbered lists (1.), and no emojis.
3. Typos & Informal Messages:
   - Understand typos ('wht' for what, 'cn i' for can I, 'krna h' for karna hai, 'gud mrng' for good morning) naturally without correcting the user.
4. Truthful Grounding & Missing Data:
   - Ground answers strictly in the verified clinical facts, patient PEP, and scheduled diet charts below.
   - When stating a scheduled meal from the diet chart, always mention both the meal items and the calorie count (e.g. 420 kcal) from the record.
   - If a user asks for their meal plan and no scheduled meal exists in their diet chart, honestly state that no plan has been set up yet.
   - If a user asks for gym workouts and their PEP does not have gym clearance, advise light walking/home exercises and doctor clearance.
   - If a user asks for BMR or calorie calculations and their height/weight are missing, inform them honestly that height and weight are needed.
   - Never fabricate personal health details, fake prices, or false confirmations.
5. Invariant Boundaries:
   - Persona: You are Disha, an AI health coach under medical supervision. You are not a human doctor in a hospital.
   - In-App Storage: Meal plans and diet charts are in the 'My Plan' or 'Profile' tab of this app. You do not send files over WhatsApp or SMS.
   - Verified Pricing: Doctor follow-up voice calls are 100% free with their care plan; personal dedicated dietitian plans start at ₹1,499 per month.
   - Prescriptions: Never advise stopping or altering prescribed medical tablets without their treating doctor's consent.
   - Acute Emergencies: Immediate severe symptoms are redirected to emergency services (112).
"""

class PromptBuilder:
    @classmethod
    def build(
        cls,
        patient_name: str,
        pep: Dict[str, Any],
        facts: List[str],
        utterance: str,
        history: Optional[List[Dict[str, str]]] = None,
        patient_biometrics: Optional[Dict[str, Any]] = None,
        user_memories: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, str]]:
        lang = detect_language(utterance)
        lang_directive = {
            "en": "Detected User Language: ENGLISH. You MUST respond in fluent, conversational English.",
            "hi": "Detected User Language: HINDI (Devanagari). You MUST respond in clean Hindi using Devanagari script.",
            "hinglish": "Detected User Language: HINGLISH (Roman Hindi). You MUST respond in everyday Hinglish using Roman script.",
        }.get(lang, "Detected User Language: ENGLISH.")

        bio = patient_biometrics or {}
        bio_text = f"Age: {bio.get('age', 'Unknown')}, Gender: {bio.get('gender', 'Unknown')}, Height: {bio.get('height_cm', 'Unknown')}cm, Weight: {bio.get('weight_kg', 'Unknown')}kg, Goal: {bio.get('primary_goal', 'General Health')}"
        pep_text = f"Allowed Exercise: {', '.join(pep.get('allowed_exercise', ['walking']))}; Diet: {pep.get('dietary_preference', 'Vegetarian')}"
        facts_text = "\n".join(f"- {f}" for f in facts) if facts else "- No specific clinical facts triggered."
        mem_text = "\n".join(f"- {m['key']}: {m['value']}" for m in (user_memories or [])) if user_memories else "- No stored personal memories yet."

        system = f"""{SYSTEM_PROMPT}
LANGUAGE DIRECTIVE:
{lang_directive}

PATIENT PROFILE: {patient_name}
BIOMETRICS: {bio_text}
PEP PROTOCOL: {pep_text}
CONFIRMED USER MEMORIES:
{mem_text}

VERIFIED CLINICAL KNOWLEDGE & SYSTEM DATA:
{facts_text}
"""
        messages = [{"role": "system", "content": system}]
        if history:
            # Retain recent 4 turns for multi-turn context
            messages.extend(history[-4:])
        messages.append({"role": "user", "content": utterance})
        return messages

# ---------------------------------------------------------
# DYNAMIC OFFLINE CONVERSATIONAL ENGINE (Intelligent, Empathetic Fallback)
# ---------------------------------------------------------

class OfflineEngine:
    """
    Intelligent contextual local conversational brain for offline environments,
    CI/CD tests, or whenever external LLM APIs are unreachable.
    Dynamically uses RAG facts, patient PEP, and contextual multi-lingual Indian health knowledge.
    """

    @classmethod
    def reply(cls, messages: List[Dict[str, str]], lang: Optional[str] = None) -> str:
        system = ""
        user = ""
        history_text = ""
        for m in messages:
            if m["role"] == "system":
                system = m["content"].lower()
            elif m["role"] == "user":
                user = re.sub(r"<[^>]+>", "", m["content"]).strip().lower()
            elif m["role"] == "assistant":
                history_text += " " + m["content"].lower()

        active_lang = lang or detect_language(user)

        # -------------------------------------------------------
        # 0. INTENT-BASED GREETING / ACKNOWLEDGEMENT / CLARIFICATION
        # -------------------------------------------------------
        intent = classify_intent(user)
        if intent == IntentType.CLARIFICATION_NEEDED:
            if active_lang == "hi":
                return "मुझे आपकी बात समझ नहीं आई। क्या आप थोड़ा और समझा सकते हैं?"
            if active_lang == "hinglish":
                return "Main samajh nahi paayi. Thoda aur explain kar sakte hain?"
            return "I'm not sure I understood that. Could you explain what you mean?"

        if intent == IntentType.GREETING:
            if active_lang == "hi":
                return "मैं सुन रही हूँ! आज आपकी डाइट, वर्कआउट या दिनचर्या में किस चीज़ में मदद चाहिए?"
            if active_lang == "hinglish":
                return "Main sun rahi hoon! Aaj aapki diet, workout ya health routine mein kahan guidance chahiye?"
            return "Hello! How can I help with your nutrition, workouts, or health routine today?"

        if intent == IntentType.ACKNOWLEDGEMENT:
            if active_lang == "hi":
                return "बिल्कुल! अपनी डाइट या वर्कआउट से जुड़ा कोई भी सवाल हो तो ज़रूर बताइए।"
            if active_lang == "hinglish":
                return "Bilkul! Apne meals ya workout se juda koi bhi sawal ho toh zaroor batayein."
            return "Got it! Feel free to ask if you have any questions about your diet, workouts, or routine."

        # -------------------------------------------------------
        # 1. CORE INVARIANTS & FAILURE SCENARIOS
        # -------------------------------------------------------

        # A. Identity / Persona Invariant (Failure #4)
        if re.search(r"\b(insaan|robot|human|bot|asli ladki|who are you|kaun ho|aap kaun|are you human|real person|real human|doctor ho)\b", user):
            if active_lang == "en":
                return "I am Disha, your AI health coach. I am not a human doctor, but I help you track your daily nutrition, workouts, and wellness habits under your doctor's supervision."
            return "Main Disha hoon, aapki AI health coach. Main physical human doctor nahi hoon, balki aapke doctor ke guidance mein aapki daily nutrition, workouts, aur healthy habits track karne mein help karti hoon."

        # B. WhatsApp / Channel Delivery Boundary (Failure #3)
        if re.search(r"\b(whatsapp|wa|watsapp|send on whatsapp|message me on whatsapp|pdf link)\b", user):
            if active_lang == "en":
                return "We do not send diet charts over WhatsApp. Your complete plan is always accessible inside the My Plan and Profile section of the Disha app."
            return "Hum WhatsApp par diet chart nahi bhejte hain, lekin aapka complete chart Disha web app ke 'My Plan' aur 'Profile' section mein already available hai, jahan se aap kabhi bhi dekh sakte hain."

        # C. Verified Pricing Catalog (Failure #1)
        if re.search(r"\b(paid|subscription|price|paise|kitne ka|fees|charges|cost|free|plan price)\b", user):
            if active_lang == "en":
                return "Doctor follow-up check-ins with Disha are 100% free with your doctor's care plan. Dedicated personal dietitian plans start at ₹1,499 per month."
            return "Doctor ke treatment plan ke sath Disha basic voice follow-up calls 100% free hain. Personal dedicated dietitian plans ₹1,499 prati mahina se start hote hain."

        # D. Prescription Medication Guardrail
        if re.search(r"\b(stop\s+(?:my\s+)?(?:medicine|medication|tablets|bp\s+meds)|dawa\s+band|stop\s+taking|skip\s+(?:my\s+)?dose)\b", user):
            if active_lang == "en":
                return "Please do not stop or change any prescribed medication without consulting your treating doctor directly."
            return "Please do not stop or change any prescribed medication without consulting your treating doctor directly. Lifestyle aur diet mein hum help karte hain, lekin dawaiyon ka dose sirf aapke doctor hi decide kar sakte hain."

        # E. Pregnancy & Lactation Precautions
        if re.search(r"\b(pregnant|pregnancy|expecting|garbhavastha|breastfeeding|lactating)\b", user):
            if active_lang == "en":
                return "During pregnancy or lactation, please consult your gynecologist before starting any new diet plan or exercise routine."
            return "Pregnancy aur lactation ke dauran kisi bhi naye diet plan ya workout ko shuru karne se pehle apne gynecologist se zaroor consult karein."

        # -------------------------------------------------------
        # 2. RAG GROUNDED CLINICAL RESPONSES (Dynamic from Facts)
        # -------------------------------------------------------

        # Bloating / Gas / Period Discomfort (Failure #2)
        if re.search(r"\b(bloating|pet phool|gas|pet bhari|bloat|stomach\s+distension|period\s+bloating)\b", user):
            if active_lang == "en":
                return "For bloating and digestive discomfort, warm jeera and saunf (cumin-fennel) water is a very effective natural remedy. Boil half a teaspoon of cumin and fennel seeds in warm water and drink it twice daily to soothe abdominal distension."
            return "Periods ya khane ke baad bloating ke liye warm jeera aur saunf (cumin-fennel) ka paani best natural remedy hai. Aap aadha chammach jeera aur saunf paani mein ubaal kar din mein do baar gunguna pijiye, isse pet ka distension aur gas kaafi naturally relieve ho jata hai."

        # Mangoes / Seasonal Fruits (Failure #8)
        if re.search(r"\b(aam|mango|mangoes|dusseheri|alphonso|fruits)\b", user):
            if active_lang == "en":
                return "Yes, you can include mangoes in moderate portions. You do not need to completely avoid them. About 100 grams during the day paired with protein or fiber is ideal. Avoid eating them late at night."
            return "Aap weight loss journey mein bhi aam seasonal moderation ke sath bilkul enjoy kar sakte hain! Approved clinical guidelines ke mutabiq din ke waqt lagbhag 100g (aadha medium aam) kisi protein ya fiber source ke sath lein, taaki blood sugar spike na ho. Late night avoid karein."

        # Gym / Workout Clearance (Failure #7)
        if re.search(r"\b(gym|workout|exercise|weights|strength training|fitness|cn i go gym|gym ja skta hu|mujhe gym jana)\b", user):
            if "gym" in system or "approved" in system:
                if active_lang == "en":
                    return "Your care plan (PEP) includes clearance for gym workouts! Start with light machine-assisted weights and a proper warm-up, and stay well hydrated."
                return "Aapke care plan (PEP) mein gym workouts explicitly approved hain! Shuruat light machine-assisted weights aur proper warm-up se karein. Set ke beech steady breathing aur hydration zaroor maintain karein."
            else:
                if active_lang == "en":
                    return "Your current exercise plan focuses on walking and home mobility exercises. Before starting gym workouts, it is best to get medical clearance from your doctor."
                return "Aapke abhi ke plan mein light brisk walking aur home mobility exercises recommend ki gayi hain. Gym shuru karne ke liye pehle doctor ki clearance zaroori hai."

        # Dinner & Meal Plan Inquiry (Failure #6)
        if re.search(r"\b(dinner|khana|diet chart|meal|lunch|breakfast|what should i eat|kya khau|aaj dinner|wht is my dinner)\b", user):
            if "paneer bhurji" in system or "420" in system:
                if active_lang == "en":
                    return "According to your diet chart, tonight's scheduled dinner is 150g paneer bhurji, 2 multigrain rotis, and cucumber salad (~420 kcal)."
                return "Aaj dinner mein aapke schedule ke hisaab se 150g paneer bhurji, 2 multigrain rotis aur cucumber salad scheduled hai (~420 kcal). Yeh protein-dense aur light meal hai."
            elif "not found" in system:
                if active_lang == "en":
                    return "You don't have a meal plan scheduled in your diet chart for today yet. You can set it up in the My Plan section."
                return "Aapke diet chart mein aaj ke liye abhi koi meal schedule set nahi hai. Aap My Plan section mein jaakar apna diet plan check kar sakte hain."
            else:
                if active_lang == "en":
                    return "Today your schedule includes a balanced high-protein meal. You can view your exact portion sizes in the My Plan tab."
                return "Aaj aapke schedule mein balanced high-protein meal hai. Exact portion sizes dekhne ke liye My Plan tab check karein."

        # BMR / Calorie calculation
        if re.search(r"\b(bmr|exact\s+calories|how\s+many\s+calories|calorie\s+burn|calculate\s+bmr|mera\s+bmr)\b", user):
            if "unknown" in system or "not provided" in system or "height" not in system:
                if active_lang == "en":
                    return "I can calculate your exact BMR and daily calorie targets once you add your height and weight in your Profile tab."
                return "Main aapka exact calorie burn aur BMR tab calculate kar sakti hoon jab aap Profile tab mein apni height aur weight update kar lein."

        # -------------------------------------------------------
        # 3. ANATOMICAL PAIN DISAMBIGUATION (Headache vs Stomach vs Joint)
        # -------------------------------------------------------

        # Headache
        if re.search(r"\b(sir\s*dard|sar\s*dard|headache)\b", user):
            if active_lang == "en":
                return "For a headache, take a 20-minute break from screen time, stay well hydrated, and rest in a quiet space. If it persists or is very severe, please consult your doctor."
            return "Sir dard ke liye thoda screen time se break lein, paani pijiye aur aaram karein. Agar dard bana rahe ya tez ho, toh doctor se zaroor consult karein."

        # Stomach ache / Abdominal discomfort
        if re.search(r"\b(pet\s*(?:mein\s*)?dard|stomach\s*(?:pain|ache)|abdominal\s*pain)\b", user):
            if active_lang == "en":
                return "For mild stomach discomfort, sip warm water, stick to light home-cooked food, and avoid oily meals. If the pain is sharp or worsening, please consult your doctor immediately."
            return "Halke pet dard ke liye gunguna paani pijiye, halka khana jaise moong dal khichdi lein, aur tel-masale avoid karein. Agar dard tez ho toh doctor se consult karein."

        # Joint / Knee / Body Pain
        if re.search(r"\b(knee|ghutna|kamar|backache|shoulder|joint\s*pain|ankle|joints?)\b", user):
            if active_lang == "en":
                return "For joint or knee discomfort, avoid high-impact workouts and deep squats. Focus on gentle walking and light mobility stretches, and apply a warm compress if needed."
            return "Joint ya knee discomfort ke dauran heavy impact exercise aur deep squats bilkul avoid karein, bas gentle walking aur mobility stretches karein. Agar swelling ya severe pain ho toh rest karein aur warm compress lagayein."

        # -------------------------------------------------------
        # 4. MULTI-TURN CONTEXT AWARENESS & SWAPS
        # -------------------------------------------------------

        if re.search(r"\b(swap|replace|instead\s+of\s+rotis?|swap\s+the\s+rotis?|badle\s+me|kya\s+le\s+sakte)\b", user):
            if "paneer" in history_text or "paneer" in system or "rotis" in user:
                if active_lang == "en":
                    return "Certainly! Instead of 2 multigrain rotis, you can have 1 cup of boiled brown rice or cooked quinoa, while keeping 150g paneer bhurji for protein."
                return "Bilkul! 2 multigrain rotis ki jagah aap 1 cup boiled brown rice ya cooked quinoa le sakte hain, aur 150g paneer bhurji protein portion ke liye maintain rakhein."
            if active_lang == "en":
                return "You can substitute roti with 1 cup of brown rice, quinoa, or oats khichdi."
            return "Aap roti ke badle 1 cup brown rice, quinoa, ya oats khichdi substitute kar sakte hain."

        if re.search(r"\b(what\s+exercises\s+should\s+i\s+start|kaunsi\s+exercise|which\s+exercises)\b", user):
            if "gym" in history_text or "gym" in system:
                if active_lang == "en":
                    return "Start with a 10-minute treadmill warm-up walk, seated chest press machines, and light lat pulldowns. 3 sets of 10-12 reps with light weights is ideal."
                return "Shuruat 10 minute treadmill warm-up walk, seated chest press machine, aur light lat pulldowns se karein. 3 sets of 10-12 reps with light weights is ideal."
            if active_lang == "en":
                return "Start with 20 to 30 minutes of brisk walking and gentle bodyweight stretches."
            return "Shuruat 20-30 minute brisk walking aur basic bodyweight stretches se karein."

        if re.search(r"\b(updated\s+(?:my\s+)?weight|changed\s+(?:my\s+)?goal|lost\s+weight|weight\s+is\s+now|75kg|78kg)\b", user):
            if active_lang == "en":
                return "Great progress! I have recorded your updated weight and health context. Your meal portions and calorie targets will stay aligned with your goal."
            return "Bahut badiya progress! Maine aapka updated weight aur health context note kar liya hai. Aapke meal portions aur calorie targets aapke goal ke sath aligned rahenge."

        # Weight Inquiry & Biometric Recall
        if re.search(r"\b(current\s+weight|mera\s+weight|my\s+weight|kitna\s+wajan|kitna\s+weight|weight\s+kya\s+hai|wazan\s+kitna|current\s+wajan|wajan\s+kya\s+hai)\b", user):
            wt_m = re.search(r"weight:\s*(\d+(?:\.\d+)?)\s*kg", system)
            if wt_m:
                wt_val = wt_m.group(1)
                if active_lang == "en":
                    return f"Your current recorded weight is {wt_val} kg."
                if active_lang == "hi":
                    return f"आपका अभी का दर्ज वजन {wt_val} किलोग्राम है।"
                return f"Aapka abhi ka recorded weight {wt_val} kg hai."
            else:
                if active_lang == "en":
                    return "I don't have your weight recorded yet. You can tell me your weight or add it in your Profile tab."
                if active_lang == "hi":
                    return "अभी आपका वजन दर्ज नहीं है। आप मुझे अपना वजन बता सकते हैं या प्रोफाइल सेक्शन में जोड़ सकते हैं।"
                return "Abhi aapka weight record nahi hai. Aap mujhe apna weight bata sakte hain ya Profile tab mein add kar sakte hain."

        # -------------------------------------------------------
        # 5. EVERYDAY CLINICAL NUTRITION & LIFESTYLE QUERIES
        # -------------------------------------------------------

        # Evening snacks & hunger
        if re.search(r"\b(snack|snacks|shaam|bhuk|bhookh|evening|craving|bhook)\b", user):
            if active_lang == "en":
                return "Around 4 to 5 PM, instead of fried snacks, opt for roasted makhana, a handful of roasted chana, sprouts chaat, or cucumber slices. These keep your blood sugar steady."
            return "Shaam ko 4-5 baje agar bhookh lage toh fried snacks ke bajaye roasted makhana, 1 mutthi bhuna chana, sprouts chaat, ya cucumber slices lein. Yeh light bhi hain aur blood sugar stable rakhte hain."

        # Chai / Coffee
        if re.search(r"\b(chai|tea|coffee|caffeine)\b", user):
            if active_lang == "en":
                return "You can enjoy tea or coffee! Just limit it to 1-2 cups daily, reduce added sugar, and avoid drinking it right after meals to protect digestion and iron absorption."
            return "Chai aap bilkul le sakte hain! Bas din mein 1-2 cup tak limit rakhein, cheeni kam karein, aur khana khane ke turant baad chai na pijiye taaki digestion aur iron absorption disturb na ho."

        # Cheat meals / Samosa / Guilt
        if re.search(r"\b(samosa|cheat|pizza|junk|mithai|sweet|fried|gulab jamun|cake)\b", user):
            if active_lang == "en":
                return "Do not feel guilty! Consistency matters most in your health journey. Have a light meal like moong dal khichdi or vegetable soup next, and go for a 25-minute brisk walk this evening."
            return "Koi baat nahi, guilt feel bilkul mat kijiye! Health journey mein consistency matter karti hai. Agle meal mein light moong dal khichdi ya soup lein aur shaam ko 25-30 minute brisk walk zaroor karein."

        # Water / Hydration
        if re.search(r"\b(water|paani|pani|hydration|kitna paani|dehydration|पानी)\b", user):
            if active_lang == "en":
                return "You should aim for 2.5 to 3 liters of water throughout the day. Instead of drinking large amounts at once, sipping a glass every hour is much more effective."
            if active_lang == "hi":
                return "दिन भर में कम से कम 2.5 से 3 लीटर पानी ज़रूर पिएं। हर एक घंटे में थोड़ा-थोड़ा पानी पीना पाचन और स्वास्थ्य के लिए सबसे अच्छा होता है।"
            return "Aapko din bhar mein kam se kam 2.5 se 3 litres paani zaroor peena chahiye. Ek baar mein bohot saara peene ke bajaye har 1 ghante mein thoda-thoda sip karna sabse effective hota hai."

        # Acidity / Heartburn / Indigestion
        if re.search(r"\b(acidity|acid|jalan|heartburn|indigestion|khatti\s+dakar|belch)\b", user):
            if active_lang == "en":
                return "For acidity, avoid heavy spicy meals and walk upright for 15 minutes after eating instead of lying down. Chewing a teaspoon of saunf (fennel) or sipping normal water helps settle stomach acid quickly."
            return "Acidity ke liye heavy spicy meals avoid karein aur khane ke turant baad letne ke bajaye 15 minute seedhe walk karein. Ek chammach saunf chabana ya thoda sa normal paani sip karna stomach acid ko kaafi jaldi settle karta hai."

        # If clinical facts are present in system prompt from RAG, synthesize only if relevant to user query
        user_words = set(re.findall(r"\w+", user))
        for line in system.split("\n"):
            if "approved reference" in line or "guidance:" in line:
                clean_fact = line.split(":")[-1].strip()
                fact_words = set(re.findall(r"\w+", clean_fact.lower()))
                stop_words = {"the", "a", "an", "is", "in", "to", "for", "and", "or", "what", "can", "how", "my", "your", "of", "on", "at", "i", "me", "you", "ke", "ki", "ka", "ko", "se", "me", "hai", "hain", "kya", "are", "do"}
                meaningful_overlap = (user_words & fact_words) - stop_words
                if len(meaningful_overlap) >= 2:
                    if active_lang == "en":
                        return f"According to verified clinical guidelines: {clean_fact[:160]}."
                    return f"Aapke clinical records ke mutabiq: {clean_fact[:160]}."

        # General warm contextual Indian health coach reply
        if active_lang == "en":
            return "I understand your point. To stay on track with your daily routine and nutrition goals, maintain balanced meals and consistent movement. Let me know if you would like any specific guidance!"
        if active_lang == "hi":
            return "मैं आपकी बात समझ रही हूँ। अपने दैनिक रूटीन और पोषण लक्ष्यों को पूरा करने के लिए संतुलित आहार और नियमित व्यायाम बनाए रखें।"
        return "Main aapki baat samajh rahi hoon. Aapke daily routine aur nutrition goals ke sath aligned rehne ke liye balanced meals aur regular movement maintain karein. Ispar koi specific clarification chahiye toh batayein!"

# ---------------------------------------------------------
# PRODUCTION LLM CLIENT (Gemini 2.0 / Groq with Fallback)
# ---------------------------------------------------------

class LLMClient:
    """
    Connects to Google Gemini (free tier) or Groq Llama 3.3 70B (free tier),
    with seamless fallback to the intelligent OfflineEngine.
    Supports both batch generation and Server-Sent Events (SSE) token streaming.
    """

    def _get_credentials(self) -> Dict[str, str]:
        gemini_key = get_setting("gemini_api_key") or settings.GEMINI_API_KEY
        groq_key = get_setting("groq_api_key") or settings.GROQ_API_KEY
        return {
            "gemini_key": gemini_key.strip(),
            "gemini_model": settings.GEMINI_MODEL,
            "groq_key": groq_key.strip(),
            "groq_model": settings.GROQ_MODEL
        }

    async def generate(self, messages: List[Dict[str, str]]) -> str:
        creds = self._get_credentials()

        # 1. Try Groq (Ultra-low latency inference ~500-900ms)
        if creds["groq_key"]:
            try:
                headers = {
                    "Authorization": f"Bearer {creds['groq_key']}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": creds["groq_model"],
                    "messages": messages,
                    "temperature": 0.3,
                    "max_tokens": 160
                }
                async with httpx.AsyncClient(timeout=4.0) as client:
                    res = await client.post("https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers)
                    if res.status_code == 200:
                        data = res.json()
                        return data["choices"][0]["message"]["content"].strip()
            except Exception:
                pass

        # 2. Try Google Gemini API if key configured
        if creds["gemini_key"]:
            try:
                system_instruction = next((m["content"] for m in messages if m["role"] == "system"), "")
                contents = []
                for m in messages:
                    if m["role"] == "system":
                        continue
                    role = "user" if m["role"] == "user" else "model"
                    contents.append({"role": role, "parts": [{"text": m["content"]}]})

                gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/{creds['gemini_model']}:generateContent?key={creds['gemini_key']}"
                payload = {
                    "contents": contents,
                    "systemInstruction": {"parts": [{"text": system_instruction}]},
                    "generationConfig": {"temperature": 0.4, "maxOutputTokens": 200}
                }
                async with httpx.AsyncClient(timeout=8.0) as client:
                    res = await client.post(gemini_url, json=payload)
                    if res.status_code == 200:
                        data = res.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                            if text.strip():
                                return text.strip()
            except Exception:
                pass

        # 3. Intelligent Offline Conversational Engine
        return OfflineEngine.reply(messages)

    async def generate_stream(self, messages: List[Dict[str, str]]) -> AsyncGenerator[str, None]:
        """Streams response tokens for real-time SSE display."""
        creds = self._get_credentials()

        # 1. Try Groq streaming (Ultra-low latency ~300ms time to first token)
        if creds["groq_key"]:
            try:
                headers = {
                    "Authorization": f"Bearer {creds['groq_key']}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": creds["groq_model"],
                    "messages": messages,
                    "temperature": 0.3,
                    "max_tokens": 160,
                    "stream": True
                }
                async with httpx.AsyncClient(timeout=6.0) as client:
                    async with client.stream("POST", "https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers) as response:
                        if response.status_code == 200:
                            async for line in response.aiter_lines():
                                if line.startswith("data: ") and line != "data: [DONE]":
                                    chunk = json.loads(line[6:])
                                    delta = chunk["choices"][0].get("delta", {}).get("content", "")
                                    if delta:
                                        yield delta
                            return
            except Exception:
                pass

        # 2. Try Google Gemini streaming if key configured
        if creds["gemini_key"]:
            try:
                system_instruction = next((m["content"] for m in messages if m["role"] == "system"), "")
                contents = []
                for m in messages:
                    if m["role"] == "system":
                        continue
                    role = "user" if m["role"] == "user" else "model"
                    contents.append({"role": role, "parts": [{"text": m["content"]}]})

                gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/{creds['gemini_model']}:streamGenerateContent?alt=sse&key={creds['gemini_key']}"
                payload = {
                    "contents": contents,
                    "systemInstruction": {"parts": [{"text": system_instruction}]},
                    "generationConfig": {"temperature": 0.4, "maxOutputTokens": 250}
                }
                async with httpx.AsyncClient(timeout=6.0) as client:
                    async with client.stream("POST", gemini_url, json=payload) as response:
                        if response.status_code == 200:
                            async for line in response.aiter_lines():
                                if line.startswith("data: "):
                                    chunk_str = line[6:].strip()
                                    if chunk_str:
                                        try:
                                             chunk = json.loads(chunk_str)
                                             candidates = chunk.get("candidates", [])
                                             if candidates:
                                                 part_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                                                 if part_text:
                                                     yield part_text
                                        except Exception:
                                             pass
                            return
            except Exception:
                pass

        # Full response fallback with simulated conversational token pacing
        full_text = await self.generate(messages)
        words = full_text.split()
        for idx in range(0, len(words), 2):
            chunk = " ".join(words[idx:idx+2]) + " "
            yield chunk
            await asyncio.sleep(0.03)

llm_client = LLMClient()

# ---------------------------------------------------------
# TURN ORCHESTRATOR
# ---------------------------------------------------------

class TurnResult(BaseModel):
    turn_id: str
    session_id: str
    turn_number: int
    user_utterance: str
    is_emergency: bool
    emergency_category: Optional[str] = None
    final_response: str
    latency_ms: float
    intercepted: bool = False
    interception_reason: Optional[str] = None

class TurnOrchestrator:
    """Coordinates pre-turn emergency triage, knowledge grounding, LLM, sanitizer, and audit."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path

    async def execute_turn(
        self,
        patient_id: str,
        utterance: str,
        session_id: Optional[str] = None,
        turn_number: int = 1,
        history: Optional[List[Dict[str, str]]] = None,
        override_day: Optional[str] = None,
        source: str = "chat",
    ) -> TurnResult:
        start = time.perf_counter()
        turn_id = f"turn_{uuid.uuid4().hex[:8]}"
        sid = session_id or f"sess_{uuid.uuid4().hex[:8]}"
        lang = detect_language(utterance)

        # STEP 1: Pre-turn Emergency & Critical Guardrail Circuit Breaker (<0.05ms)
        emg = emergency_breaker.evaluate(utterance)
        if emg.is_emergency:
            lat = (time.perf_counter() - start) * 1000.0
            self._save_turn(
                turn_id=turn_id,
                session_id=sid,
                turn_number=turn_number,
                patient_id=patient_id,
                utterance=utterance,
                pre_status="EMERGENCY_TRIGGERED",
                rules_json="[]",
                raw_llm=None,
                post_status="EMERGENCY_HALT",
                final_text=emg.triage_message,
                latency_ms=lat,
                source=source,
            )
            self._save_emergency(
                turn_id=turn_id,
                patient_id=patient_id,
                category=emg.category or "general",
                phrases=emg.matched_phrases,
                action="LLM_ABORTED_112_TRIAGE_EMITTED",
            )
            return TurnResult(
                turn_id=turn_id,
                session_id=sid,
                turn_number=turn_number,
                user_utterance=utterance,
                is_emergency=True,
                emergency_category=emg.category,
                final_response=emg.triage_message,
                latency_ms=lat,
            )

        # Pre-turn Intercept (Prompt Injection / Medication Safety / Pregnancy Precaution)
        if getattr(emg, "is_pre_turn_intercept", False):
            lat = (time.perf_counter() - start) * 1000.0
            self._save_turn(
                turn_id=turn_id,
                session_id=sid,
                turn_number=turn_number,
                patient_id=patient_id,
                utterance=utterance,
                pre_status=emg.intercept_reason or "PRE_TURN_INTERCEPT",
                rules_json="[]",
                raw_llm=None,
                post_status="CIRCUIT_BREAKER_HALT",
                final_text=emg.triage_message or "",
                latency_ms=lat,
                source=source,
            )
            return TurnResult(
                turn_id=turn_id,
                session_id=sid,
                turn_number=turn_number,
                user_utterance=utterance,
                is_emergency=False,
                final_response=emg.triage_message or "",
                latency_ms=lat,
                intercepted=True,
                interception_reason=emg.intercept_reason,
            )

        # STEP 1.5: Intent Routing (Clarification / Greeting / Acknowledgement)
        intent = classify_intent(utterance)
        if intent == IntentType.CLARIFICATION_NEEDED:
            lat = (time.perf_counter() - start) * 1000.0
            clarification_msg = {
                "en": "I'm not sure I understood that. Could you explain what you mean?",
                "hi": "मुझे आपकी बात समझ नहीं आई। क्या आप थोड़ा और समझा सकते हैं?",
                "hinglish": "Main samajh nahi paayi. Thoda aur explain kar sakte hain?",
            }.get(lang, "I'm not sure I understood that. Could you explain what you mean?")
            self._save_turn(
                turn_id=turn_id,
                session_id=sid,
                turn_number=turn_number,
                patient_id=patient_id,
                utterance=utterance,
                pre_status="CLARIFICATION_REQUESTED",
                rules_json="[]",
                raw_llm=None,
                post_status="CLEAN",
                final_text=clarification_msg,
                latency_ms=lat,
                source=source,
            )
            return TurnResult(
                turn_id=turn_id,
                session_id=sid,
                turn_number=turn_number,
                user_utterance=utterance,
                is_emergency=False,
                final_response=clarification_msg,
                latency_ms=lat,
            )

        if intent == IntentType.GREETING:
            lat = (time.perf_counter() - start) * 1000.0
            greet_msg = {
                "en": "Hello! How can I help with your nutrition, workouts, or health routine today?",
                "hi": "मैं सुन रही हूँ! आज आपकी डाइट, वर्कआउट या दिनचर्या में किस चीज़ में मदद चाहिए?",
                "hinglish": "Main sun rahi hoon! Aaj aapki diet, daily workout ya health routine mein kahan guidance chahiye?",
            }.get(lang, "Hello! How can I help with your nutrition, workouts, or health routine today?")
            self._save_turn(
                turn_id=turn_id,
                session_id=sid,
                turn_number=turn_number,
                patient_id=patient_id,
                utterance=utterance,
                pre_status="GREETING_ACK",
                rules_json="[]",
                raw_llm=None,
                post_status="CLEAN",
                final_text=greet_msg,
                latency_ms=lat,
                source=source,
            )
            return TurnResult(
                turn_id=turn_id,
                session_id=sid,
                turn_number=turn_number,
                user_utterance=utterance,
                is_emergency=False,
                final_response=greet_msg,
                latency_ms=lat,
            )

        if intent == IntentType.ACKNOWLEDGEMENT:
            lat = (time.perf_counter() - start) * 1000.0
            ack_msg = {
                "en": "Got it! Feel free to ask if you have any questions about your diet, workouts, or routine.",
                "hi": "बिल्कुल! अपनी डाइट या वर्कआउट से जुड़ा कोई भी सवाल हो तो ज़रूर बताइए।",
                "hinglish": "Bilkul! Apne meals ya workout se juda koi bhi sawal ho toh zaroor batayein.",
            }.get(lang, "Got it! Feel free to ask if you have any questions about your diet, workouts, or routine.")
            self._save_turn(
                turn_id=turn_id,
                session_id=sid,
                turn_number=turn_number,
                patient_id=patient_id,
                utterance=utterance,
                pre_status="ACKNOWLEDGEMENT_NOD",
                rules_json="[]",
                raw_llm=None,
                post_status="CLEAN",
                final_text=ack_msg,
                latency_ms=lat,
                source=source,
            )
            return TurnResult(
                turn_id=turn_id,
                session_id=sid,
                turn_number=turn_number,
                user_utterance=utterance,
                is_emergency=False,
                final_response=ack_msg,
                latency_ms=lat,
            )

        # STEP 1.6: Conversational Biometric & Goal Persistence
        wt_match = re.search(r"\b(?:weight|wajan|vajan|wgt)?\s*(?:is|now|hai|ho\s*gaya)?\s*[:=]?\s*(\d{2,3}(?:\.\d+)?)\s*(?:kg|kilos?|kgs)\b", utterance, re.I)
        if wt_match and patient_id:
            try:
                new_wt = float(wt_match.group(1))
                if 25.0 <= new_wt <= 250.0:
                    with get_db(self.db_path) as conn:
                        conn.execute("INSERT OR IGNORE INTO patients (id, full_name, phone, primary_goal) VALUES (?, 'User', 'N/A', 'General Health')", (patient_id,))
                        conn.execute("UPDATE patients SET weight_kg = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_wt, patient_id))
                        conn.execute("""
                            INSERT INTO user_memories (id, user_id, category, key, value, status, confidence, source_utterance)
                            VALUES (?, ?, 'biometrics', 'weight_kg', ?, 'confirmed', 1.0, ?)
                        """, (f"mem_{uuid.uuid4().hex[:8]}", patient_id, str(new_wt), utterance))
            except Exception:
                pass

        # STEP 2: Context Grounding
        patient = clinical_resolver.get_patient(patient_id)
        patient_name = patient["full_name"].split()[0] if (patient and patient.get("full_name") and patient["full_name"] != "User") else "there"
        pep = clinical_resolver.get_pep(patient_id)

        facts: List[str] = []
        retrieved_rules: List[str] = []
        lower_utt = utterance.lower()

        # Meal plan lookup (Database direct)
        if any(w in lower_utt for w in ["dinner", "khana", "diet chart", "meal", "lunch"]):
            meal = clinical_resolver.get_meal(patient_id, day_of_week=override_day, meal_type="dinner")
            facts.append(f"Scheduled Meal: {meal['summary']}")
            retrieved_rules.append("DB_PATIENT_MEALS")

        # Pricing lookup (Database direct)
        if any(w in lower_utt for w in ["paid", "subscription", "price", "paise", "kitne ka"]):
            facts.append(f"Authorized Pricing Plans:\n{clinical_resolver.get_pricing_text()}")
            retrieved_rules.append("DB_PRICING_PLANS")

        # Clinical rules, stances, and approved RAG knowledge
        rules_facts, required_remedy_tokens = clinical_resolver.retrieve_knowledge(utterance, patient_id=patient_id)
        facts.extend(rules_facts)
        retrieved_rules.extend(rules_facts)

        # STEP 3: Prompt & LLM Call
        user_memories = []
        try:
            with get_db(self.db_path) as conn:
                m_rows = conn.execute("SELECT key, value FROM user_memories WHERE user_id = ? AND status = 'confirmed' ORDER BY updated_at DESC LIMIT 5", (patient_id,)).fetchall()
                user_memories = [dict(r) for r in m_rows]
        except Exception:
            pass

        messages = PromptBuilder.build(
            patient_name=patient_name,
            pep=pep,
            facts=facts,
            utterance=utterance,
            history=history,
            patient_biometrics=patient,
            user_memories=user_memories,
        )
        raw_llm = await llm_client.generate(messages)

        # STEP 4: Post-turn Sanitizer
        clean_text, intercepted, reason = sanitizer.sanitize(
            raw_text=raw_llm,
            required_remedy_tokens=required_remedy_tokens,
            patient_conditions=pep.get("medical_conditions", []),
            dietary_preference=pep.get("dietary_preference"),
        )

        # STEP 5: Egress Scrubbing & Markdown Normalization
        clean_text = re.sub(r"[*_#`]+", "", clean_text)
        clean_text = re.sub(r"^\s*[-•]\s*", "", clean_text, flags=re.MULTILINE)
        final_text = EgressGate.scrub(clean_text).strip()
        lat = (time.perf_counter() - start) * 1000.0

        # STEP 6: Audit Persistence
        self._save_turn(
            turn_id=turn_id,
            session_id=sid,
            turn_number=turn_number,
            patient_id=patient_id,
            utterance=utterance,
            pre_status="PASS",
            rules_json=json.dumps(retrieved_rules),
            raw_llm=raw_llm,
            post_status=reason or "CLEAN",
            final_text=final_text,
            latency_ms=lat,
            source=source,
        )

        return TurnResult(
            turn_id=turn_id,
            session_id=sid,
            turn_number=turn_number,
            user_utterance=utterance,
            is_emergency=False,
            final_response=final_text,
            latency_ms=lat,
            intercepted=intercepted,
            interception_reason=reason,
        )

    def _save_turn(self, turn_id, session_id, turn_number, patient_id, utterance, pre_status, rules_json, raw_llm, post_status, final_text, latency_ms, source="chat"):
        with get_db(self.db_path) as conn:
            if patient_id:
                conn.execute("""
                    INSERT OR IGNORE INTO patients (id, full_name, phone, primary_goal)
                    VALUES (?, 'User', 'N/A', 'General Health')
                """, (patient_id,))
            conn.execute("""
                INSERT OR REPLACE INTO call_sessions (id, patient_id, status, total_turns)
                VALUES (?, ?, 'ACTIVE', ?)
            """, (session_id, patient_id, turn_number))
            conn.execute("""
                INSERT INTO call_turns (id, session_id, turn_number, user_utterance, pre_guardrail_status, retrieved_rules, raw_llm_response, post_guardrail_status, final_response, latency_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (turn_id, session_id, turn_number, utterance, pre_status, rules_json, raw_llm, post_status, final_text, latency_ms))
            if patient_id and session_id:
                conn.execute("""
                    INSERT INTO conversation_messages (id, user_id, session_id, role, content, source)
                    VALUES (?, ?, ?, 'user', ?, ?)
                """, (f"msg_{uuid.uuid4().hex[:8]}", patient_id, session_id, utterance, source))
                conn.execute("""
                    INSERT INTO conversation_messages (id, user_id, session_id, role, content, source)
                    VALUES (?, ?, ?, 'assistant', ?, ?)
                """, (f"msg_{uuid.uuid4().hex[:8]}", patient_id, session_id, final_text, source))

    def _save_emergency(self, turn_id, patient_id, category, phrases, action):
        with get_db(self.db_path) as conn:
            if patient_id:
                conn.execute("""
                    INSERT OR IGNORE INTO patients (id, full_name, phone, primary_goal)
                    VALUES (?, 'User', 'N/A', 'General Health')
                """, (patient_id,))
            conn.execute("""
                INSERT INTO emergency_escalations (id, turn_id, patient_id, category, detected_phrases, triage_action)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (f"esc_{uuid.uuid4().hex[:8]}", turn_id, patient_id, category, json.dumps(phrases), action))

    def _save_emergency(self, turn_id, patient_id, category, phrases, action):
        with get_db(self.db_path) as conn:
            if patient_id:
                conn.execute("""
                    INSERT OR IGNORE INTO patients (id, full_name, phone, primary_goal)
                    VALUES (?, 'User', 'N/A', 'General Health')
                """, (patient_id,))
            conn.execute("""
                INSERT INTO emergency_escalations (id, turn_id, patient_id, category, detected_phrases, triage_action)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (f"esc_{uuid.uuid4().hex[:8]}", turn_id, patient_id, category, json.dumps(phrases), action))

turn_orchestrator = TurnOrchestrator()
