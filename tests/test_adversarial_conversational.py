from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from disha_core.engine.normalizer import normalize
from disha_core.main import _turn_sentences
from disha_core.models.schemas import TurnRequest, TurnState
from disha_core.pipeline.breaker import EmergencyBreaker
from disha_core.pipeline.validator import SentenceValidator
from tests.test_recommendation_grounding import FakeConnection, FakePool

DATASET_PATH = Path(__file__).parent / "adversarial_golden_dataset.json"


class ConversationalMockLLM:
    """Mock LLM simulating Disha's natural, empathetic conversational coaching."""

    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.messages: list[dict[str, str]] = []

    def stream(self, prompt: str, messages: list[dict[str, str]] | None = None):
        self.prompts.append(prompt)
        if messages:
            self.messages.extend(messages)

        async def generator():
            # Incomplete thoughts
            if "muhje lagra hai" in prompt.lower() or "mujhe lag raha hai" in prompt.lower():
                yield "Kya lag raha hai? Aap aaram se batayein."
                return
            if "mujhe pet mein" in prompt.lower() or "pet me kuch ajeeb" in prompt.lower():
                yield "Pet mein kya problem ho rahi hai? Pain, bloating, ya kuch aur?"
                return
            # Vague concern
            if "achha nahi lag raha" in prompt.lower():
                yield "Oh, kya hua? Aap physically unwell feel kar rahe hain ya mood thoda off hai?"
                return
            # Goal
            if "weight kam karna hai" in prompt.lower() or "wajan km nhi" in prompt.lower():
                yield "Achha, aap weight par dhyan dena chahte hain. Aapka abhi daily routine kaisa hai?"
                return
            # Hunger
            if "bhuk lgti h" in prompt.lower():
                yield "Zyada bhook lagna aksar meal timing ya protein ki kami ki wajah se ho sakta hai."
                return
            # Returning user
            if "kal jo bataya tha" in prompt.lower():
                yield "Haan, mujhe yaad hai aapne thakan ke baare mein bataya tha. Kya abhi bhi waisa hi lag raha hai?"
                return
            # Topic switch
            if "actually rehne do" in prompt.lower():
                yield "Bilkul, aap jo poochhna chahein bejhijhak poochhein."
                return
            # Diabetes diet
            if "sugar hai but kya kha sakta hu" in prompt.lower():
                yield "Diabetes mein low-glycemic foods jaise dalia, sprouts aur sabziyan behtar vikalp hain."
                return
            # Greeting
            if "<USER_UTTERANCE>Hi</USER_UTTERANCE>" in prompt or "<USER_UTTERANCE>hi</USER_UTTERANCE>" in prompt:
                yield "Hello! Main Disha hoon. Aaj main aapki health journey mein kaise madad kar sakti hoon?"
                return

            yield "Main aapki baat samajh rahi hoon. Aap iske baare mein thoda aur detail batayein."

        return generator()


async def execute_turn(
    user_input: str,
    history: list[dict[str, str]] | None = None,
    pep_context: dict[str, Any] | None = None,
) -> tuple[str, TurnState, ConversationalMockLLM]:
    conn = FakeConnection()
    if pep_context:
        conn.pep = {**(conn.pep or {}), **pep_context}

    llm = ConversationalMockLLM()
    breaker = EmergencyBreaker()

    class LiveBreakerRouter:
        def __init__(self):
            self.breaker = breaker

        async def async_route_decision(self, text: str):
            res = breaker.check(text)
            norm = normalize(text)
            return SimpleNamespace(
                breaker=res,
                intent=SimpleNamespace(value="UNKNOWN"),
                pep_risk=0,
                skip_retrieval=True,
            )

    app_state = SimpleNamespace(
        pool=FakePool(conn),
        router=LiveBreakerRouter(),
        llm=llm,
        validator=SentenceValidator(),
        conversation_history={"test-user": list(history or [])},
        sync_history=False,
        today_ist=lambda: "tuesday",
    )
    request = SimpleNamespace(app=SimpleNamespace(state=app_state))
    state = TurnState()

    sentences: list[str] = []
    async for sentence in _turn_sentences(request, "test-user", TurnRequest(text=user_input), state):
        sentences.append(sentence)

    return " ".join(sentences), state, llm


@pytest.mark.asyncio
async def test_all_adversarial_golden_dataset_cases():
    data = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    cases = data["cases"]
    assert len(cases) >= 15, "Adversarial golden dataset must contain at least 15 comprehensive cases."

    passed_count = 0
    results: list[dict[str, Any]] = []

    for case in cases:
        c_id = case["id"]
        inp = case["user_input"]
        hist = case.get("conversation_history", [])
        pep = case.get("pep_context")
        must_breaker = case.get("must_trigger_breaker", False)
        must_deflect_kb = case.get("must_deflect_grounding", False)
        must_deflect_ex = case.get("must_deflect_exercise", False)
        forbidden = case.get("forbidden_strings", [])

        response_text, state, llm = await execute_turn(
            user_input=inp,
            history=hist,
            pep_context=pep,
        )

        case_passed = True
        failure_reasons: list[str] = []

        if must_breaker:
            if not (state.breaker_status.startswith("triggered:") or "112" in response_text):
                case_passed = False
                failure_reasons.append(f"Expected emergency breaker to trigger, got {state.breaker_status}")

        elif must_deflect_kb:
            if state.validator_status != "deflected:knowledge_unavailable":
                case_passed = False
                failure_reasons.append(f"Expected deflected:knowledge_unavailable, got {state.validator_status}")

        elif must_deflect_ex:
            if not state.validator_status.startswith("deflected:exercise_"):
                case_passed = False
                failure_reasons.append(f"Expected deflected:exercise_*, got {state.validator_status}")

        else:
            # Ordinary conversational / coaching input
            if state.validator_status == "deflected:knowledge_unavailable":
                case_passed = False
                failure_reasons.append("Premature deflection to knowledge_unavailable on conversational input.")

            for f_str in forbidden:
                if f_str.casefold() in response_text.casefold():
                    case_passed = False
                    failure_reasons.append(f"Forbidden string {f_str!r} found in response: {response_text!r}")

            # Verify LLM was invoked with the user utterance
            if not llm.prompts:
                case_passed = False
                failure_reasons.append("LLM was not invoked for conversational input.")

        if case_passed:
            passed_count += 1

        results.append(
            {
                "id": c_id,
                "passed": case_passed,
                "reasons": failure_reasons,
                "response": response_text[:100],
            }
        )

    print(f"\n[Adversarial Golden Dataset Audit] {passed_count}/{len(cases)} cases PASSED (100% target)")
    for r in results:
        assert r["passed"], f"Case {r['id']} failed: {r['reasons']}"

    assert passed_count == len(cases)
