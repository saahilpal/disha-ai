"""Response Harness Module (Section 5 Architecture).

Owns the single unified conversational lifecycle:
PERCEIVE -> PLAN -> GENERATE (stream) -> VERIFY -> REPAIR -> COMMIT
Tracking TurnContext trace, eliminating canned answer strings and fake Disha utterances.
"""

from __future__ import annotations

import logging
import time
from contextlib import suppress
from typing import Any, AsyncIterator

import asyncpg

from disha_core.engine.context_builder import (
    add_approved_remedy_constraints,
    build_patient_context,
    determine_length_policy,
    normalize_preferred_language,
    render_user_payload,
)
from disha_core.engine.normalizer import (
    UNSUPPORTED_LANGUAGE_REPLACEMENT,
    is_prescribed_meal_query,
    is_unsupported_language,
    normalize,
)
from disha_core.engine.retriever import retrieve_chunks
from disha_core.harness.planner import StructuredPlan, build_structured_plan
from disha_core.harness.repair import format_system_error, repair_turn
from disha_core.harness.verifier import verify_response
from disha_core.llm.sentence_buffer import validated_sentences
from disha_core.models.schemas import TurnRequest, TurnState
from disha_core.models.turn_context import TurnContext
from disha_core.pep.exercise_safety import extract_patient_health_tags
from disha_core.pipeline.breaker import EmergencyBreaker
from disha_core.pipeline.router import Intent
from disha_core.pipeline.validator import (
    MEAL_NOT_FOUND_REPLACEMENT,
    PEP_REPLACEMENT,
    SentenceValidator,
    knowledge_unavailable_response,
)

logger = logging.getLogger("disha_core.harness")


def _get_app_main() -> Any:
    import sys
    return sys.modules.get("disha_core.main")


