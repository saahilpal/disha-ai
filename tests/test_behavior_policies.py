"""Unit and integration tests for Situation Policy Pack and hot-reloading loader."""

from __future__ import annotations

import shutil
import tempfile
import threading
import time
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError

from disha_core.policies.loader import (
    PolicyPackLoader,
    get_policy_loader,
    reset_policy_loader,
)
from disha_core.policies.schema import (
    ExampleLanguage,
    ExampleType,
    PolicyExample,
    PolicyStatus,
    SituationPolicy,
)

EXPECTED_25_SITUATIONS = [
    "incomplete_message",
    "vague_message",
    "emotional_venting",
    "symptom_report",
    "red_flag",
    "crisis_self_harm",
    "medication_dose",
    "diet_exercise",
    "plan_lookup",
    "goal_setting",
    "progress_wins",
    "lapse_support",
    "motivation_dip",
    "small_talk",
    "humor_human_check",
    "pricing_product",
    "unsupported_capability",
    "out_of_scope",
    "unsupported_language",
    "privacy_request",
    "abusive_user",
    "silence_timeout",
    "correction_of_fact",
    "repeated_question",
    "returning_after_gap",
]


@pytest.fixture(autouse=True)
def clean_global_loader():
    reset_policy_loader()
    yield
    reset_policy_loader()


class TestPolicySchemaValidation:
    """Tests for strict Pydantic schema validation."""

    def test_valid_policy_card(self):
        card = SituationPolicy(
            situation_id="test_situation",
            triggers=["test trigger 1", "test trigger 2"],
            objective="Provide a clear, evidence-based response to the test situation.",
            must=["Do action A", "Do action B"],
            must_not=["Do not do action X"],
            response_shape="Action A -> Action B",
            coach_moves=["reflective listening", "scaling"],
            owner="clinical_lead",
            version="1.0.0",
            status=PolicyStatus.ACTIVE,
            examples=[
                PolicyExample(
                    user_input="Hello good",
                    response="Hi there!",
                    type=ExampleType.GOOD,
                    language=ExampleLanguage.EN,
                    critique="Clear and direct.",
                ),
                PolicyExample(
                    user_input="Namaste good",
                    response="Namaste!",
                    type=ExampleType.GOOD,
                    language=ExampleLanguage.HINGLISH,
                    critique="Warm and culturally aligned.",
                ),
                PolicyExample(
                    user_input="Hello bad",
                    response="Go away",
                    type=ExampleType.BAD,
                    language=ExampleLanguage.EN,
                    critique="Rude response.",
                ),
                PolicyExample(
                    user_input="Namaste bad",
                    response="Shut up",
                    type=ExampleType.BAD,
                    language=ExampleLanguage.HINGLISH,
                    critique="Abusive response.",
                ),
            ],
        )
        assert card.situation_id == "test_situation"
        assert len(card.good_examples) == 2
        assert len(card.bad_examples) == 2

    def test_schema_rejects_insufficient_good_examples(self):
        with pytest.raises(ValidationError) as exc:
            SituationPolicy(
                situation_id="test_insufficient",
                triggers=["test"],
                objective="Objective of sufficient length.",
                must=["Action"],
                must_not=["Anti-action"],
                response_shape="Shape",
                coach_moves=["Move"],
                owner="team",
                version="1.0.0",
                examples=[
                    PolicyExample(
                        user_input="Single good",
                        response="Good",
                        type=ExampleType.GOOD,
                        language=ExampleLanguage.EN,
                        critique="Only one good example.",
                    ),
                    PolicyExample(
                        user_input="Bad 1",
                        response="Bad",
                        type=ExampleType.BAD,
                        language=ExampleLanguage.EN,
                        critique="Bad 1",
                    ),
                    PolicyExample(
                        user_input="Bad 2",
                        response="Bad",
                        type=ExampleType.BAD,
                        language=ExampleLanguage.EN,
                        critique="Bad 2",
                    ),
                ],
            )
        assert "at least 2 good examples" in str(exc.value)

    def test_schema_rejects_insufficient_bad_examples(self):
        with pytest.raises(ValidationError) as exc:
            SituationPolicy(
                situation_id="test_insufficient_bad",
                triggers=["test"],
                objective="Objective of sufficient length.",
                must=["Action"],
                must_not=["Anti-action"],
                response_shape="Shape",
                coach_moves=["Move"],
                owner="team",
                version="1.0.0",
                examples=[
                    PolicyExample(
                        user_input="Good 1",
                        response="Good",
                        type=ExampleType.GOOD,
                        language=ExampleLanguage.EN,
                        critique="Good 1",
                    ),
                    PolicyExample(
                        user_input="Good 2",
                        response="Good",
                        type=ExampleType.GOOD,
                        language=ExampleLanguage.EN,
                        critique="Good 2",
                    ),
                    PolicyExample(
                        user_input="Bad 1",
                        response="Bad",
                        type=ExampleType.BAD,
                        language=ExampleLanguage.EN,
                        critique="Bad 1",
                    ),
                ],
            )
        assert "at least 2 bad examples" in str(exc.value)

    def test_schema_forbids_extra_fields(self):
        with pytest.raises(ValidationError):
            SituationPolicy(
                situation_id="extra_fields",
                triggers=["test"],
                objective="Objective of sufficient length.",
                must=["Action"],
                must_not=["Anti-action"],
                response_shape="Shape",
                coach_moves=["Move"],
                owner="team",
                version="1.0.0",
                unknown_extra_field="invalid",
                examples=[
                    PolicyExample(
                        user_input="Good 1",
                        response="Good",
                        type=ExampleType.GOOD,
                        language=ExampleLanguage.EN,
                        critique="Good 1",
                    ),
                    PolicyExample(
                        user_input="Good 2",
                        response="Good",
                        type=ExampleType.GOOD,
                        language=ExampleLanguage.EN,
                        critique="Good 2",
                    ),
                    PolicyExample(
                        user_input="Bad 1",
                        response="Bad",
                        type=ExampleType.BAD,
                        language=ExampleLanguage.EN,
                        critique="Bad 1",
                    ),
                    PolicyExample(
                        user_input="Bad 2",
                        response="Bad",
                        type=ExampleType.BAD,
                        language=ExampleLanguage.EN,
                        critique="Bad 2",
                    ),
                ],
            )


