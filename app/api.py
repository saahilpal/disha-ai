import json
import base64
import time
import re
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from app.config import settings
from app.db import get_connection, get_db, get_setting, set_setting
from app.engine import (
    turn_orchestrator,
    TurnResult,
    PromptBuilder,
    llm_client,
    detect_language,
    classify_intent,
    IntentType,
)
from app.clinical import clinical_resolver
from app.guardrails import emergency_breaker, sanitizer, EgressGate
from app.voice import tts, stt, ContextSynchronizer
from app.rag.manager import document_manager
from app.rag.retriever import hybrid_retriever

router = APIRouter()

# ---------------------------------------------------------
# PYDANTIC SCHEMAS
# ---------------------------------------------------------

class ChatRequest(BaseModel):
    patient_id: Optional[str] = None
    utterance: str
    session_id: Optional[str] = None
    turn_number: int = 1
    history: Optional[List[Dict[str, str]]] = None
    override_day: Optional[str] = None

class PatientCreateRequest(BaseModel):
    full_name: str
    age: Optional[int] = 32
    gender: Optional[str] = "Female"
    height_cm: Optional[float] = 165.0
    weight_kg: Optional[float] = 62.0
    activity_level: Optional[str] = "Moderate"
    primary_goal: str = "Weight management and healthy habits"
    medical_conditions: Optional[List[str]] = []
    dietary_preference: Optional[str] = "Vegetarian"
    allowed_exercise: Optional[List[str]] = ["Walking", "Home", "Gym"]
    phone: Optional[str] = "+919876543210"

class PatientUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    activity_level: Optional[str] = None
    primary_goal: Optional[str] = None
    medical_conditions: Optional[List[str]] = None
    dietary_preference: Optional[str] = None
    allowed_exercise: Optional[List[str]] = None
    phone: Optional[str] = None

class TranscribeRequest(BaseModel):
    audio_base64: str
    filename: Optional[str] = "audio.webm"

class VoiceTurnRequest(BaseModel):
    patient_id: Optional[str] = None
    utterance: Optional[str] = None
    audio_base64: Optional[str] = None
    session_id: Optional[str] = None
    turn_number: int = 1
    history: Optional[List[Dict[str, str]]] = None

class SynthesizeRequest(BaseModel):
    text: str

class RuleCreateRequest(BaseModel):
    rule_code: str
    category: str
    trigger_keywords: List[str]
    trigger_pattern: str
    clinical_remedy: str
    author_name: str
    severity: Optional[str] = "mandatory"

class RuleTestRequest(BaseModel):
    test_utterance: str
    pattern: str
    keywords: Optional[List[str]] = []

class DocumentUploadRequest(BaseModel):
    title: str
    filename: str
    file_type: str = "txt"
    category: str = "clinical_guideline"
    content_text: Optional[str] = None
    content_base64: Optional[str] = None
    author: str = "Clinician"
    patient_id: Optional[str] = None
    auto_approve: bool = False

class RAGQueryRequest(BaseModel):
    query: str
    patient_id: Optional[str] = None
    category: Optional[str] = None
    top_k: int = 3

class SettingsUpdateRequest(BaseModel):
    gemini_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None

# ---------------------------------------------------------
# REST ENDPOINTS
# ---------------------------------------------------------

@router.get("/health")
def health_check():
    """System health check verifying database and engine readiness."""
    db_ok = False
    try:
        conn = get_connection()
        db_ok = bool(conn.execute("SELECT 1").fetchone())
        conn.close()
    except Exception:
        db_ok = False

    gemini_k = get_setting("gemini_api_key") or settings.GEMINI_API_KEY
    groq_k = get_setting("groq_api_key") or settings.GROQ_API_KEY
    active_provider = "Google Gemini" if gemini_k else ("Groq Llama 3.3" if groq_k else "Offline Conversational Engine")

    return {
        "status": "healthy" if db_ok else "degraded",
        "database_connected": db_ok,
        "llm_provider": active_provider,
        "tts_voice": settings.TTS_VOICE,
    }

@router.get("/settings")
def get_app_settings():
    """Returns active AI model configuration and masked credentials."""
    gemini_k = get_setting("gemini_api_key") or settings.GEMINI_API_KEY
    groq_k = get_setting("groq_api_key") or settings.GROQ_API_KEY
    active_provider = "Google Gemini (gemini-2.0-flash)" if gemini_k else ("Groq (llama-3.3-70b-versatile)" if groq_k else "Offline Conversational Engine")
    return {
        "active_provider": active_provider,
        "has_gemini": bool(gemini_k),
        "has_groq": bool(groq_k),
        "gemini_key_masked": gemini_k[:6] + "..." + gemini_k[-4:] if len(gemini_k) > 10 else "",
        "groq_key_masked": groq_k[:6] + "..." + groq_k[-4:] if len(groq_k) > 10 else "",
    }

@router.post("/settings")
def update_app_settings(req: SettingsUpdateRequest):
    """Allows user/developer to configure free Gemini or Groq API keys directly from the UI."""
    if req.gemini_api_key is not None:
        set_setting("gemini_api_key", req.gemini_api_key.strip())
    if req.groq_api_key is not None:
        set_setting("groq_api_key", req.groq_api_key.strip())
    return {"status": "success"}