class ResponseHarness:
    """Master response pipeline harness orchestrating PERCEIVE -> PLAN -> GENERATE -> VERIFY -> REPAIR -> COMMIT."""

    def __init__(self, llm_client: Any, validator: SentenceValidator | None = None) -> None:
        self.llm = llm_client
        self.validator = validator or SentenceValidator()

    async def execute_turn(
        self,
        request: Any,
        patient_id: str,
        payload: TurnRequest,
        legacy_state: TurnState | None = None,
        turn_context: TurnContext | None = None,
    ) -> AsyncIterator[str]:
        """Execute complete response turn lifecycle with TurnContext tracking."""
        t_start = time.monotonic()
        state = legacy_state if legacy_state is not None else TurnState()
        tc = turn_context or TurnContext(patient_id=patient_id)
        tc.transcript.final = payload.text
        app_state = getattr(request, "app", request).state

        # ==========================================
        # 1. PERCEIVE
        # ==========================================
        t0 = time.monotonic()

        # 1a. Table-driven emergency protocol BEFORE LLM step
        breaker = getattr(getattr(app_state, "router", None), "breaker", EmergencyBreaker())
        emergency = breaker.check(payload.text)
        if emergency.triggered:
            tc.safety.breaker_triggered = True
            tc.safety.category = emergency.category
            tc.safety.response = emergency.response
            state.breaker_status = f"triggered:{emergency.category}"
            tc.record_stage_latency("PERCEIVE", (time.monotonic() - t0) * 1000.0)
            emergency_text = emergency.response or "Yeh emergency ho sakti hai. Abhi 112 par call karein."
            tc.validator.validated_sentences = [emergency_text]
            tc.validator.status = f"triggered:{emergency.category}"
            yield emergency_text
            return

        # 1b. Language boundary check
        if is_unsupported_language(payload.text):
            tc.language.is_supported = False
            tc.language.deflected = True
            state.validator_status = "deflected:unsupported_language"
            tc.record_stage_latency("PERCEIVE", (time.monotonic() - t0) * 1000.0)
            tc.validator.validated_sentences = [UNSUPPORTED_LANGUAGE_REPLACEMENT]
            tc.validator.status = "deflected:unsupported_language"
            yield UNSUPPORTED_LANGUAGE_REPLACEMENT
            return

        # 1c. Routing & Intent Perception
        router = getattr(app_state, "router", None)
        pep_risk = 0
        skip_retrieval = False
        intent = None
        if router is not None:
            if hasattr(router, "async_route_decision"):
                decision = await router.async_route_decision(payload.text)
                intent = decision.intent
                pep_risk = decision.pep_risk
                skip_retrieval = decision.skip_retrieval
            elif hasattr(router, "async_route"):
                _, intent = await router.async_route(payload.text)
                pep_risk = getattr(router, "last_pep_risk", 0)
                skip_retrieval = intent in {Intent.GENERAL_COACHING, Intent.APP_META, Intent.GREETING}
            elif hasattr(router, "route"):
                _, intent = router.route(payload.text)
                pep_risk = getattr(router, "last_pep_risk", 0)
                skip_retrieval = intent in {Intent.GENERAL_COACHING, Intent.APP_META, Intent.GREETING}

        tc.stage_intent.intent = getattr(intent, "value", str(intent or "general_coaching"))
        tc.safety.pep_risk = pep_risk

        # 1d. Patient context and PEP loading
        day = app_state.today_ist() if hasattr(app_state, "today_ist") else "monday"
        prescribed_meal_query = is_prescribed_meal_query(payload.text)
        pool = getattr(app_state, "pool", None)
        context: dict[str, Any] = {}

        app_m = _get_app_main()
        ctx_builder = getattr(app_m, "build_patient_context", build_patient_context) if app_m else build_patient_context
        try:
            if pool is None:
                context = await ctx_builder(
                    None,
                    patient_id,
                    day,
                    payload.meal_type if prescribed_meal_query else None,
                    user_input=payload.text,
                    intent=intent.value if intent else None,
                )
            else:
                async with pool.acquire() as connection:
                    context = await ctx_builder(
                        connection,
                        patient_id,
                        day,
                        payload.meal_type if prescribed_meal_query else None,
                        user_input=payload.text,
                        intent=intent.value if intent else None,
                    )
        except (asyncpg.PostgresError, ConnectionError, OSError, RuntimeError) as exc:
            logger.warning("Database unavailable in ResponseHarness PERCEIVE: %s", exc)
            state.validator_status = "deflected:db_unavailable"
            state.retrieval_status = "unavailable"
            tc.validator.status = "deflected:db_unavailable"
            tc.retrieval.skipped = True
            err_msg = format_system_error(
                "Database connection unavailable", "Kripya thodi der baad koshish karein."
            )
            yield err_msg
            return

        normalized = normalize(payload.text)
        is_incomplete_thought = payload.text.strip().endswith("...") or (
            len(payload.text.strip().split()) <= 4
            and not normalized.is_recommendation_request
            and not any(
                q_word in payload.text.casefold()
                for q_word in ("kya", "kaise", "kyun", "what", "how", "why", "when", "kahan", "where", "hi", "hello")
            )
        )
        context["is_incomplete_thought"] = is_incomplete_thought
        context["clinical_tags"] = normalized.tags
        context["intent"] = intent.value if intent else Intent.UNKNOWN.value
        context["pep_risk"] = pep_risk
        context["user_input"] = payload.text
        context["meal_relevant"] = normalized.is_meal_query or intent == Intent.MEAL_QUERY
        context["exercise_relevant"] = normalized.is_exercise_query or intent == Intent.EXERCISE_QUERY
        context["length_policy"] = determine_length_policy(
            payload.text,
            intent.value if intent else None,
            is_emergency=False,
        )

        # 1e. Prescribed Meal & Diet Status Checks
        if prescribed_meal_query and payload.meal_type is None:
            state.validator_status = "deflected:meal_window_required"
            tc.validator.status = "deflected:meal_window_required"
            msg = "Aap apne prescribed plan mein kaunsa meal dekhna chahte hain: breakfast, lunch, ya dinner?"
            yield msg
            return

        if prescribed_meal_query and context.get("diet_status") == "NOT_FOUND":
            state.validator_status = "rewritten:meal_not_found"
            tc.validator.status = "rewritten:meal_not_found"
            yield MEAL_NOT_FOUND_REPLACEMENT
            return

        if prescribed_meal_query and context.get("diet_status") != "FOUND":
            state.validator_status = "deflected:meal_plan_unavailable"
            tc.validator.status = "deflected:meal_plan_unavailable"
            msg = "Main abhi aapka saved meal plan access nahi kar paa rahi. Kripya thodi der baad phir koshish karein."
            yield msg
            return

        # 1f. PEP Safety Envelope Check
        pep = context.get("pep") or {}
        restricted = {str(item).replace("_", " ").casefold() for item in pep.get("restricted_modalities") or ()}
        hypertension_stage = str(pep.get("hypertension_stage") or "").casefold().replace("_", " ")
        diagnosed = " ".join(str(item) for item in pep.get("diagnosed_conditions") or ()).casefold()
        has_cardiac_htn = hypertension_stage in {"stage 1", "stage 2", "crisis"} or any(
            condition in diagnosed for condition in ("cardiac", "heart", "coronary", "arrhythmia")
        )
        if pep_risk >= 2 and (restricted or has_cardiac_htn):
            state.validator_status = "rewritten:pep_restriction"
            tc.validator.status = "rewritten:pep_restriction"
            yield PEP_REPLACEMENT
            return

        # 1g. Conversation History & Disclosures
        if not hasattr(app_state, "conversation_history"):
            app_state.conversation_history = {}
        db_history = context.get("conversation_history") or []
        if patient_id not in app_state.conversation_history or not app_state.conversation_history[patient_id]:
            app_state.conversation_history[patient_id] = list(db_history)

        history = app_state.conversation_history.get(patient_id, [])[-8:]
        context["has_history"] = bool(history)
        tc.memory_brief.has_history = bool(history)
        tc.memory_brief.history_turns = list(history)

        # 1h. RAG Retrieval via single acquired connection
        channel = "voice" if hasattr(request, "client_state") or "WebSocket" in str(type(request)) else "chat"
        tc.channel = channel
        chunks: tuple[Any, ...] = ()

        if getattr(app_state, "pool", None) is not None:
            try:
                async with app_state.pool.acquire() as connection:
                    with suppress(Exception):
                        from disha_core.journey import (
                            extract_patient_disclosures,
                            load_or_create_journey,
                            record_field_answer,
                            select_next_question,
                        )

                        lang = normalize_preferred_language((context.get("pep") or {}).get("language"))
                        lang = {"english": "en", "hindi": "hi"}.get(lang, "hinglish")
                        disclosures = extract_patient_disclosures(payload.text, lang=lang)
                        for f_id, f_val in disclosures.items():
                            await record_field_answer(
                                patient_id=patient_id,
                                field_id=f_id,
                                raw_value=f_val,
                                raw_text=payload.text,
                                channel=channel,
                                conn=connection,
                                lang=lang,
                            )
                        journey_state = await load_or_create_journey(patient_id, conn=connection, channel=channel)
                        context["journey_state"] = journey_state
                        is_off_topic = (
                            bool(
                                normalized.is_meal_query
                                or normalized.is_exercise_query
                                or intent in {Intent.MEAL_QUERY, Intent.EXERCISE_QUERY, Intent.SYMPTOM_COMPLAINT}
                            )
                            and not disclosures
                        )
                        if not is_incomplete_thought:
                            scheduled_q = await select_next_question(
                                patient_id=patient_id,
                                journey_state=journey_state,
                                user_turn_text=payload.text,
                                channel=channel,
                                is_emergency=False,
                                is_off_topic_query=is_off_topic,
                                conn=connection,
                                preferred_lang=lang,
                            )
                            if scheduled_q:
                                context["scheduled_question"] = scheduled_q.text

                    should_retrieve = not prescribed_meal_query and (
                        bool(normalized.tags)
                        or normalized.is_meal_query
                        or normalized.is_exercise_query
                        or normalized.is_recommendation_request
                        or (
                            not skip_retrieval
                            and intent not in {Intent.GENERAL_COACHING, Intent.APP_META, Intent.GREETING}
                        )
                    )
                    if should_retrieve:
                        pep_context = context.get("pep") or {}
                        contextual_terms: list[str] = []
                        if normalized.is_meal_query:
                            contextual_terms.extend(
                                str(value)
                                for value in (
                                    pep_context.get("dietary_preference"),
                                    pep_context.get("primary_focus"),
                                    *(pep_context.get("diagnosed_conditions") or ()),
                                )
                                if value
                            )
                        if normalized.is_exercise_query:
                            contextual_terms.extend(
                                str(value)
                                for value in (
                                    pep_context.get("user_reported_concerns"),
                                    *(pep_context.get("restricted_modalities") or ()),
                                    *(pep_context.get("diagnosed_conditions") or ()),
                                )
                                if value
                            )
                        retrieval_query = " ".join((normalized.normalized, *contextual_terms))
                        profile_tags = normalize(" ".join(contextual_terms)).tags
                        target_tags = list(dict.fromkeys((*normalized.tags, *profile_tags)))
                        retriever = getattr(app_m, "retrieve_chunks", retrieve_chunks) if app_m else retrieve_chunks
                        chunks = await retriever(
                            connection, retrieval_query, patient_id=patient_id, tags=target_tags
                        )
                        state.retrieval_status = "retrieved" if chunks else "no_results"
                        state.evidence_ids = [
                            str(getter("chunk_id"))
                            for chunk in chunks
                            if (
                                getter := (
                                    chunk.get
                                    if hasattr(chunk, "get")
                                    else lambda key, default=None: getattr(chunk, key, default)
                                )
                            )("chunk_id", None)
                            is not None
                        ]
                        if len(state.evidence_ids) != len(chunks):
                            state.retrieval_status = "invalid_provenance"
                            chunks = ()
                            state.evidence_ids = []
                        else:
                            context["retrieved_evidence_ids"] = state.evidence_ids
                            tc.retrieval.evidence_ids = state.evidence_ids
                            tc.retrieval.chunk_count = len(chunks)
            except (asyncpg.PostgresError, ConnectionError, OSError, RuntimeError) as exc:
                logger.warning("Database retrieval unavailable: %s", exc)
                state.retrieval_status = "unavailable"
                tc.retrieval.skipped = True
                chunks = ()
        elif normalized.tags or intent in {
            Intent.MEAL_QUERY,
            Intent.EXERCISE_QUERY,
            Intent.SYMPTOM_COMPLAINT,
        }:
            state.retrieval_status = "unavailable"
            tc.retrieval.skipped = True

        # 1i. Clinical Grounding & Exercise Safety Gates
        requires_grounding = normalized.is_recommendation_request and not is_incomplete_thought
        if prescribed_meal_query and context.get("diet_status") == "FOUND":
            requires_grounding = False

        if normalized.is_exercise_query and normalized.is_recommendation_request:
            pep_context = context.get("pep") or {}
            safety_tags = extract_patient_health_tags(
                pep_data=pep_context,
                reported_symptoms=[
                    payload.text,
                    str(pep_context.get("user_reported_concerns") or ""),
                ],
                physical_limitations=pep_context.get("restricted_modalities") or (),
                diagnosed_conditions=pep_context.get("diagnosed_conditions") or (),
            )
            has_recorded_safety_context = bool(
                pep_context.get("user_reported_concerns")
                or pep_context.get("restricted_modalities")
                or pep_context.get("diagnosed_conditions")
                or (pep_context.get("hypertension_stage") or "").casefold() not in {"", "unknown", "none"}
            )
            if safety_tags:
                state.validator_status = "deflected:exercise_suitability_uncertain"
                tc.validator.status = "deflected:exercise_suitability_uncertain"
                msg = (
                    "Aapke bataye hue ya saved health context ke saath main abhi workout ya alternate movement "
                    "recommend nahi karungi, kyunki uski suitability establish nahi hui. Aap apni limitation "
                    "aur jis activity ke baare mein pooch rahe hain woh batayein; zarurat par clinician se "
                    "suitability confirm karein."
                )
                yield msg
                return
            if not has_recorded_safety_context:
                state.validator_status = "deflected:exercise_context_required"
                tc.validator.status = "deflected:exercise_context_required"
                msg = (
                    "Personalized exercise suggestion se pehle batayein ki aapko pain, injury, recent surgery, "
                    "mobility difficulty, heart condition, ya exercise restriction hai ya nahi. Bina is context "
                    "ke main workout recommend nahi karungi."
                )
                yield msg
                return

        if requires_grounding and not chunks:
            state.validator_status = "deflected:knowledge_unavailable"
            tc.validator.status = "deflected:knowledge_unavailable"
            preferred_language = (context.get("pep") or {}).get("language")
            msg = knowledge_unavailable_response(preferred_language)
            yield msg
            return

        add_approved_remedy_constraints(context, chunks)
        tc.record_stage_latency("PERCEIVE", (time.monotonic() - t0) * 1000.0)

        # ==========================================
        # 2. PLAN
        # ==========================================
        t1 = time.monotonic()
        plan: StructuredPlan = build_structured_plan(payload.text, context, intent=intent.value if intent else None)
        context["structured_plan"] = plan.to_json()
        tc.record_stage_latency("PLAN", (time.monotonic() - t1) * 1000.0)

        # ==========================================
        # 3. GENERATE (stream)
        # ==========================================
        t2 = time.monotonic()
        payload_renderer = getattr(app_m, "render_user_payload", render_user_payload) if app_m else render_user_payload
        prompt = payload_renderer(normalized.normalized, context, chunks)

        llm_instance = getattr(app_state, "llm", self.llm)
        try:
            llm_stream = llm_instance.stream(prompt, messages=history)
        except TypeError:
            llm_stream = llm_instance.stream(prompt)

        generated_sentences: list[str] = []
        emitted = False

        # ==========================================
        # 4 & 5. VERIFY & REPAIR
        # ==========================================
        val_stream_fn = getattr(app_m, "validated_sentences", validated_sentences) if app_m else validated_sentences
        validator_instance = getattr(app_state, "validator", self.validator)
        try:
            raw_generated_chunks: list[str] = []
            async for sentence in val_stream_fn(llm_stream, validator_instance, context):
                # Verify individual sentence boundaries
                v_res = verify_response(sentence, context)
                if not v_res.is_valid:
                    # Repair sentence if violated
                    repaired_sent, ok, _ = await repair_turn(
                        llm_instance,
                        prompt,
                        sentence,
                        v_res,
                        context,
                        messages=history,
                        max_attempts=2,
                    )
                    final_sent = repaired_sent
                else:
                    final_sent = sentence

                emitted = True
                generated_sentences.append(final_sent)
                yield final_sent

        except Exception as exc:
            logger.exception("LLM generation stream failed: %s", exc)
            state.validator_status = "provider_unavailable"
            tc.validator.status = "provider_unavailable"
            if not emitted:
                err_msg = format_system_error(
                    "LLM provider unavailable", "Kripya thodi der baad koshish karein."
                )
                yield err_msg
                return

        tc.record_stage_latency("GENERATE", (time.monotonic() - t2) * 1000.0)

        # ==========================================
        # 6. COMMIT
        # ==========================================
        t3 = time.monotonic()
        if state.validator_status == "accepted":
            state.validator_status = "validated"
        tc.validator.status = state.validator_status
        tc.validator.validated_sentences = list(generated_sentences)

        if generated_sentences:
            full_reply = " ".join(generated_sentences)
            if patient_id not in app_state.conversation_history:
                app_state.conversation_history[patient_id] = []
            app_state.conversation_history[patient_id].append({"role": "user", "content": payload.text})
            app_state.conversation_history[patient_id].append({"role": "assistant", "content": full_reply})
            app_state.conversation_history[patient_id] = app_state.conversation_history[patient_id][-16:]

            if getattr(app_state, "pool", None) is not None:
                with suppress(Exception):
                    from disha_core.services.chat_service import persist_patient_disclosure, store_conversation_turn

                    async with app_state.pool.acquire() as save_conn:
                        await store_conversation_turn(save_conn, patient_id, payload.text, full_reply)
                        await persist_patient_disclosure(save_conn, patient_id, payload.text)

        tc.record_stage_latency("COMMIT", (time.monotonic() - t3) * 1000.0)
        tc.record_stage_latency("TOTAL_TURN", (time.monotonic() - t_start) * 1000.0)