class TestPolicyPackContents:
    """Tests verifying the actual behavior_policies.yaml pack."""

    def test_all_25_situations_present_and_valid(self):
        loader = get_policy_loader(force_new=True)
        situations = loader.list_situations()

        for expected in EXPECTED_25_SITUATIONS:
            assert expected in situations, f"Missing required situation: {expected}"

        assert len(situations) == 25, f"Expected exactly 25 situations, got {len(situations)}"

    def test_each_card_has_required_structure(self):
        loader = get_policy_loader(force_new=True)

        for sit_id in EXPECTED_25_SITUATIONS:
            card = loader.get_policy(sit_id)
            assert card is not None, f"Card {sit_id} could not be retrieved"
            assert card.situation_id == sit_id
            assert len(card.triggers) >= 1
            assert len(card.objective) >= 10
            assert len(card.must) >= 1
            assert len(card.must_not) >= 1
            assert len(card.response_shape) >= 5
            assert len(card.coach_moves) >= 1
            assert card.owner in {"coaching_lead", "clinical_ops", "safety_board", "behavioral_health_lead"}
            assert card.version == "1.0.0"
            assert card.status == PolicyStatus.ACTIVE

            good_examples = card.good_examples
            bad_examples = card.bad_examples
            assert len(good_examples) >= 2, f"{sit_id} must have >= 2 good examples"
            assert len(bad_examples) >= 2, f"{sit_id} must have >= 2 bad examples"

            for ex in card.examples:
                assert len(ex.user_input) > 0
                assert len(ex.response) > 0
                assert len(ex.critique) >= 5
                assert ex.language in {ExampleLanguage.EN, ExampleLanguage.HI, ExampleLanguage.HINGLISH}

    def test_emergency_red_flag_invariants(self):
        loader = get_policy_loader(force_new=True)
        red_flag = loader.require_policy("red_flag")

        # Must mention 112 in rules
        has_112 = any("112" in m for m in red_flag.must)
        assert has_112, "red_flag card must mandate calling 112"

        # Must forbid home remedies or water
        has_forbidden_remedy = any("remedies" in mn.lower() or "water" in mn.lower() for mn in red_flag.must_not)
        assert has_forbidden_remedy, "red_flag card must forbid home remedies / water"

    def test_crisis_self_harm_invariants(self):
        loader = get_policy_loader(force_new=True)
        crisis = loader.require_policy("crisis_self_harm")

        # Must mention Tele-MANAS or KIRAN in rules
        has_telemanas = any("Tele-MANAS" in m or "14416" in m or "KIRAN" in m for m in crisis.must)
        assert has_telemanas, "crisis_self_harm card must mandate Tele-MANAS / 14416 / KIRAN"

    def test_pricing_factual_invariants(self):
        loader = get_policy_loader(force_new=True)
        pricing = loader.require_policy("pricing_product")

        # Must contain ₹0 free and ₹1,499 nutritionist plan
        assert any("₹0" in m or "free" in m.lower() for m in pricing.must)
        assert any("1,499" in m or "1499" in m for m in pricing.must)