@router.post("/chat", response_model=TurnResult)
async def chat_endpoint(req: ChatRequest):
    """Processes a text chat turn with clinical grounding and safety guardrails."""
    if not req.utterance or not req.utterance.strip():
        raise HTTPException(status_code=400, detail="Utterance cannot be empty")
    
    patient_id = req.patient_id or f"pt_{uuid.uuid4().hex[:8]}"
    return await turn_orchestrator.execute_turn(
        patient_id=patient_id,
        utterance=req.utterance,
        session_id=req.session_id,
        turn_number=req.turn_number,
        history=req.history,
        override_day=req.override_day,
        source="chat",
    )

@router.post("/chat/stream")
async def chat_stream_endpoint(req: ChatRequest):
    """
    Streams conversational tokens over Server-Sent Events (SSE).
    Provides real-time interactive typing experience with clinical grounding and persistent audit.
    """
    if not req.utterance or not req.utterance.strip():
        raise HTTPException(status_code=400, detail="Utterance cannot be empty")

    patient_id = req.patient_id or f"pt_{uuid.uuid4().hex[:8]}"
    session_id = req.session_id or f"sess_{uuid.uuid4().hex[:8]}"
    turn_id = f"turn_{uuid.uuid4().hex[:8]}"
    start_time = time.perf_counter()
    active_lang = detect_language(req.utterance)

    async def event_generator():
        # 1. Pre-turn emergency check (<0.05ms)
        emg = emergency_breaker.evaluate(req.utterance)
        if emg.is_emergency:
            lat = (time.perf_counter() - start_time) * 1000.0
            turn_orchestrator._save_turn(
                turn_id=turn_id,
                session_id=session_id,
                turn_number=req.turn_number,
                patient_id=patient_id,
                utterance=req.utterance,
                pre_status="EMERGENCY_TRIGGERED",
                rules_json="[]",
                raw_llm=None,
                post_status="EMERGENCY_HALT",
                final_text=emg.triage_message,
                latency_ms=lat,
                source="chat",
            )
            turn_orchestrator._save_emergency(
                turn_id=turn_id,
                patient_id=patient_id,
                category=emg.category or "general",
                phrases=emg.matched_phrases,
                action="LLM_ABORTED_112_TRIAGE_EMITTED",
            )
            yield f"data: {json.dumps({'type': 'emergency', 'text': emg.triage_message})}\n\n"
            yield f"data: [DONE]\n\n"
            return

        if getattr(emg, "is_pre_turn_intercept", False):
            lat = (time.perf_counter() - start_time) * 1000.0
            turn_orchestrator._save_turn(
                turn_id=turn_id,
                session_id=session_id,
                turn_number=req.turn_number,
                patient_id=patient_id,
                utterance=req.utterance,
                pre_status=emg.intercept_reason or "PRE_TURN_INTERCEPT",
                rules_json="[]",
                raw_llm=None,
                post_status="CIRCUIT_BREAKER_HALT",
                final_text=emg.triage_message or "",
                latency_ms=lat,
                source="chat",
            )
            yield f"data: {json.dumps({'type': 'token', 'token': emg.triage_message})}\n\n"
            yield f"data: [DONE]\n\n"
            return

        # 2. Intent Routing (Clarification / Greeting / Acknowledgement)
        intent = classify_intent(req.utterance)
        if intent == IntentType.CLARIFICATION_NEEDED:
            clarification_msg = {
                "en": "I'm not sure I understood that. Could you explain what you mean?",
                "hi": "मुझे आपकी बात समझ नहीं आई। क्या आप थोड़ा और समझा सकते हैं?",
                "hinglish": "Main samajh nahi paayi. Thoda aur explain kar sakte hain?",
            }.get(active_lang, "I'm not sure I understood that. Could you explain what you mean?")
            lat = (time.perf_counter() - start_time) * 1000.0
            turn_orchestrator._save_turn(
                turn_id=turn_id,
                session_id=session_id,
                turn_number=req.turn_number,
                patient_id=patient_id,
                utterance=req.utterance,
                pre_status="CLARIFICATION_REQUESTED",
                rules_json="[]",
                raw_llm=None,
                post_status="CLEAN",
                final_text=clarification_msg,
                latency_ms=lat,
                source="chat",
            )
            yield f"data: {json.dumps({'type': 'token', 'token': clarification_msg})}\n\n"
            yield f"data: [DONE]\n\n"
            return

        if intent == IntentType.GREETING:
            greet_msg = {
                "en": "Hello! How can I help with your nutrition, workouts, or health routine today?",
                "hi": "मैं सुन रही हूँ! आज आपकी डाइट, वर्कआउट या दिनचर्या में किस चीज़ में मदद चाहिए?",
                "hinglish": "Main sun rahi hoon! Aaj aapki diet, daily workout ya health routine mein kahan guidance chahiye?",
            }.get(active_lang, "Hello! How can I help with your nutrition, workouts, or health routine today?")
            lat = (time.perf_counter() - start_time) * 1000.0
            turn_orchestrator._save_turn(
                turn_id=turn_id,
                session_id=session_id,
                turn_number=req.turn_number,
                patient_id=patient_id,
                utterance=req.utterance,
                pre_status="GREETING_ACK",
                rules_json="[]",
                raw_llm=None,
                post_status="CLEAN",
                final_text=greet_msg,
                latency_ms=lat,
                source="chat",
            )
            yield f"data: {json.dumps({'type': 'token', 'token': greet_msg})}\n\n"
            yield f"data: [DONE]\n\n"
            return

        if intent == IntentType.ACKNOWLEDGEMENT:
            ack_msg = {
                "en": "Got it! Feel free to ask if you have any questions about your diet, workouts, or routine.",
                "hi": "बिल्कुल! अपनी डाइट या वर्कआउट से जुड़ा कोई भी सवाल हो तो ज़रूर बताइए।",
                "hinglish": "Bilkul! Apne meals ya workout se juda koi bhi sawal ho toh zaroor batayein.",
            }.get(active_lang, "Got it! Feel free to ask if you have any questions about your diet, workouts, or routine.")
            lat = (time.perf_counter() - start_time) * 1000.0
            turn_orchestrator._save_turn(
                turn_id=turn_id,
                session_id=session_id,
                turn_number=req.turn_number,
                patient_id=patient_id,
                utterance=req.utterance,
                pre_status="ACKNOWLEDGEMENT_NOD",
                rules_json="[]",
                raw_llm=None,
                post_status="CLEAN",
                final_text=ack_msg,
                latency_ms=lat,
                source="chat",
            )
            yield f"data: {json.dumps({'type': 'token', 'token': ack_msg})}\n\n"
            yield f"data: [DONE]\n\n"
            return

        # 3. Conversational Biometric & Goal Persistence
        wt_match = re.search(r"\b(?:weight|wajan|vajan|wgt)?\s*(?:is|now|hai|ho\s*gaya)?\s*[:=]?\s*(\d{2,3}(?:\.\d+)?)\s*(?:kg|kilos?|kgs)\b", req.utterance, re.I)
        if wt_match and patient_id:
            try:
                new_wt = float(wt_match.group(1))
                if 25.0 <= new_wt <= 250.0:
                    with get_db() as conn:
                        conn.execute("UPDATE patients SET weight_kg = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_wt, patient_id))
                        conn.execute("""
                            INSERT INTO user_memories (id, user_id, category, key, value, status, confidence, source_utterance)
                            VALUES (?, ?, 'biometrics', 'weight_kg', ?, 'confirmed', 1.0, ?)
                        """, (f"mem_{uuid.uuid4().hex[:8]}", patient_id, str(new_wt), req.utterance))
            except Exception:
                pass

        # 4. Context Grounding
        patient = clinical_resolver.get_patient(patient_id)
        patient_name = patient["full_name"].split()[0] if (patient and patient.get("full_name") and patient["full_name"] != "User") else "there"
        pep = clinical_resolver.get_pep(patient_id)

        facts: List[str] = []
        retrieved_rules: List[str] = []
        lower_utt = req.utterance.lower()

        if any(w in lower_utt for w in ["dinner", "khana", "diet chart", "meal", "lunch"]):
            meal = clinical_resolver.get_meal(patient_id, day_of_week=req.override_day, meal_type="dinner")
            facts.append(f"Scheduled Meal: {meal['summary']}")
            retrieved_rules.append("DB_PATIENT_MEALS")

        if any(w in lower_utt for w in ["paid", "subscription", "price", "paise", "kitne ka"]):
            facts.append(f"Authorized Pricing Plans:\n{clinical_resolver.get_pricing_text()}")
            retrieved_rules.append("DB_PRICING_PLANS")

        rules_facts, required_remedy_tokens = clinical_resolver.retrieve_knowledge(req.utterance, patient_id=patient_id)
        facts.extend(rules_facts)
        retrieved_rules.extend(rules_facts)

        messages = PromptBuilder.build(
            patient_name=patient_name,
            pep=pep,
            facts=facts,
            utterance=req.utterance,
            history=req.history,
            patient_biometrics=patient,
        )

        accumulated = ""
        async for token in llm_client.generate_stream(messages):
            accumulated += token
            yield f"data: {json.dumps({'type': 'token', 'token': token})}\n\n"

        # 5. Post-turn sanitizer check on final output
        clean_text, intercepted, reason = sanitizer.sanitize(
            raw_text=accumulated,
            required_remedy_tokens=required_remedy_tokens,
            patient_conditions=pep.get("medical_conditions", []),
            dietary_preference=pep.get("dietary_preference"),
        )
        clean_text = re.sub(r"[*_#`]+", "", clean_text)
        clean_text = re.sub(r"^\s*[-•]\s*", "", clean_text, flags=re.MULTILINE)
        final_text = EgressGate.scrub(clean_text).strip()

        if final_text.strip() != accumulated.strip():
            yield f"data: {json.dumps({'type': 'replace_all', 'text': final_text})}\n\n"

        lat = (time.perf_counter() - start_time) * 1000.0

        # 6. Save Turn to Database (so chat history is immediately persistent)
        turn_orchestrator._save_turn(
            turn_id=turn_id,
            session_id=session_id,
            turn_number=req.turn_number,
            patient_id=patient_id,
            utterance=req.utterance,
            pre_status="PASS",
            rules_json=json.dumps(retrieved_rules),
            raw_llm=accumulated,
            post_status=reason or "CLEAN",
            final_text=final_text,
            latency_ms=lat,
            source="chat",
        )

        yield f"data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.post("/synthesize")
async def synthesize_endpoint(req: SynthesizeRequest):
    """Synthesizes text to MP3 audio for client playback."""
    audio_bytes = await tts.synthesize(req.text)
    return Response(content=audio_bytes, media_type="audio/mpeg")

@router.get("/patient/{patient_id}")
def get_patient_profile(patient_id: str):
    """Returns patient profile, PEP constraints, and scheduled weekly meals."""
    patient = clinical_resolver.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    pep = clinical_resolver.get_pep(patient_id)
    conn = get_connection()
    meals = conn.execute("SELECT day_of_week, meal_type, meal_name, items_description, calories FROM patient_meals WHERE patient_id = ?", (patient_id,)).fetchall()
    conn.close()

    return {
        "patient": patient,
        "pep": pep,
        "meals": [dict(m) for m in meals],
    }

@router.get("/conversations/{patient_id}")
def get_conversation_history(patient_id: str, session_id: Optional[str] = None):
    """Retrieves persistent message history for a user across chat and voice."""
    conn = get_connection()
    if session_id:
        rows = conn.execute("""
            SELECT id, user_id, session_id, role, content, source, created_at
            FROM conversation_messages
            WHERE user_id = ? AND session_id = ?
            ORDER BY created_at ASC
        """, (patient_id, session_id)).fetchall()
    else:
        rows = conn.execute("""
            SELECT id, user_id, session_id, role, content, source, created_at
            FROM conversation_messages
            WHERE user_id = ?
            ORDER BY created_at ASC
        """, (patient_id,)).fetchall()
    conn.close()
    return {
        "patient_id": patient_id,
        "count": len(rows),
        "messages": [dict(r) for r in rows]
    }

@router.delete("/conversations/{patient_id}")
def clear_conversation_history(patient_id: str):
    """Clears conversation messages for a fresh clean chat session."""
    with get_db() as conn:
        conn.execute("DELETE FROM conversation_messages WHERE user_id = ?", (patient_id,))
    return {"status": "success", "message": "Conversation history cleared"}

@router.post("/patient")
def create_patient_profile(req: PatientCreateRequest):
    """Creates a new patient profile and PEP plan during onboarding."""
    import uuid
    patient_id = f"pt_{uuid.uuid4().hex[:6]}"
    
    with get_db() as conn:
        # 1. Insert patient record
        conn.execute("""
            INSERT OR REPLACE INTO patients (id, full_name, phone, age, gender, height_cm, weight_kg, activity_level, primary_goal)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            patient_id,
            req.full_name,
            req.phone or "+919876543210",
            req.age or 30,
            req.gender or "Prefer not to say",
            req.height_cm,
            req.weight_kg,
            req.activity_level or "Moderate",
            req.primary_goal or "Healthy habit building"
        ))

        # 2. Insert PEP record
        conn.execute("""
            INSERT OR REPLACE INTO patient_pep (patient_id, allowed_exercise, target_activity, dietary_preference, medical_conditions, emergency_contact_phone)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            patient_id,
            json.dumps(req.allowed_exercise or ["Walking", "Home", "Gym"]),
            f"Active daily routine: {req.activity_level or 'Moderate'} exercise",
            req.dietary_preference or "Vegetarian",
            json.dumps(req.medical_conditions or []),
            "+919876543211"
        ))

        # 3. Populate personalized 7-day meal plan based on diet preference
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        diet = (req.dietary_preference or "Vegetarian").lower()
        
        if "non-veg" in diet:
            dinner_name = "Lean Protein Dinner"
            dinner_desc = "150g grilled chicken/fish, 1 cup quinoa or 2 rotis, steamed vegetables"
            dinner_cal = 450
            lunch_name = "Wholesome Protein Lunch"
            lunch_desc = "Egg bhurji or chicken curry with brown rice and cucumber salad"
            lunch_cal = 490
        elif "vegan" in diet:
            dinner_name = "Plant-Based Balanced Dinner"
            dinner_desc = "150g spiced tofu, 1 cup yellow dal tadka, 2 multigrain rotis, green salad"
            dinner_cal = 420
            lunch_name = "High-Fiber Vegan Lunch"
            lunch_desc = "Chickpea chana masala, brown rice, sautéed spinach and cucumber"
            lunch_cal = 460
        else:
            dinner_name = "High-Protein Balanced Dinner"
            dinner_desc = "150g paneer bhurji, 2 multigrain rotis, cucumber salad"
            dinner_cal = 420
            lunch_name = "Wholesome Dal & Sabzi"
            lunch_desc = "1 bowl moong dal tadka, 1 cup brown rice, mix veg sabzi, curd"
            lunch_cal = 480

        for day in days:
            conn.execute("""
                INSERT OR REPLACE INTO patient_meals (id, patient_id, day_of_week, meal_type, meal_name, items_description, calories)
                VALUES (?, ?, ?, 'dinner', ?, ?, ?)
            """, (f"meal_din_{patient_id}_{day}", patient_id, day, dinner_name, dinner_desc, dinner_cal))
            conn.execute("""
                INSERT OR REPLACE INTO patient_meals (id, patient_id, day_of_week, meal_type, meal_name, items_description, calories)
                VALUES (?, ?, ?, 'lunch', ?, ?, ?)
            """, (f"meal_lun_{patient_id}_{day}", patient_id, day, lunch_name, lunch_desc, lunch_cal))
            conn.execute("""
                INSERT OR REPLACE INTO patient_meals (id, patient_id, day_of_week, meal_type, meal_name, items_description, calories)
                VALUES (?, ?, ?, 'breakfast', 'Nourishing Breakfast', 'Besan chilla or vegetable oats with green tea', 320)
            """, (f"meal_bf_{patient_id}_{day}", patient_id, day))

    patient = clinical_resolver.get_patient(patient_id)
    pep = clinical_resolver.get_pep(patient_id)
    return {
        "status": "success",
        "patient_id": patient_id,
        "patient": patient,
        "pep": pep
    }

