-- Disha AI Core: Product Facts, Commercial Pricing, and Clinical Clearance Policies
-- Table: product_facts

CREATE TABLE IF NOT EXISTS product_facts (
    fact_key VARCHAR(64) PRIMARY KEY,
    category VARCHAR(64) NOT NULL,
    title VARCHAR(128) NOT NULL,
    fact_value JSONB NOT NULL,
    description TEXT,
    owner VARCHAR(64) NOT NULL DEFAULT 'product_team',
    is_verified BOOLEAN NOT NULL DEFAULT FALSE,
    verification_status VARCHAR(64) NOT NULL DEFAULT 'unknown',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_product_facts_category ON product_facts(category);

-- 1. Commercial Pricing Facts
INSERT INTO product_facts (fact_key, category, title, fact_value, description)
VALUES 
    (
        'pricing_followup_consultations',
        'pricing',
        'Follow-up Consultations Pricing',
        '{"status": "unknown"}'::jsonb,
        'Awaiting verified pricing information from the responsible team.'
    ),
    (
        'pricing_dedicated_nutritionist',
        'pricing',
        'Dedicated Human Nutritionist Plan Pricing',
        '{"status": "unknown"}'::jsonb,
        'Awaiting verified pricing information from the responsible team.'
    )
ON CONFLICT (fact_key) DO UPDATE SET
    fact_value = EXCLUDED.fact_value,
    description = EXCLUDED.description,
    updated_at = NOW()
WHERE product_facts.is_verified = FALSE
  AND product_facts.verification_status = 'unknown';

-- 2. Access Channel & Delivery Policies
INSERT INTO product_facts (fact_key, category, title, fact_value, description)
VALUES 
    (
        'channel_delivery_policy',
        'access_channel',
        'Application Delivery Channel Policy',
        '{"status": "unknown"}'::jsonb,
        'Awaiting verified supported-channel information from the responsible team.'
    )
ON CONFLICT (fact_key) DO UPDATE SET
    fact_value = EXCLUDED.fact_value,
    description = EXCLUDED.description,
    updated_at = NOW()
WHERE product_facts.is_verified = FALSE
  AND product_facts.verification_status = 'unknown';

-- 3. AI Persona Identity & Clinical Disclaimer Boundaries
INSERT INTO product_facts (fact_key, category, title, fact_value, description)
VALUES 
    (
        'persona_identity',
        'identity',
        'Disha AI Persona Statement',
        '{"name": "Disha", "role": "AI Health Coach", "is_doctor": false, "is_human": false, "statement": "Main Disha hoon, aapki AI health coach."}'::jsonb,
        'Identity boundary: Disha is an AI wellness coach and must never claim medical licensure or human status.'
    ),
    (
        'clinical_diagnosis_policy',
        'clinical_boundary',
        'Medical Diagnosis Boundary',
        '{"statement": "Main ek AI coach hoon aur koi medical diagnosis nahi de sakti; kripya diagnosis ke liye clinician se consult karein."}'::jsonb,
        'Disha cannot provide medical diagnoses or interpret definitive clinical pathology.'
    ),
    (
        'clinical_prescription_policy',
        'clinical_boundary',
        'Pharmaceutical Prescription Boundary',
        '{"statement": "Main dawaiyon ki dose ya prescription badalne ke liye authorized nahi hoon; kripya apne prescribing clinician se salah lein."}'::jsonb,
        'Disha cannot prescribe pharmaceuticals, adjust medication doses, or alter physician regimens.'
    )
ON CONFLICT (fact_key) DO UPDATE SET
    fact_value = EXCLUDED.fact_value,
    description = EXCLUDED.description,
    updated_at = NOW();

-- 4. Emergency Contacts & Helplines
INSERT INTO product_facts (fact_key, category, title, fact_value, description)
VALUES 
    (
        'emergency_helpline_national',
        'emergency_helpline',
        'National Emergency Ambulance Helpline',
        '{"service": "National Emergency Services", "number": "112", "statement": "Yeh emergency ho sakti hai. Abhi 112 par call karein."}'::jsonb,
        'Indian national all-in-one emergency response service number.'
    ),
    (
        'emergency_helpline_telemanas',
        'emergency_helpline',
        'Tele-MANAS Mental Health Helpline',
        '{"service": "Tele-MANAS National Tele-Mental Health Programme", "number": "14416", "statement": "Tele-MANAS se 14416 par bhi baat kar sakte hain."}'::jsonb,
        'Government of India 24x7 toll-free mental health psychological support helpline.'
    )
ON CONFLICT (fact_key) DO UPDATE SET
    fact_value = EXCLUDED.fact_value,
    description = EXCLUDED.description,
    updated_at = NOW();

-- Clinical permissions are enforced by backend safety rules. Dietary alternatives
-- come from approved knowledge retrieval and the user's recorded preferences.
DELETE FROM product_facts
WHERE fact_key LIKE 'pep_clearance_%'
   OR fact_key LIKE 'diet_template_%'
   OR fact_key = 'diet_vegetarian_guardrail';