class TestPolicyPackHotReload:
    """Tests verifying live file hot-reload and LKG resilience."""

    def test_hot_reload_on_file_modification(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src_file = Path("data/behavior_policies.yaml")
            test_file = Path(tmpdir) / "test_policies.yaml"
            shutil.copyfile(src_file, test_file)

            loader = PolicyPackLoader(policy_path=test_file, auto_load=True)
            original_policy = loader.get_policy("incomplete_message")
            assert original_policy is not None
            assert original_policy.version == "1.0.0"

            # Modify file content (update version to 1.1.0 and change objective)
            with open(test_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            data["policies"][0]["version"] = "1.1.0"
            data["policies"][0]["objective"] = "Updated hot-reloaded objective for incomplete messages."

            # Write back
            time.sleep(0.05)  # Ensure mtime tick
            with open(test_file, "w", encoding="utf-8") as f:
                yaml.dump(data, f)

            assert loader.is_modified() is True

            reloaded = loader.reload_if_modified()
            assert reloaded is True

            updated_policy = loader.get_policy("incomplete_message")
            assert updated_policy.version == "1.1.0"
            assert "Updated hot-reloaded objective" in updated_policy.objective

    def test_hot_reload_preserves_last_known_good_on_syntax_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src_file = Path("data/behavior_policies.yaml")
            test_file = Path(tmpdir) / "test_policies.yaml"
            shutil.copyfile(src_file, test_file)

            loader = PolicyPackLoader(policy_path=test_file, auto_load=True)
            assert len(loader.list_situations()) == 25
            good_red_flag = loader.get_policy("red_flag")
            assert good_red_flag is not None

            # Corrupt the file with invalid YAML syntax
            time.sleep(0.05)
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("corrupted: yaml: [unclosed list")

            assert loader.is_modified() is True

            # Attempt reload - should return False and keep LKG
            success = loader.reload_if_modified()
            assert success is False

            # Existing in-memory cache remains intact!
            assert len(loader.list_situations()) == 25
            preserved_red_flag = loader.get_policy("red_flag")
            assert preserved_red_flag == good_red_flag

    def test_hot_reload_preserves_lkg_on_schema_violation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src_file = Path("data/behavior_policies.yaml")
            test_file = Path(tmpdir) / "test_policies.yaml"
            shutil.copyfile(src_file, test_file)

            loader = PolicyPackLoader(policy_path=test_file, auto_load=True)
            assert len(loader.list_situations()) == 25

            # Corrupt file by removing good examples (violating min 2 requirement)
            with open(test_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            # Strip all good examples from first policy
            data["policies"][0]["examples"] = [ex for ex in data["policies"][0]["examples"] if ex["type"] == "bad"]

            time.sleep(0.05)
            with open(test_file, "w", encoding="utf-8") as f:
                yaml.dump(data, f)

            # Attempt reload - must fail validation and preserve LKG
            success = loader.reload_if_modified()
            assert success is False
            assert len(loader.list_situations()) == 25
            assert len(loader.get_policy("incomplete_message").good_examples) >= 2


class TestRetrievalAndPromptFormatting:
    """Tests for few-shot example retrieval and XML prompt construction."""

    def test_filter_examples_by_type_and_language(self):
        loader = get_policy_loader(force_new=True)

        good_hinglish = loader.get_examples("symptom_report", example_type="good", language="hinglish")
        assert len(good_hinglish) >= 1
        assert all(ex.type == ExampleType.GOOD for ex in good_hinglish)
        assert all(ex.language == ExampleLanguage.HINGLISH for ex in good_hinglish)

        bad_examples = loader.get_examples("symptom_report", example_type="bad")
        assert len(bad_examples) >= 2
        assert all(ex.type == ExampleType.BAD for ex in bad_examples)

    def test_format_situation_prompt_structure(self):
        loader = get_policy_loader(force_new=True)

        prompt = loader.format_situation_prompt("diet_exercise", include_examples=True, max_examples=2)
        assert '<SITUATION_POLICY id="diet_exercise"' in prompt
        assert "<OBJECTIVE>" in prompt
        assert "<RESPONSE_SHAPE>" in prompt
        assert "<RULES>" in prompt
        assert "- MUST:" in prompt
        assert "- MUST NOT:" in prompt
        assert "<RECOMMENDED_COACH_MOVES>" in prompt
        assert "<FEW_SHOT_GUIDANCE>" in prompt
        assert '<EXAMPLE id="1"' in prompt
        assert "<PATIENT>" in prompt
        assert "<COACH>" in prompt
        assert "<RATIONALE>" in prompt
        assert "</SITUATION_POLICY>" in prompt

    def test_format_situation_prompt_without_examples(self):
        loader = get_policy_loader(force_new=True)

        prompt = loader.format_situation_prompt("small_talk", include_examples=False)
        assert '<SITUATION_POLICY id="small_talk"' in prompt
        assert "<FEW_SHOT_GUIDANCE>" not in prompt
        assert "</SITUATION_POLICY>" in prompt

    def test_match_situation_trigger_heuristics(self):
        loader = get_policy_loader(force_new=True)

        # Cardiac red flag
        cardiac = loader.match_situation("Mujhe seene mein tez dard ho raha hai aur baayein haath mein khinchaav hai")
        assert cardiac is not None
        assert cardiac.situation_id == "red_flag"

        # Crisis self harm
        crisis = loader.match_situation("I want to kill myself, I have no reason to live")
        assert crisis is not None
        assert crisis.situation_id == "crisis_self_harm"

        # Medication dose change
        med = loader.match_situation("kya main apni dawa ki dose badha doon?")
        assert med is not None
        assert med.situation_id == "medication_dose"

        # Abusive user
        abuse = loader.match_situation("tum bekar ho aur stupid idiot ho")
        assert abuse is not None
        assert abuse.situation_id == "abusive_user"

        # Privacy
        privacy = loader.match_situation("kya mera data safe hai aur encrypted hai?")
        assert privacy is not None
        assert privacy.situation_id == "privacy_request"

        # Pricing
        pricing = loader.match_situation("disha ka charge kitna hai?")
        assert pricing is not None
        assert pricing.situation_id == "pricing_product"

        # Incomplete / cutoff
        incomplete = loader.match_situation("aur phir...")
        assert incomplete is not None
        assert incomplete.situation_id == "incomplete_message"


class TestThreadSafety:
    """Verify thread safety during high-frequency concurrent queries and hot reloads."""

    def test_concurrent_access_during_reload(self):
        loader = get_policy_loader(force_new=True)
        errors: list[Exception] = []
        stop_event = threading.Event()

        def reader_worker():
            while not stop_event.is_set():
                try:
                    p = loader.get_policy("progress_wins")
                    assert p is not None
                    exs = loader.get_examples("progress_wins", "good")
                    assert len(exs) >= 2
                except Exception as e:
                    errors.append(e)

        def reloader_worker():
            for _ in range(20):
                try:
                    loader.reload(force=True)
                    time.sleep(0.01)
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=reader_worker) for _ in range(5)]
        reloader = threading.Thread(target=reloader_worker)

        for t in threads:
            t.start()
        reloader.start()

        reloader.join()
        stop_event.set()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Encountered thread safety errors: {errors}"