@router.put("/patient/{patient_id}")
def update_patient_profile(patient_id: str, req: PatientUpdateRequest):
    """Updates an existing patient's profile and PEP constraints."""
    current_patient = clinical_resolver.get_patient(patient_id)
    if not current_patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    current_pep = clinical_resolver.get_pep(patient_id)
    
    updated_name = req.full_name if req.full_name is not None else current_patient["full_name"]
    updated_age = req.age if req.age is not None else current_patient["age"]
    updated_gender = req.gender if req.gender is not None else current_patient.get("gender")
    updated_height = req.height_cm if req.height_cm is not None else current_patient.get("height_cm")
    updated_weight = req.weight_kg if req.weight_kg is not None else current_patient.get("weight_kg")
    updated_activity = req.activity_level if req.activity_level is not None else current_patient.get("activity_level")
    updated_goal = req.primary_goal if req.primary_goal is not None else current_patient["primary_goal"]

    with get_db() as conn:
        conn.execute("""
            UPDATE patients
            SET full_name = ?, age = ?, gender = ?, height_cm = ?, weight_kg = ?, activity_level = ?, primary_goal = ?
            WHERE id = ?
        """, (
            updated_name,
            updated_age,
            updated_gender,
            updated_height,
            updated_weight,
            updated_activity,
            updated_goal,
            patient_id
        ))

        # Update PEP fields if supplied
        if req.allowed_exercise is not None or req.dietary_preference is not None or req.medical_conditions is not None:
            new_allowed = json.dumps(req.allowed_exercise) if req.allowed_exercise is not None else json.dumps(current_pep.get("allowed_exercise", []))
            new_diet = req.dietary_preference if req.dietary_preference is not None else current_pep.get("dietary_preference", "Vegetarian")
            new_conditions = json.dumps(req.medical_conditions) if req.medical_conditions is not None else json.dumps(current_pep.get("medical_conditions", []))

            conn.execute("""
                UPDATE patient_pep
                SET allowed_exercise = ?, dietary_preference = ?, medical_conditions = ?
                WHERE patient_id = ?
            """, (new_allowed, new_diet, new_conditions, patient_id))

    return {
        "status": "success",
        "patient": clinical_resolver.get_patient(patient_id),
        "pep": clinical_resolver.get_pep(patient_id)
    }

