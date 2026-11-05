import time
import json
import uuid
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

from app.guardrails.pre_turn_emergency import emergency_circuit_breaker, EmergencyCheckResult
from app.guardrails.post_turn_sanitizer import post_turn_sanitizer, PostTurnSanitizeResult
from app.guardrails.egress_gate import EgressGate
from app.knowledge.retriever import hybrid_retriever
from app.knowledge.patient_grounding import patient_context_resolver
from app.llm.prompt_builder import PromptBuilder
from app.llm.client import llm_client
from app.db.connection import get_connection, get_db

class LatencyBreakdown(BaseModel):
    guardrail_ms: float
    retrieval_ms: float
    llm_ttft_ms: float
    sanitizer_ms: float
    total_ms: float

class TurnResult(BaseModel):
    turn_id: str
    session_id: str
    turn_number: int
    user_utterance: str
    is_emergency: bool
    emergency_category: Optional[str] = None
    turn_status: str             # 'SUCCESS' | 'EMERGENCY_HALTED' | 'DEGRADED'
    final_response: str
    pre_guardrail: Dict[str, Any]
    post_guardrail: Dict[str, Any]
    retrieved_rules: List[str]
    latency: LatencyBreakdown

class VoiceTurnOrchestrator:
    """
    Central Turn Orchestrator implementing the Thick Deterministic Spine.
    Coordinates speech ingestion, emergency triage, hybrid retrieval, LLM reasoning,
    atomic output sanitization, and audit persistence.
    """

    def __init__(self, db_path: str = None):
        self.db_path = db_path

    async def execute_turn(
        self,
        patient_id: str,
        utterance: str,
        session_id: Optional[str] = None,
        turn_number: int = 1,
        dialogue_history: Optional[List[Dict[str, str]]] = None
    ) -> TurnResult:
        turn_start = time.perf_counter()
        turn_id = f"turn_{uuid.uuid4().hex[:8]}"
        sid = session_id or f"sess_{uuid.uuid4().hex[:8]}"

        # STEP 1: Pre-Turn Emergency Red-Flag Circuit Breaker (<0.005ms)
        emg_result = emergency_circuit_breaker.evaluate(utterance)
        
        if emg_result.is_emergency:
            # Critical Emergency: Bypass LLM completely
            total_ms = (time.perf_counter() - turn_start) * 1000.0
            latency = LatencyBreakdown(
                guardrail_ms=emg_result.latency_ms,
                retrieval_ms=0.0,
                llm_ttft_ms=0.0,
                sanitizer_ms=0.0,
                total_ms=total_ms
            )

            # Persist turn in audit ledger first (foreign key dependency)
            self._record_turn(
                turn_id=turn_id,
                session_id=sid,
                turn_number=turn_number,
                user_utterance=utterance,
                pre_status="EMERGENCY_TRIGGERED",
                rules_json="[]",
                raw_llm=None,
                post_status="EMERGENCY_OVERRIDE",
                final_response=emg_result.triage_message,
                latency_dict=latency.model_dump(),
                patient_id=patient_id
            )

            # Persist emergency alert referencing the recorded turn
            self._record_emergency_escalation(
                turn_id=turn_id,
                patient_id=patient_id,
                category=emg_result.category or "general",
                phrases=emg_result.matched_phrases,
                action="LLM_ABORTED_TRIAGE_AUDIO_EMITTED"
            )

            return TurnResult(
                turn_id=turn_id,
                session_id=sid,
                turn_number=turn_number,
                user_utterance=utterance,
                is_emergency=True,
                emergency_category=emg_result.category,
                turn_status="EMERGENCY_HALTED",
                final_response=emg_result.triage_message,
                pre_guardrail=emg_result.model_dump(),
                post_guardrail={"action": "EMERGENCY_AUDIO_OVERRIDE"},
                retrieved_rules=[],
                latency=latency
            )

        # STEP 2: Patient Context & Dynamic Grounding
        rag_start = time.perf_counter()
        pep = patient_context_resolver.get_pep_profile(patient_id)
        patient_raw = patient_context_resolver.get_patient_profile(patient_id)
        real_first_name = patient_raw["full_name"].split()[0] if patient_raw else "Friend"

        # Upstream PHI De-identification Proxy
        synthetic_name = "[PATIENT_FIRST_NAME]"

        retrieved_facts: List[str] = []
        retrieved_rule_codes: List[str] = []
        mandatory_remedy_tokens: List[str] = []

        # A. Dynamic Meal Plan Lookup (Failure #6: Today's Dinner)
        lower_utt = utterance.lower()
        if any(w in lower_utt for w in ["dinner", "lunch", "breakfast", "diet chart", "khana", "meal"]):
            meal_type = "dinner" if "dinner" in lower_utt else ("lunch" if "lunch" in lower_utt else "breakfast")
            meal_data = patient_context_resolver.get_meal_plan(patient_id, meal_type=meal_type)
            retrieved_facts.append(f"Today's {meal_type.title()} from DB: {meal_data['summary']}")
            retrieved_rule_codes.append(f"DB_{meal_type.upper()}_PLAN")

        # B. Pricing Facts Lookup (Failure #1: Pricing)
        if any(w in lower_utt for w in ["paid", "subscription", "price", "paise", "kitne ka"]):
            pricing_summary = patient_context_resolver.get_pricing_summary()
            retrieved_facts.append(f"Verified Pricing Catalog:\n{pricing_summary}")
            retrieved_rule_codes.append("DB_PRICING_PLANS")

        # C. Hybrid Knowledge RAG (Rules & Stances: Failures #2 & #8)
        knowledge_items = hybrid_retriever.retrieve(utterance, top_k=2)
        for item in knowledge_items:
            retrieved_facts.append(f"{item.code_or_entity}: {item.content}")
            retrieved_rule_codes.append(item.code_or_entity)
            if item.required_remedy_tokens:
                mandatory_remedy_tokens.extend(item.required_remedy_tokens)

        retrieval_ms = (time.perf_counter() - rag_start) * 1000.0

        # STEP 3: Prompt Assembly (<320 tokens ceiling)
        messages = PromptBuilder.build_turn_prompt(
            patient_first_name=synthetic_name,
            pep_profile=pep,
            retrieved_facts=retrieved_facts,
            user_utterance=utterance,
            dialogue_history=dialogue_history
        )

        # STEP 4: LLM Generation
        raw_llm_text, llm_ttft_ms = await llm_client.generate(messages)

        # STEP 5: Atomic Sentence Barrier & Post-Turn Output Sanitizer
        sanitizer_start = time.perf_counter()
        sanitize_result = post_turn_sanitizer.sanitize(
            raw_text=raw_llm_text,
            required_remedy_tokens=mandatory_remedy_tokens
        )
        
        # Re-hydrate first name
        final_text = sanitize_result.sanitized_text.replace("[PATIENT_FIRST_NAME]", real_first_name)
        # Final pass through EgressGate to ensure zero credential/ABHA leakage
        final_text = EgressGate.sanitize(final_text)
        sanitizer_ms = (time.perf_counter() - sanitizer_start) * 1000.0

        total_ms = (time.perf_counter() - turn_start) * 1000.0
        latency = LatencyBreakdown(
            guardrail_ms=emg_result.latency_ms,
            retrieval_ms=retrieval_ms,
            llm_ttft_ms=llm_ttft_ms,
            sanitizer_ms=sanitizer_ms,
            total_ms=total_ms
        )

        # STEP 6: Persist Turn in SQLite Audit Ledger
        self._record_turn(
            turn_id=turn_id,
            session_id=sid,
            turn_number=turn_number,
            user_utterance=utterance,
            pre_status="PASS",
            rules_json=json.dumps(retrieved_rule_codes),
            raw_llm=raw_llm_text,
            post_status=sanitize_result.modification_reason or "CLEAN",
            final_response=final_text,
            latency_dict=latency.model_dump(),
            patient_id=patient_id
        )

        return TurnResult(
            turn_id=turn_id,
            session_id=sid,
            turn_number=turn_number,
            user_utterance=utterance,
            is_emergency=False,
            turn_status="SUCCESS",
            final_response=final_text,
            pre_guardrail=emg_result.model_dump(),
            post_guardrail=sanitize_result.model_dump(),
            retrieved_rules=retrieved_rule_codes,
            latency=latency
        )

    def _record_emergency_escalation(self, turn_id: str, patient_id: str, category: str, phrases: List[str], action: str):
        with get_db(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO emergency_escalations (id, turn_id, patient_id, red_flag_category, detected_phrases, triage_action_taken, care_ops_notified)
                VALUES (?, ?, ?, ?, ?, ?, 1)
            """, (f"esc_{uuid.uuid4().hex[:8]}", turn_id, patient_id, category, json.dumps(phrases), action))

    def _record_turn(self, turn_id: str, session_id: str, turn_number: int, user_utterance: str, pre_status: str, rules_json: str, raw_llm: Optional[str], post_status: str, final_response: str, latency_dict: Dict[str, Any], patient_id: str = "pt_101"):
        with get_db(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO call_sessions (id, patient_id, status, total_turns)
                VALUES (?, ?, 'ACTIVE', ?)
            """, (session_id, patient_id, turn_number))
            cursor.execute("""
                INSERT INTO call_turns (id, session_id, turn_number, user_utterance, pre_guardrail_status, retrieved_rule_codes, raw_llm_response, post_guardrail_status, final_response, latency_breakdown)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (turn_id, session_id, turn_number, user_utterance, pre_status, rules_json, raw_llm, post_status, final_response, json.dumps(latency_dict)))

# Global singleton
turn_orchestrator = VoiceTurnOrchestrator()
