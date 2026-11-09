# Knowledge inventory and trust status

## What the repository establishes

The live general-knowledge source is `clinical_knowledge_base`, exposed to the retriever through `clinical_guideline_chunks`. Chat/voice retrieval accepts only records marked `approved`. Search currently uses PostgreSQL full-text and trigram similarity; it is not vector search.

The repository includes SQL seeds and ingestion scripts with examples of nutrition, exercise, and lifestyle guidance. Their presence, source labels, citations, record counts, and clinical-sounding prose do not establish that the source was fetched correctly, licensed for this use, reviewed by a qualified person, or currently present in a live database. New seed/imported health content is now draft, not approved.

## Trust boundaries

| Data | Source of truth | Current limitation |
|---|---|---|
| General food, nutrition, exercise, remedies, and lifestyle knowledge | Approved knowledgebase records | Live content and approval provenance have not been audited. Existing seed prose is not proof of clinical review. |
| User's prescribed meals | User's active approved `patient_diet_schedules` records | This is distinct from general meal guidance. No generic fallback should be represented as the user's prescription. |
| Preferences, dislikes, conditions, symptoms, limitations, and goals | User profile, PEP, and persisted user facts | Missing data must remain missing; do not infer Vegetarian or another preference. |
| Food composition, recipe portions, calories, and nutrient totals | A verified structured food/recipe source would be required | The repository does not establish a validated runtime service capable of exact meal composition or nutrient calculation. |
| Exercise suitability | Approved retrieved exercise knowledge plus user context and deterministic safety gates | The former static catalogue and canned alternatives were removed. The safety helper blocks explicit recorded restrictions and otherwise abstains; it is not a complete exercise eligibility engine. |
| Provenance | Retrieved chunk IDs and retrieval status surfaced in chat/voice responses | The UI displays raw IDs/status; source citation text is not returned. IDs identify supplied records but do not prove that every generated statement is entailed by them. |

## Retired/unverified claims

Older versions of this inventory described dataset sizes, licenses, exact nutrition values, remedies, exercise prescriptions, “verified” source status, and broad clinical coverage. Those claims were not validated by this code audit and must not be used as evidence of current corpus contents, legal permission, medical review, or product capability. In particular:

- Do not claim exact calories or macros from illustrative meal examples.
- Do not treat all bundled records as approved. Seed/import scripts must leave them draft until actual review.
- Do not treat a named public authority or a populated `source_citation` field as proof that a record accurately reflects that authority.
- Do not route prescribed meal questions to general nutrition chunks.
- Do not infer suitability from the exercise safety helper; it does not choose routines or alternatives.

## Approval requirements before production

1. Inventory the deployed database's actual records and status, including source provenance and reviewer identity.
2. Verify source text, license, attribution, language, and freshness for each record.
3. Use a real review/approval workflow; do not rely on placeholder reviewer IDs or seed status.
4. Validate retrieval relevance and user-context filters against the actual corpus.
5. Add claim-level grounding and domain-specific food/exercise suitability evidence before claiming personalized recommendations.

See [RAG ingestion and retrieval](../architecture/04_rag_ingestion_and_retrieval.md) and [the hardcode audit ledger](./HARDCODE_AUDIT.md) for implementation details and unresolved risks.