@router.post("/transcribe")
async def transcribe_endpoint(req: TranscribeRequest):
    """Transcribes client recorded audio into text using Groq Whisper STT."""
    try:
        audio_bytes = base64.b64decode(req.audio_base64)
        text = await stt.transcribe(audio_bytes, filename=req.filename or "audio.webm")
        return {"status": "success", "text": text}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Transcription failed: {str(e)}")

@router.post("/voice-turn")
async def voice_turn_endpoint(req: VoiceTurnRequest):
    """
    Executes a complete voice turn:
    Accepts speech audio or text, executes clinical turn through Thick Spine,
    and returns text + synthesized audio bytes.
    """
    patient_id = req.patient_id or f"pt_{uuid.uuid4().hex[:8]}"
    session_id = req.session_id or f"sess_{uuid.uuid4().hex[:8]}"
    user_text = req.utterance or ""
    if not user_text and req.audio_base64:
        try:
            audio_bytes = base64.b64decode(req.audio_base64)
            user_text = await stt.transcribe(audio_bytes, filename="audio.webm")
        except Exception:
            user_text = ""

    if not user_text.strip():
        raise HTTPException(status_code=400, detail="Could not capture audio or text utterance.")

    turn_res = await turn_orchestrator.execute_turn(
        patient_id=patient_id,
        utterance=user_text,
        session_id=session_id,
        turn_number=req.turn_number,
        history=req.history,
        source="voice",
    )

    audio_b64 = ""
    try:
        audio_bytes = await tts.synthesize(turn_res.final_response)
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
    except Exception:
        pass

    return {
        "turn_id": turn_res.turn_id,
        "session_id": turn_res.session_id,
        "turn_number": turn_res.turn_number,
        "user_utterance": user_text,
        "user_transcript": user_text,
        "final_response": turn_res.final_response,
        "bot_response": turn_res.final_response,
        "is_emergency": turn_res.is_emergency,
        "emergency_category": turn_res.emergency_category,
        "latency_ms": turn_res.latency_ms,
        "intercepted": turn_res.intercepted,
        "interception_reason": turn_res.interception_reason,
        "audio_base64": audio_b64
    }

