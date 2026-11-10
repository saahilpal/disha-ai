# Behavior Spec v1 — Enforcement Matrix

- **Date:** 2026-11-10
- **Version:** v1 (Commit on `feat/behavior-spec-v1`)
- **Root System Prompt File:** `disha_core/llm/client.py:14-53`
- **Root System Prompt Size:** 2,341 characters, 363 words, ~585 estimated tokens (chars÷4 method)
- **Hash / Version:** `PROMPT_VERSION = "v1-9f113b222df1"` (derived from `data/behavior_rules.yaml`)

---

## 1. Summary Counts
- **VERIFIED:** 18 rules (P1-P6, F1-F5, C1-C4, M1-M3) + 4 decisions (D2-D5)
- **PARTIAL:** 0
- **NOT IMPLEMENTED:** 0
- **CONTRADICTED:** 0

---

## 2. Rule Enforcement Mapping

| Rule ID | Rule Text Summary | Enforcement Layer & File:Line | Test Coverage | Status | Notes |
|---|---|---|---|---|---|
| **P1** | Warm, curious, clinically smart | Root System Prompt (`client.py:35-47`) rendered from `data/behavior_rules.yaml:8-10` | `tests/test_behavior_spec_v1.py::test_all_18_rule_ids_present_in_rendered_prompt` | **VERIFIED** | Present in rendered prompt at import time |
| **P2** | Approachable Health Coach, not formal bot | Root System Prompt (`client.py:35-47`) + identity invariant in `validator.py:118-124` | `tests/test_invariants.py::test_claims_to_be_doctor_or_human_rejected` | **VERIFIED** | Enforced in prompt and deterministic validator |
| **P3** | Natural Hinglish default; English & Hindi supported | Prompt injection (`client.py:113-125`) + Verifier `check_p3_language_mode` in `verifier.py:369-399` | `tests/test_behavior_spec_v1.py::test_p3_hinglish_rejects_devanagari`, `test_p3_english_rejects_hindi_words` | **VERIFIED** | Deterministic script and loanword validation per mode |
| **P4** | No honorifics ("Ji sir/ma'am"), no corporate templates | Prompt rule `[P4]` + Verifier `check_p4_honorifics` in `verifier.py:402-411` | `tests/test_behavior_spec_v1.py::test_p4_banned_honorifics` | **VERIFIED** | Multilingual banned regex compiled from i18n data |
| **P5** | Dynamic adaptation, no static scripts | Root System Prompt (`client.py:35-47`) + removed all static canned deflections | `tests/test_behavior_spec_v1.py::test_all_18_rule_ids_present_in_rendered_prompt` | **VERIFIED** | Static fallback strings replaced with LLM repair |
| **P6** | No lengthy paragraphs, fast WhatsApp exchange feel | Prompt rule `[P6]` + Verifier `check_p6_f3_length` in `verifier.py:414-431` (≤3 sents, ≤450 chars) | `tests/test_behavior_spec_v1.py::test_p6_f3_max_3_sentences`, `test_p6_f3_allows_1_to_3_sentences` | **VERIFIED** | Multilingual sentence splitter handles `.` `?` `!` `।` `\n` |
| **F1** | Zero-echo: never repeat user facts (e.g. weight) | Prompt rule `[F1]` + Verifier `check_f1_zero_echo` in `verifier.py:434-473` | `tests/test_behavior_spec_v1.py::test_f1_zero_echo_user_facts`, `test_f1_zero_echo_prefix` | **VERIFIED** | Cross-script entity and echo clause regex matching |
| **F2** | At most ONE question per response | Prompt rule `[F2]` + Verifier `check_f2_at_most_one_question` in `verifier.py:476-485` | `tests/test_behavior_spec_v1.py::test_f2_at_most_one_question`, `test_f2_allows_single_question` | **VERIFIED** | Strictly enforces `count("?") <= 1` across whole turn |
| **F3** | 1-3 sentences maximum; no boilerplate phrasing | Prompt rule `[F3]` + Verifier `check_p6_f3_length` in `verifier.py:414-431` | `tests/test_behavior_spec_v1.py::test_p6_f3_max_3_sentences` | **VERIFIED** | Whole-draft chat verification enforces 1-3 sentences |
| **F4** | Selective empathy: only on distress/struggle | Prompt rule `[F4]` + Verifier `check_f4_selective_empathy` in `verifier.py:488-506` | `tests/test_behavior_spec_v1.py::test_f4_selective_empathy_disallows_boilerplate_without_distress` | **VERIFIED** | Gated on `distress_expressed` flag from perception |
| **F5** | Forward motion toward clinical evaluation | Prompt rule `[F5]` + Move selector `select_move` in `perception.py:72-108` | `tests/test_behavior_spec_v1.py::test_precedence_triangle_question_before_insight` | **VERIFIED** | Deterministic move order progresses turn by turn |
| **C1** | History Triangle: Duration, Past attempts, Severity | Move selector in `perception.py:84-88` + `harness.py:488-512` | `tests/test_behavior_spec_v1.py::test_precedence_triangle_question_before_insight`, `test_precedence_clinical_insight_only_after_triangle_complete` | **VERIFIED** | Next unanswered triangle axis asked before clinical insight |
| **C2** | No advice on chat (meds, diagnosis, treatment) | Prompt rule `[C2]` + Verifier `check_c2_clinical_boundary` in `verifier.py:509-543` + `data/c2_boundary.yaml` | `tests/test_behavior_spec_v1.py::test_c2_boundary_medication_dose_forbidden`, `test_c2_boundary_diagnosis_forbidden`, `test_c2_boundary_treatment_plan_forbidden` | **VERIFIED** | Disallows specific dosages, diagnoses, and treatment plans |
| **C3** | Emergency red flags immediate referral | Deterministic Breaker `EmergencyBreaker.check()` in `breaker.py:72-105` (<5ms) | `tests/test_behavior_spec_v1.py::test_c3_emergency_red_flag_preempts_everything` | **VERIFIED** | 100% recall on red_flags.yaml; 112 referral returned |
| **C4** | Pivot toward 10-minute expert call | Prompt rule `[C4]` + Move selector in `perception.py:107` + CTA UI in `app.js` | `tests/test_behavior_spec_v1.py::test_precedence_medication_inquiry_withholds_and_pivots` | **VERIFIED** | Recommends expert call when triangle is complete or meds asked |
| **M1** | Retain state and context; user never repeats facts | Unified database persistence (`main.py:470-600`, `chat_service.py:170-320`) | `tests/test_behavior_spec_v1.py::TestBehaviorSpecPromptAndRules` | **VERIFIED** | Messages, conversation entity, and dialogue state in DB |
| **M2** | Ambiguity handler: clarify vague answers first | Move selector in `perception.py:80-82` (`answer_quality in ('vague', 'incomplete')`) | `tests/test_behavior_spec_v1.py::test_precedence_clarify_vague_answer` | **VERIFIED** | Clarification takes precedence over triangle questions |
| **M3** | All guardrails live in the root system prompt | Single source `data/behavior_rules.yaml` renders `SYSTEM_PROMPT` in `client.py:33-53` | `tests/test_behavior_spec_v1.py::test_all_18_rule_ids_present_in_rendered_prompt`, `test_prompt_token_budget_under_600_tokens` | **VERIFIED** | Rendered prompt contains all 18 rule IDs and is ≤600 tokens |

---

## 3. Decided Defaults & Architectural Policies (D2–D5)

| Decision | Policy Statement | Code Location | Status | Notes |
|---|---|---|---|---|
| **D2** | F1 Zero-echo applies strictly. `confirm_critical_values` config flag exists (default OFF). | `config.py:59`, `verifier.py:434-473` | **VERIFIED** | Safety risk of leaving OFF documented in `IMPLEMENTATION_NOTES.md` |
| **D3** | C2 boundary lives in editable table: forbidden vs allowed. | `data/c2_boundary.yaml`, `verifier.py:509-543` | **VERIFIED** | Lifestyle info allowed after C1; medications/diagnoses strictly forbidden |
| **D4** | 10-minute expert call is configurable CTA in `product_facts` (`is_active=FALSE` by default). Recommended in words only if unconfigured. | `seed_product_facts.sql:107-117`, `app.js:2830-2850` | **VERIFIED** | Unconfigured status confirmed; no fake booking capabilities promised |
| **D5** | Silent language switch after 2 consecutive messages in another supported language. | `harness.py:618-632`, `config.py:60` | **VERIFIED** | Updates `patient_profiles` and `patient_pep` without verbal interruption |

