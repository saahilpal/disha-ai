# Dialogue-State Perception Schema

To enable robust perception of user intents and dialogue acts, Disha processes inbound utterances into a structured schema:

```json
{
  "dialogue_act": "answer | refusal | acknowledgement | correction | new_topic | question | disclosure | greeting",
  "referent": "string (e.g., 'sleep', 'diet', 'alcohol', 'exercise', 'previous_question')",
  "sentiment": "positive | neutral | negative | distressed",
  "extracted_entities": {
    "food_items": [],
    "habits": [],
    "time_references": [],
    "symptoms": []
  },
  "clinical_risk_flag": false,
  "confidence": 0.95
}
```

## Dialogue Act Definitions
- **greeting**: Initial user salutation (e.g., "hi", "hello").
- **answer**: Direct response to a previous coach inquiry.
- **refusal**: Rejection of a suggestion or topic (e.g., "no", "nahi karna").
- **acknowledgement**: Brief confirmation (e.g., "okay", "haan", "hmm").
- **correction**: Rectifying a misunderstood fact or preference.
- **new_topic**: Shifting discussion to a completely different domain (e.g., sleep to diet).
- **question**: Inquiring about health, food, or coaching rules.
- **disclosure**: Sharing personal health habits, challenges, or lifestyle details (e.g., "mai daaru peeta hoo").