@router.get("/rules")
def get_clinical_rules():
    """Returns all doctor-authored rules, version audit history, stances, and pricing."""
    conn = get_connection()
    rules = conn.execute("SELECT * FROM clinical_rules ORDER BY updated_at DESC").fetchall()
    history = conn.execute("SELECT * FROM clinical_rule_versions ORDER BY created_at DESC LIMIT 20").fetchall()
    stances = conn.execute("SELECT * FROM clinical_stances").fetchall()
    pricing = conn.execute("SELECT * FROM pricing_plans").fetchall()
    conn.close()

    return {
        "rules": [dict(r) for r in rules],
        "history": [dict(h) for h in history],
        "stances": [dict(s) for s in stances],
        "pricing_plans": [dict(p) for p in pricing],
    }

@router.post("/rules")
def create_clinical_rule(req: RuleCreateRequest):
    """Allows medical staff to author or update a clinical protocol with versioning and audit history."""
    try:
        re.compile(req.trigger_pattern)
    except re.error as e:
        raise HTTPException(status_code=400, detail=f"Invalid regex trigger_pattern: {str(e)}")

    with get_db() as conn:
        existing = conn.execute("SELECT * FROM clinical_rules WHERE rule_code = ?", (req.rule_code,)).fetchone()
        
        if existing:
            new_version = existing["version"] + 1
            existing_dict = dict(existing)
            # Record audit history for previous version
            conn.execute("""
                INSERT INTO clinical_rule_versions (id, rule_code, version, category, severity, trigger_keywords, trigger_pattern, clinical_remedy, author_name, action, change_summary)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'UPDATED', ?)
            """, (
                f"ver_{uuid.uuid4().hex[:6]}",
                existing["rule_code"],
                existing["version"],
                existing["category"],
                existing_dict.get("severity", "mandatory"),
                existing["trigger_keywords"],
                existing["trigger_pattern"],
                existing["clinical_remedy"],
                req.author_name,
                f"Updated to version {new_version} by {req.author_name}"
            ))

            # Update existing rule
            conn.execute("""
                UPDATE clinical_rules
                SET category = ?, severity = ?, trigger_keywords = ?, trigger_pattern = ?, clinical_remedy = ?, author_name = ?, version = ?, previous_version_id = ?, updated_at = CURRENT_TIMESTAMP
                WHERE rule_code = ?
            """, (
                req.category,
                req.severity or "mandatory",
                json.dumps(req.trigger_keywords),
                req.trigger_pattern,
                req.clinical_remedy,
                req.author_name,
                new_version,
                existing["id"],
                req.rule_code
            ))
            return {"status": "success", "rule_code": req.rule_code, "version": new_version, "action": "updated"}

        else:
            rule_id = f"rule_{uuid.uuid4().hex[:6]}"
            conn.execute("""
                INSERT INTO clinical_rules (id, rule_code, category, severity, trigger_keywords, trigger_pattern, clinical_remedy, author_name, version, is_active, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1, 'active')
            """, (
                rule_id,
                req.rule_code,
                req.category,
                req.severity or "mandatory",
                json.dumps(req.trigger_keywords),
                req.trigger_pattern,
                req.clinical_remedy,
                req.author_name,
            ))
            conn.execute("""
                INSERT INTO clinical_rule_versions (id, rule_code, version, category, severity, trigger_keywords, trigger_pattern, clinical_remedy, author_name, action, change_summary)
                VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, 'CREATED', 'Initial version authoring')
            """, (
                f"ver_{uuid.uuid4().hex[:6]}",
                req.rule_code,
                req.category,
                req.severity or "mandatory",
                json.dumps(req.trigger_keywords),
                req.trigger_pattern,
                req.clinical_remedy,
                req.author_name,
            ))
            return {"status": "success", "rule_code": req.rule_code, "version": 1, "action": "created"}

