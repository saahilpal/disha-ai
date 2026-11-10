# Baseline Failure Replay Analysis (Section 3)

## Transcript Replay
1. **User**: `hi`
   - **Agent Behavior**: Delivered a rigid profile lecture and onboarding interrogation.
   - **Failure Analysis**: Violated conversational flow and greeting rules; treated the user like a form-filling questionnaire instead of meeting them with natural warmth.
2. **User**: `no`
   - **Agent Behavior**: Ignored refusal, continued pushing questionnaire.
   - **Failure Analysis**: Failed to detect user refusal/pushback; lack of motivational interviewing (MI) reflection.
3. **User**: `unrelated sleep`
   - **Agent Behavior**: Ignored topic shift, gave generic advice.
   - **Failure Analysis**: Failed new-topic perception schema and context continuity; dropped user focus.
4. **User**: `what should i eat`
   - **Agent Behavior**: Generic ungrounded advice.
   - **Failure Analysis**: Failed clinical grounding and personalization rules.
5. **User**: `no`
   - **Agent Behavior**: Repeated generic advice or ignored.
   - **Failure Analysis**: Lack of empathetic pacing.
6. **User**: `abhi toh 3 baj rhe hai`
   - **Agent Behavior**: Ignored time-disclosure context.
   - **Failure Analysis**: Failed to adjust to night-shift / atypical schedule context.
7. **User**: `yes mai daaru peeta hoo`
   - **Agent Behavior**: Judgmental or generic lecturing.
   - **Failure Analysis**: Violated non-judgmental stance (SDT relatedness / MI spirit) and failed to explore lifestyle disclosure supportively.

## Root Causes
- Lack of structured dialogue-act extraction per turn.
- Over-reliance on static prompt instructions without dynamic policy-card routing.
- Failure to respect user refusals and topic shifts.
