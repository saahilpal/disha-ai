"""Add knowledge_sources, knowledge_chunks with provenance, and product_facts tables

Revision ID: 0003_knowledge_and_product_facts
Revises: 0002_memory_and_pep
Create Date: 2026-11-08 23:30:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0003_knowledge_and_product_facts"
down_revision: Union[str, None] = "0002_memory_and_pep"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Knowledge Sources Table (Authoritative Provenance)
    op.execute("""
    CREATE TABLE IF NOT EXISTS knowledge_sources (
        id VARCHAR(64) PRIMARY KEY,
        name TEXT NOT NULL,
        license VARCHAR(128) NOT NULL,
        url TEXT,
        version VARCHAR(64) NOT NULL,
        ingest_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        language VARCHAR(32) NOT NULL DEFAULT 'en',
        domain VARCHAR(64) NOT NULL,
        trust_tier VARCHAR(16) NOT NULL CHECK (trust_tier IN ('tier_1', 'tier_2', 'tier_3'))
    );
    CREATE INDEX IF NOT EXISTS idx_ksources_domain ON knowledge_sources(domain);
    CREATE INDEX IF NOT EXISTS idx_ksources_trust ON knowledge_sources(trust_tier);
    """)

    # 2. Seed Baseline Knowledge Sources
    op.execute("""
    INSERT INTO knowledge_sources (id, name, license, url, version, language, domain, trust_tier)
    VALUES 
        ('src_icmr_nin_2024', 'ICMR-NIN 2024 Dietary Guidelines for Indians', 'GODL-India', 'https://www.nin.res.in/dietaryguidelines/', '2024.1', 'en', 'dietary_guidelines', 'tier_1'),
        ('src_ifct_2017', 'ICMR-NIN Indian Food Composition Tables 2017', 'GODL-India', 'https://www.nin.res.in/ifct/', '2017.1', 'en', 'food_composition', 'tier_1'),
        ('src_ayush_remedies_2024', 'Ayurvedic Pharmacopoeia of India (API) & Evidence-Based Home Remedies', 'CC-BY-4.0', 'https://ayush.gov.in/', 'API-IX', 'sa', 'ayush_integrative_health', 'tier_1'),
        ('src_mohfw_protocols', 'MoHFW National Health Portal Treatment Protocols', 'GODL-India', 'https://www.nhp.gov.in/', '2023.2', 'hi', 'clinical_medicine', 'tier_1'),
        ('src_who_cvd_diabetes_2021', 'WHO Primary Care Guidelines for Hypertension & Type-2 Diabetes', 'CC BY-NC-SA 3.0 IGO', 'https://www.who.int/publications/i/item/9789240033986', '2021.1', 'en', 'preventive_cardiology', 'tier_1'),
        ('src_hf_pcos_nutrition_2024', 'Hugging Face PCOS Indian Diet & Clinical Nutrition Guidelines', 'Apache-2.0', 'https://huggingface.co/datasets/Khyatimirani/pcos-indian-diet-guidelines', '2024.1', 'en', 'womens_health', 'tier_2'),
        ('src_emergency_redflags_100', 'Disha 100-Utterance Red-Flag Acute Clinical Emergency Benchmark', 'Internal Proprietary', 'local://tests/fixtures/emergency_red_flags_100.json', '2.1', 'hinglish', 'emergency_triage', 'tier_1'),
        ('src_golden_corpus_2703', 'Disha AI 25-Scenario Multi-Turn Clinical Quality Golden Corpus', 'Internal Development Asset', 'local://disha_core/tests/golden_corpus_2703.jsonl', '4.0', 'hinglish', 'evaluation', 'tier_3')
    ON CONFLICT (id) DO UPDATE SET
        name = EXCLUDED.name,
        license = EXCLUDED.license,
        url = EXCLUDED.url,
        version = EXCLUDED.version,
        language = EXCLUDED.language,
        domain = EXCLUDED.domain,
        trust_tier = EXCLUDED.trust_tier;
    """)

    # 3. Knowledge Chunks Table (Granular Content with Provenance)
    op.execute("""
    CREATE TABLE IF NOT EXISTS knowledge_chunks (
        id BIGSERIAL PRIMARY KEY,
        source_id VARCHAR(64) NOT NULL REFERENCES knowledge_sources(id) ON DELETE RESTRICT,
        domain VARCHAR(64) NOT NULL,
        condition_tags TEXT[] NOT NULL DEFAULT '{}',
        diet_tags TEXT[] NOT NULL DEFAULT '{}',
        language VARCHAR(32) NOT NULL DEFAULT 'hinglish',
        script VARCHAR(32) NOT NULL DEFAULT 'latin',
        content TEXT NOT NULL CHECK (btrim(content) <> ''),
        fts_vector tsvector GENERATED ALWAYS AS (to_tsvector('simple'::regconfig, content)) STORED,
        embedding REAL[] DEFAULT NULL,
        derived BOOLEAN NOT NULL DEFAULT FALSE
    );
    CREATE INDEX IF NOT EXISTS idx_kchunks_source ON knowledge_chunks(source_id);
    CREATE INDEX IF NOT EXISTS idx_kchunks_domain ON knowledge_chunks(domain);
    CREATE INDEX IF NOT EXISTS idx_kchunks_fts ON knowledge_chunks USING GIN(fts_vector);
    CREATE INDEX IF NOT EXISTS idx_kchunks_condition_tags ON knowledge_chunks USING GIN(condition_tags);
    CREATE INDEX IF NOT EXISTS idx_kchunks_diet_tags ON knowledge_chunks USING GIN(diet_tags);
    """)

    # 4. Migrate Existing Guideline Chunks from clinical_knowledge_base to knowledge_chunks
    op.execute("""
    INSERT INTO knowledge_chunks (
        source_id,
        domain,
        condition_tags,
        diet_tags,
        language,
        script,
        content,
        derived
    )
    SELECT 
        CASE 
            WHEN c.source_citation ILIKE '%HuggingFace%' OR c.condition_tag ILIKE 'PCOS%' 
                THEN 'src_hf_pcos_nutrition_2024'
            WHEN c.source_citation ILIKE '%Ayurvedic%' OR c.condition_tag ILIKE 'AYUSH%' OR c.source_citation ILIKE '%AYUSH%'
                THEN 'src_ayush_remedies_2024'
            WHEN c.source_citation ILIKE '%National Health Portal%' OR c.source_citation ILIKE '%MoHFW%'
                THEN 'src_mohfw_protocols'
            WHEN c.source_citation ILIKE '%WHO%'
                THEN 'src_who_cvd_diabetes_2021'
            ELSE 'src_icmr_nin_2024'
        END AS source_id,
        CASE 
            WHEN c.condition_tag ILIKE 'PCOS%' THEN 'womens_health'
            WHEN c.condition_tag ILIKE 'AYUSH%' OR c.condition_tag ILIKE 'REMEDY_%' THEN 'ayush_integrative_health'
            WHEN c.condition_tag ILIKE 'HYPERTENSION%' OR c.condition_tag ILIKE 'CHOLESTEROL%' THEN 'cardiovascular'
            WHEN c.condition_tag ILIKE 'T2D%' THEN 'metabolic_health'
            WHEN c.condition_tag ILIKE 'GI_%' OR c.condition_tag ILIKE 'GERD%' OR c.condition_tag ILIKE 'CONSTIPATION%' THEN 'gastrointestinal'
            ELSE 'clinical_nutrition'
        END AS domain,
        ARRAY[c.condition_tag]::TEXT[] AS condition_tags,
        CASE 
            WHEN c.condition_tag ILIKE '%DIET%' OR c.condition_tag ILIKE '%SALT%' OR c.condition_tag ILIKE '%FRUIT%' OR c.condition_tag ILIKE '%FIBER%'
                THEN ARRAY['dietary_guideline']::TEXT[]
            ELSE '{}'::TEXT[]
        END AS diet_tags,
        'hinglish' AS language,
        'latin' AS script,
        c.guideline_content AS content,
        FALSE AS derived
    FROM clinical_knowledge_base c
    WHERE NOT EXISTS (
        SELECT 1 FROM knowledge_chunks k WHERE k.content = c.guideline_content
    );
    """)

    # 5. Product Facts Table (Commercial Pricing, Channels, Clearances)
    op.execute("""
    CREATE TABLE IF NOT EXISTS product_facts (
        fact_key VARCHAR(64) PRIMARY KEY,
        category VARCHAR(64) NOT NULL,
        title VARCHAR(128) NOT NULL,
        fact_value JSONB NOT NULL,
        description TEXT,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_product_facts_category ON product_facts(category);
    """)

    # 6. Seed Product Facts
    op.execute("""
    INSERT INTO product_facts (fact_key, category, title, fact_value, description)
    VALUES 
        ('pricing_followup_consultations', 'pricing', 'Follow-up Consultations Pricing', '{"amount": 0, "currency": "INR", "interval": "per_consultation", "statement": "Follow-up consultations ₹0 hain."}'::jsonb, 'Disha AI coaching follow-ups are free.'),
        ('pricing_dedicated_nutritionist', 'pricing', 'Dedicated Human Nutritionist Plan Pricing', '{"amount": 1499, "currency": "INR", "interval": "monthly", "statement": "dedicated nutritionist plan ₹1,499 per month hai."}'::jsonb, 'Dedicated nutritionist plan is ₹1,499 per month.'),
        ('channel_delivery_policy', 'access_channel', 'Application Delivery Channel Policy', '{"allowed_channel": "app_my_plan_tab", "forbidden_channels": ["whatsapp", "sms", "email", "telegram"], "statement": "Aap apna plan sirf app ke ''My Plan'' tab mein dekh sakte hain."}'::jsonb, 'Plans delivered in My Plan tab.'),
        ('persona_identity', 'identity', 'Disha AI Persona Statement', '{"name": "Disha", "role": "AI Health Coach", "is_doctor": false, "is_human": false, "statement": "Main Disha hoon, aapki AI health coach."}'::jsonb, 'AI Coach identity boundary.'),
        ('clinical_diagnosis_policy', 'clinical_boundary', 'Medical Diagnosis Boundary', '{"statement": "Main ek AI coach hoon aur koi medical diagnosis nahi de sakti; kripya diagnosis ke liye clinician se consult karein."}'::jsonb, 'Cannot provide medical diagnosis.'),
        ('clinical_prescription_policy', 'clinical_boundary', 'Pharmaceutical Prescription Boundary', '{"statement": "Main dawaiyon ki dose ya prescription badalne ke liye authorized nahi hoon; kripya apne prescribing clinician se salah lein."}'::jsonb, 'Cannot alter medication doses.'),
        ('emergency_helpline_national', 'emergency_helpline', 'National Emergency Ambulance Helpline', '{"service": "National Emergency Services", "number": "112", "statement": "Yeh emergency ho sakti hai. Abhi 112 par call karein."}'::jsonb, 'National 112 emergency service.'),
        ('emergency_helpline_telemanas', 'emergency_helpline', 'Tele-MANAS Mental Health Helpline', '{"service": "Tele-MANAS National Tele-Mental Health Programme", "number": "14416", "statement": "Tele-MANAS se 14416 par bhi baat kar sakte hain."}'::jsonb, 'Tele-MANAS 14416 helpline.'),
        ('pep_clearance_hypertension_stage1', 'exercise_clearance', 'PEP Policy for Stage 1 Hypertension', '{"condition": "hypertension_stage1", "gym_clearance": false, "allowed": ["brisk walking", "gentle yoga", "stretching", "breathing exercises", "light cycling"], "restricted": ["heavy deadlifts", "max weight lifting", "valsalva maneuver", "high-intensity sprinting"]}'::jsonb, 'Stage 1 HTN clearance policy.'),
        ('pep_clearance_cardiac_severe', 'exercise_clearance', 'PEP Policy for Severe HTN / Cardiac History', '{"condition": "cardiac_or_severe_hypertension", "gym_clearance": false, "allowed": ["brisk walking"], "restricted": ["heavy weightlifting", "heavy deadlifts", "hiit", "high intensity sprints", "valsalva maneuver"]}'::jsonb, 'High risk cardiac contraindications.'),
        ('pep_clearance_healthy_adult', 'exercise_clearance', 'PEP Policy for Unrestricted Healthy Adults', '{"condition": "healthy_unrestricted", "gym_clearance": true, "allowed": ["brisk walking", "jogging", "swimming", "cycling", "moderate strength training"], "restricted": []}'::jsonb, 'Unrestricted adult clearance.'),
        ('diet_vegetarian_guardrail', 'diet_rules', 'Vegetarian Dietary Invariant Guardrail', '{"forbidden": ["chicken", "mutton", "fish", "meat", "poultry", "seafood", "prawns", "beef", "pork", "eggs"], "default_substitutes": ["paneer ya tofu", "sprouts", "moong dal"]}'::jsonb, 'Vegetarian food substitution rules.'),
        ('diet_template_jain', 'diet_template', 'Jain Dietary 7-Day Meal Protocol', '{"breakfast": "2 moong dal chillas with mint chutney (no root veg) and a small bowl of curd (approx 280 kcal)", "lunch": "1 bowl yellow moong dal, 2 phulkas, steamed lauki sabzi, and fresh cucumber salad (approx 420 kcal)", "dinner": "150g fresh paneer sabzi (jain prep), 2 multigrain rotis, and bottle gourd soup (approx 400 kcal)"}'::jsonb, 'Jain meal protocol.'),
        ('diet_template_vegetarian', 'diet_template', 'Standard Indian Vegetarian 7-Day Meal Protocol', '{"breakfast": "2 moong dal chillas with mint chutney and a small bowl of curd (approx 280 kcal)", "lunch": "1 bowl dal tadka, 2 multigrain rotis, steamed seasonal vegetables, and cucumber raita (approx 450 kcal)", "dinner": "150g paneer bhurji, 2 multigrain rotis, and cucumber salad (approx 420 kcal)"}'::jsonb, 'Vegetarian meal protocol.'),
        ('diet_template_non_vegetarian', 'diet_template', 'High-Protein Non-Vegetarian 7-Day Meal Protocol', '{"breakfast": "2 boiled eggs or egg scramble with whole wheat toast and sauteed greens (approx 290 kcal)", "lunch": "1 bowl grilled chicken curry/dal with 1 cup brown rice and cucumber-tomato salad (approx 460 kcal)", "dinner": "150g grilled chicken/paneer with steamed broccoli, carrots, and 1 multigrain roti (approx 410 kcal)"}'::jsonb, 'Non-vegetarian meal protocol.')
    ON CONFLICT (fact_key) DO UPDATE SET
        fact_value = EXCLUDED.fact_value,
        description = EXCLUDED.description,
        updated_at = NOW();
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS product_facts CASCADE;")
    op.execute("DROP TABLE IF EXISTS knowledge_chunks CASCADE;")
    op.execute("DROP TABLE IF EXISTS knowledge_sources CASCADE;")