@router.post("/rules/{rule_code}/rollback")
def rollback_clinical_rule(rule_code: str):
    """Rolls back a clinical rule to its immediately preceding version."""
    import uuid
    with get_db() as conn:
        current = conn.execute("SELECT * FROM clinical_rules WHERE rule_code = ?", (rule_code,)).fetchone()
        if not current:
            raise HTTPException(status_code=404, detail="Rule not found")

        prev_version = conn.execute("""
            SELECT * FROM clinical_rule_versions 
            WHERE rule_code = ? 
            ORDER BY version DESC LIMIT 1
        """, (rule_code,)).fetchone()

        if not prev_version:
            raise HTTPException(status_code=400, detail="No previous version found for rollback")

        new_version = current["version"] + 1
        conn.execute("""
            UPDATE clinical_rules
            SET category = ?, severity = ?, trigger_keywords = ?, trigger_pattern = ?, clinical_remedy = ?, author_name = ?, version = ?, updated_at = CURRENT_TIMESTAMP
            WHERE rule_code = ?
        """, (
            prev_version["category"],
            prev_version["severity"],
            prev_version["trigger_keywords"],
            prev_version["trigger_pattern"],
            prev_version["clinical_remedy"],
            prev_version["author_name"],
            new_version,
            rule_code
        ))

        conn.execute("""
            INSERT INTO clinical_rule_versions (id, rule_code, version, category, severity, trigger_keywords, trigger_pattern, clinical_remedy, author_name, action, change_summary)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ROLLED_BACK', ?)
        """, (
            f"ver_{uuid.uuid4().hex[:6]}",
            rule_code,
            new_version,
            prev_version["category"],
            prev_version["severity"],
            prev_version["trigger_keywords"],
            prev_version["trigger_pattern"],
            prev_version["clinical_remedy"],
            "System/Clinician",
            f"Rolled back to settings of v{prev_version['version']}"
        ))

    return {"status": "success", "rule_code": rule_code, "restored_version": prev_version["version"], "current_version": new_version}

