-- Disha AI Core: Knowledge Sources & Chunks Schema and Seed
-- Tables: knowledge_sources, knowledge_chunks

-- 1. Knowledge Sources Table
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

-- Seed Registered Authoritative Sources
INSERT INTO knowledge_sources (id, name, license, url, version, language, domain, trust_tier)
VALUES 
    (
        'src_icmr_nin_2024',
        'ICMR-NIN 2024 Dietary Guidelines for Indians',
        'GODL-India',
        'https://www.nin.res.in/dietaryguidelines/',
        '2024.1',
        'en',
        'dietary_guidelines',
        'tier_1'
    ),
    (
        'src_ifct_2017',
        'ICMR-NIN Indian Food Composition Tables 2017',
        'GODL-India',
        'https://www.nin.res.in/ifct/',
        '2017.1',
        'en',
        'food_composition',
        'tier_1'
    ),
    (
        'src_ayush_remedies_2024',
        'Ayurvedic Pharmacopoeia of India (API) & Evidence-Based Home Remedies',
        'CC-BY-4.0',
        'https://ayush.gov.in/',
        'API-IX',
        'sa',
        'ayush_integrative_health',
        'tier_1'
    ),
    (
        'src_mohfw_protocols',
        'MoHFW National Health Portal Treatment Protocols',
        'GODL-India',
        'https://www.nhp.gov.in/',
        '2023.2',
        'hi',
        'clinical_medicine',
        'tier_1'
    ),
    (
        'src_who_cvd_diabetes_2021',
        'WHO Primary Care Guidelines for Hypertension & Type-2 Diabetes',
        'CC BY-NC-SA 3.0 IGO',
        'https://www.who.int/publications/i/item/9789240033986',
        '2021.1',
        'en',
        'preventive_cardiology',
        'tier_1'
    ),
    (
        'src_hf_pcos_nutrition_2024',
        'Hugging Face PCOS Indian Diet & Clinical Nutrition Guidelines',
        'Apache-2.0',
        'https://huggingface.co/datasets/Khyatimirani/pcos-indian-diet-guidelines',
        '2024.1',
        'en',
        'womens_health',
        'tier_2'
    ),
    (
        'src_emergency_redflags_100',
        'Disha 100-Utterance Red-Flag Acute Clinical Emergency Benchmark',
        'Internal Proprietary',
        'local://tests/fixtures/emergency_red_flags_100.json',
        '2.1',
        'hinglish',
        'emergency_triage',
        'tier_1'
    ),
    (
        'src_golden_corpus_2703',
        'Disha AI 25-Scenario Multi-Turn Clinical Quality Golden Corpus',
        'Internal Development Asset',
        'local://disha_core/tests/golden_corpus_2703.jsonl',
        '4.0',
        'hinglish',
        'evaluation',
        'tier_3'
    )
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    license = EXCLUDED.license,
    url = EXCLUDED.url,
    version = EXCLUDED.version,
    language = EXCLUDED.language,
    domain = EXCLUDED.domain,
    trust_tier = EXCLUDED.trust_tier;

-- 2. Knowledge Chunks Table
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

-- 3. Populate knowledge_chunks with Provenance Attribution from clinical_knowledge_base
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

-- 4. Seed Additional WHO & IFCT Chunks with Strict Provenance
INSERT INTO knowledge_chunks (source_id, domain, condition_tags, diet_tags, language, script, content, derived)
VALUES 
    (
        'src_who_cvd_diabetes_2021',
        'cardiovascular',
        ARRAY['HYPERTENSION_WHO_TARGETS'],
        ARRAY['blood_pressure', 'lifestyle'],
        'hinglish',
        'latin',
        'Target blood pressure in adults with confirmed hypertension is <140/90 mmHg, and <130/80 mmHg in high-risk cardiovascular disease or diabetes. First-line therapy includes sodium reduction and 150 min/week moderate aerobic activity.',
        FALSE
    ),
    (
        'src_who_cvd_diabetes_2021',
        'cardiovascular',
        ARRAY['HYPERTENSION_CONTRAINDICATIONS'],
        ARRAY['exercise_safety', 'hypertension'],
        'hinglish',
        'latin',
        'Uncontrolled Stage 2 hypertension (systolic >=140 or diastolic >=90) without physician clearance contraindicates heavy isometric resistance, heavy deadlifts, and maximum exertion sprints.',
        FALSE
    ),
    (
        'src_ifct_2017',
        'food_composition',
        ARRAY['IFCT_MILLETS_GLYCEMIC'],
        ARRAY['ragi', 'jowar', 'millets', 'low_gi'],
        'hinglish',
        'latin',
        'Finger millet (ragi) provides 344 kcal, 7.3g protein, and 344mg calcium per 100g, with a significantly lower glycemic index than polished rice, stabilizing postprandial glucose curves.',
        FALSE
    ),
    (
        'src_ifct_2017',
        'food_composition',
        ARRAY['IFCT_PANEER_COMPOSITION'],
        ARRAY['paneer', 'protein', 'vegetarian'],
        'hinglish',
        'latin',
        'Fresh cow milk paneer provides 289 kcal, 18.3g protein, and 20.8g fat per 100g, serving as a bioavailable complete protein source for vegetarian dietary regimens.',
        FALSE
    )
ON CONFLICT DO NOTHING;
