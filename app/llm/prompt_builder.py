from typing import List, Dict, Any, Optional

SYSTEM_CORE_PROMPT = """You are Disha, an AI health coach conducting a proactive follow-up voice call with a patient.
You work alongside the patient's doctors and dietitians to guide healthy lifestyle habits.

CORE INVARIANTS (NON-NEGOTIABLE):
1. AI IDENTITY: If asked whether you are a human or a robot, you MUST explicitly state you are an AI health coach. Never claim to be human.
2. DELIVERY CHANNELS: Never promise to send anything via WhatsApp, SMS, or Email. All diet plans and records exist inside the Disha Mobile App.
3. CONVERSATIONAL HINGLISH: Speak naturally in everyday Romanized Hinglish (code-mixed Hindi and English) with warm bedside empathy.
4. BREVITY: Keep your answer to 1-2 conversational sentences (15-35 words max). Never use bullet points, bold tags, or asterisks.
5. GROUNDING & UNCERTAINTY: If information requested by the user is NOT present in VERIFIED SYSTEM FACTS below, do NOT guess. State politely that the record is being reviewed in the Disha app.
"""

class PromptBuilder:
    """Constructs strictly bounded, de-identified turn prompts (<320 tokens)."""

    @classmethod
    def build_turn_prompt(
        cls,
        patient_first_name: str,
        pep_profile: Dict[str, Any],
        retrieved_facts: List[str],
        user_utterance: str,
        dialogue_history: Optional[List[Dict[str, str]]] = None
    ) -> List[Dict[str, str]]:
        """
        Builds the messages array for the chat completion request.
        """
        # Context block
        pep_summary = (
            f"Dietary: {pep_profile.get('dietary_preference', 'Vegetarian')}, "
            f"Approved Exercise: {', '.join(pep_profile.get('allowed_exercise', ['home']))}"
        )
        
        facts_summary = "\n".join(f"- {f}" for f in retrieved_facts) if retrieved_facts else "- No specific medical remedy triggered for this turn."

        system_content = f"""{SYSTEM_CORE_PROMPT}

PATIENT PROFILE:
- Name: {patient_first_name}
- PEP Constraints: {pep_summary}

VERIFIED SYSTEM FACTS (GROUND TRUTH):
{facts_summary}
"""

        messages = [{"role": "system", "content": system_content}]

        # Rolling history (last 2 turns)
        if dialogue_history:
            for turn in dialogue_history[-2:]:
                messages.append(turn)

        # Untrusted user transcript enclosed in XML tags
        messages.append({
            "role": "user",
            "content": f"<user_untrusted_transcript>\n{user_utterance}\n</user_untrusted_transcript>"
        })

        return messages