@router.post("/rules/test")
def test_clinical_rule(req: RuleTestRequest):
    """Interactive rule testing playground for clinicians to verify regex triggers."""
    import re
    matched = False
    groups = []
    error = None
    try:
        pat = re.compile(req.pattern, re.IGNORECASE)
        m = pat.search(req.test_utterance)
        if m:
            matched = True
            groups = [m.group(0)]
    except Exception as e:
        error = str(e)

    kw_hits = [k for k in (req.keywords or []) if k.lower() in req.test_utterance.lower()]

    return {
        "matched": matched,
        "matched_phrases": groups,
        "keyword_hits": kw_hits,
        "regex_error": error
    }

# ---------------------------------------------------------
# RAG INGESTION & RETRIEVAL ENDPOINTS
# ---------------------------------------------------------

@router.post("/rag/upload")
async def rag_upload_document(req: DocumentUploadRequest):
    """
    Ingests and parses a clinical PDF, DOCX, or text document.
    Chunks text, calculates dense embeddings, indexes FTS5, and sets status ('draft' or 'approved').
    """
    if req.content_base64:
        file_bytes = base64.b64decode(req.content_base64)
    elif req.content_text:
        file_bytes = req.content_text.encode("utf-8")
    else:
        raise HTTPException(status_code=400, detail="Either content_text or content_base64 must be provided.")

    res = document_manager.ingest_document(
        title=req.title,
        filename=req.filename,
        file_bytes=file_bytes,
        file_type=req.file_type,
        category=req.category,
        author=req.author,
        patient_id=req.patient_id,
        auto_approve=req.auto_approve
    )
    return res

@router.get("/rag/documents")
def rag_list_documents(status: Optional[str] = None, patient_id: Optional[str] = None):
    """Lists ingested documents with their approval status and chunk counts."""
    return {"documents": document_manager.list_documents(approval_status=status, patient_id=patient_id)}

@router.get("/rag/documents/{doc_id}")
def rag_get_document(doc_id: str):
    """Retrieves document metadata and its individual structural chunks."""
    doc = document_manager.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc

@router.post("/rag/documents/{doc_id}/approve")
def rag_approve_document(doc_id: str):
    """Clinician workflow: Approves a draft document for production RAG retrieval."""
    return document_manager.approve_document(doc_id)

@router.post("/rag/documents/{doc_id}/deactivate")
def rag_deactivate_document(doc_id: str):
    """Clinician workflow: Deactivates / archives a document from active retrieval."""
    return document_manager.deactivate_document(doc_id)

@router.delete("/rag/documents/{doc_id}")
def rag_delete_document(doc_id: str):
    """Permanently deletes a document and all associated chunks and FTS indexes."""
    return document_manager.delete_document(doc_id)

@router.post("/rag/query")
def rag_query_test(req: RAGQueryRequest):
    """
    Interactive RAG retrieval playground:
    Returns hybrid retrieved chunks with BM25 rank, semantic score, RRF score, and citations.
    """
    chunks, conflict = hybrid_retriever.retrieve(
        query=req.query,
        patient_id=req.patient_id,
        category=req.category,
        top_k=req.top_k
    )
    return {
        "query": req.query,
        "patient_id": req.patient_id,
        "top_k": req.top_k,
        "chunks_count": len(chunks),
        "chunks": [c.to_dict() for c in chunks],
        "conflict_warning": conflict
    }

# ---------------------------------------------------------
# REAL-TIME WEBSOCKET VOICE CALL
# ---------------------------------------------------------

@router.websocket("/ws/call")
async def websocket_call_endpoint(websocket: WebSocket):
    """
    Real-time streaming two-way voice call gateway with unified conversation context,
    interruption (barge-in) handling, and persistent message history.
    """
    await websocket.accept()
    patient_id = websocket.query_params.get("patient_id") or f"pt_{uuid_short()}"
    session_id = websocket.query_params.get("session_id") or f"call_{uuid_short()}"

    # Preload recent conversation history so voice call has immediate context from prior chat
    dialogue_history: List[Dict[str, str]] = []
    try:
        conn = get_connection()
        prev_rows = conn.execute("""
            SELECT role, content FROM conversation_messages
            WHERE user_id = ?
            ORDER BY created_at DESC LIMIT 8
        """, (patient_id,)).fetchall()
        conn.close()
        dialogue_history = [{"role": r["role"], "content": r["content"]} for r in reversed(prev_rows)]
    except Exception:
        pass

    turn_counter = len(dialogue_history) // 2 + 1

    try:
        while True:
            msg = await websocket.receive_json()
            msg_type = msg.get("type")

            # Connection initialization
            if msg_type in ("connect", "init"):
                await websocket.send_json({
                    "type": "call_connected",
                    "session_id": session_id,
                    "patient_id": patient_id,
                    "history_count": len(dialogue_history),
                    "greeting": "Main sun rahi hoon. Aaj aapki diet ya routine mein kahan help chahiye?"
                })
                continue

            # Heartbeat ping/pong
            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            # Call termination
            if msg_type in ("call_end", "terminate"):
                await websocket.send_json({"type": "call_ended", "session_id": session_id})
                break

            # 1. User interruption / barge-in event
            if msg_type in ("interrupt", "barge_in"):
                played_fraction = float(msg.get("played_fraction", 0.5))
                if dialogue_history and dialogue_history[-1]["role"] == "assistant":
                    full_speech = dialogue_history[-1]["content"]
                    truncated = ContextSynchronizer.align_history(
                        full_speech, played_fraction
                    )
                    dialogue_history[-1]["content"] = truncated
                    try:
                        with get_db() as conn:
                            last_msg = conn.execute("""
                                SELECT id FROM conversation_messages
                                WHERE user_id = ? AND session_id = ? AND role = 'assistant'
                                ORDER BY created_at DESC LIMIT 1
                            """, (patient_id, session_id)).fetchone()
                            if last_msg:
                                conn.execute("UPDATE conversation_messages SET content = ? WHERE id = ?", (truncated, last_msg["id"]))
                    except Exception:
                        pass
                await websocket.send_json({"type": "interrupted", "session_id": session_id})
                continue

            # 2. Text or Audio Utterance
            utterance_text = ""
            if msg_type == "utterance":
                utterance_text = msg.get("text", "")
            elif msg_type == "audio":
                audio_b64 = msg.get("data", "")
                audio_bytes = base64.b64decode(audio_b64)
                utterance_text = await stt.transcribe(audio_bytes)

            if not utterance_text.strip():
                continue

            # Run turn through Safety Spine & Clinical Engine
            turn_res = await turn_orchestrator.execute_turn(
                patient_id=patient_id,
                utterance=utterance_text,
                session_id=session_id,
                turn_number=turn_counter,
                history=dialogue_history,
                source="voice",
            )
            turn_counter += 1

            # Update dialogue history
            dialogue_history.append({"role": "user", "content": utterance_text})
            dialogue_history.append({"role": "assistant", "content": turn_res.final_response})

            # Send turn response metadata
            await websocket.send_json({
                "type": "turn_result",
                "turn_id": turn_res.turn_id,
                "is_emergency": turn_res.is_emergency,
                "text": turn_res.final_response,
                "latency_ms": turn_res.latency_ms,
            })

            # Synthesize audio if requested
            if msg.get("synthesize_audio", True):
                try:
                    audio_bytes = await tts.synthesize(turn_res.final_response)
                    b64_audio = base64.b64encode(audio_bytes).decode("utf-8")
                    await websocket.send_json({
                        "type": "audio_payload",
                        "audio_base64": b64_audio,
                    })
                except Exception:
                    # Fallback to client-side speech synthesis if external audio network drops
                    await websocket.send_json({"type": "audio_fallback_to_client"})

    except WebSocketDisconnect:
        pass
    except Exception:
        pass

@router.get("/patient/{patient_id}/memories")
def get_patient_memories(patient_id: str):
    """Returns persistent memory facts extracted from conversations for this patient."""
    conn = get_connection()
    memories = conn.execute("""
        SELECT id, user_id, category, key, value, status, confidence, source_utterance, updated_at
        FROM user_memories
        WHERE user_id = ?
        ORDER BY updated_at DESC
    """, (patient_id,)).fetchall()
    conn.close()
    return {
        "patient_id": patient_id,
        "count": len(memories),
        "memories": [dict(m) for m in memories]
    }

@router.delete("/patient/{patient_id}/memories/{memory_id}")
def delete_patient_memory(patient_id: str, memory_id: str):
    """Deletes or invalidates a memory fact."""
    with get_db() as conn:
        conn.execute("DELETE FROM user_memories WHERE id = ? AND user_id = ?", (memory_id, patient_id))
    return {"status": "success", "message": f"Memory {memory_id} deleted"}

def uuid_short() -> str:
    import uuid
    return uuid.uuid4().hex[:8]

