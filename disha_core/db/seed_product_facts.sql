-- Disha AI Core: Product Facts, Commercial Pricing, and Clinical Clearance Policies
-- Table: product_facts

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

-- 1. Commercial Pricing Facts
INSERT INTO product_facts (fact_key, category, title, fact_value, description)
VALUES 
    (
        'pricing_followup_consultations',
        'pricing',
        'Follow-up Consultations Pricing',
        '{"amount": 0, "currency": "INR", "interval": "per_consultation", "statement": "Follow-up consultations ₹0 hain."}'::jsonb,
        'Ongoing AI health coaching follow-up consultations with Disha are 100% free of charge.'
    ),
    (
        'pricing_dedicated_nutritionist',
        'pricing',
        'Dedicated Human Nutritionist Plan Pricing',
        '{"amount": 1499, "currency": "INR", "interval": "monthly", "statement": "dedicated nutritionist plan ₹1,499 per month hai."}'::jsonb,
        'Personal dedicated human nutritionist consultation plan pricing is ₹1,499 per month.'
    )
ON CONFLICT (fact_key) DO UPDATE SET
    fact_value = EXCLUDED.fact_value,
    description = EXCLUDED.description,
    updated_at = NOW();

-- 2. Access Channel & Delivery Policies
INSERT INTO product_facts (fact_key, category, title, fact_value, description)
VALUES 
    (
        'channel_delivery_policy',
        'access_channel',
        'Application Delivery Channel Policy',
        '{"allowed_channel": "app_my_plan_tab", "forbidden_channels": ["whatsapp", "sms", "email", "telegram"], "statement": "Aap apna plan sirf app ke ''My Plan'' tab mein dekh sakte hain."}'::jsonb,
        'Diet and exercise prescriptions are strictly delivered in-app in the My Plan tab; third-party transport is restricted.'
    )
ON CONFLICT (fact_key) DO UPDATE SET
    fact_value = EXCLUDED.fact_value,
    description = EXCLUDED.description,
    updated_at = NOW();

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

-- 5. Personalized Exercise Prescription (PEP) Clearance Policies
INSERT INTO product_facts (fact_key, category, title, fact_value, description)
VALUES 
    (
        'pep_clearance_hypertension_stage1',
        'exercise_clearance',
        'PEP Policy for Stage 1 Hypertension',
        '{"condition": "hypertension_stage1", "gym_clearance": false, "allowed": ["brisk walking", "gentle yoga", "stretching", "breathing exercises", "light cycling"], "restricted": ["heavy deadlifts", "max weight lifting", "valsalva maneuver", "high-intensity sprinting"]}'::jsonb,
        'First-line exercise clearance protocol for patients with Stage 1 hypertension without physician clearance.'
    ),
    (
        'pep_clearance_cardiac_severe',
        'exercise_clearance',
        'PEP Policy for Severe HTN / Cardiac History',
        '{"condition": "cardiac_or_severe_hypertension", "gym_clearance": false, "allowed": ["brisk walking"], "restricted": ["heavy weightlifting", "heavy deadlifts", "hiit", "high intensity sprints", "valsalva maneuver"]}'::jsonb,
        'Strict high-risk contraindication rules for patients with cardiac diagnoses or Stage 2 hypertension.'
    ),
    (
        'pep_clearance_healthy_adult',
        'exercise_clearance',
        'PEP Policy for Unrestricted Healthy Adults',
        '{"condition": "healthy_unrestricted", "gym_clearance": true, "allowed": ["brisk walking", "jogging", "swimming", "cycling", "moderate strength training"], "restricted": []}'::jsonb,
        'Standard clearance guidelines for healthy adults with physician gym clearance.'
    )
ON CONFLICT (fact_key) DO UPDATE SET
    fact_value = EXCLUDED.fact_value,
    description = EXCLUDED.description,
    updated_at = NOW();

-- 6. Dietary Preferences & Guardrails
INSERT INTO product_facts (fact_key, category, title, fact_value, description)
VALUES 
    (
        'diet_vegetarian_guardrail',
        'diet_rules',
        'Vegetarian Dietary Invariant Guardrail',
        '{"forbidden": ["chicken", "mutton", "fish", "meat", "poultry", "seafood", "prawns", "beef", "pork", "eggs"], "default_substitutes": ["paneer ya tofu", "sprouts", "moong dal"]}'::jsonb,
        'Strict non-meat guardrail and plant protein substitution rules for vegetarian profiles.'
    )
ON CONFLICT (fact_key) DO UPDATE SET
    fact_value = EXCLUDED.fact_value,
    description = EXCLUDED.description,
    updated_at = NOW();

-- 7. Onboarding 7-Day Meal Schedule Templates
INSERT INTO product_facts (fact_key, category, title, fact_value, description)
VALUES 
    (
        'diet_template_jain',
        'diet_template',
        'Jain Dietary 7-Day Meal Protocol',
        '{"breakfast": "2 moong dal chillas with mint chutney (no root veg) and a small bowl of curd (approx 280 kcal)", "lunch": "1 bowl yellow moong dal, 2 phulkas, steamed lauki sabzi, and fresh cucumber salad (approx 420 kcal)", "dinner": "150g fresh paneer sabzi (jain prep), 2 multigrain rotis, and bottle gourd soup (approx 400 kcal)"}'::jsonb,
        'Default nutritious meal template adhering to Jain dietary restrictions (no root vegetables, pure vegetarian).'
    ),
    (
        'diet_template_vegetarian',
        'diet_template',
        'Standard Indian Vegetarian 7-Day Meal Protocol',
        '{"breakfast": "2 moong dal chillas with mint chutney and a small bowl of curd (approx 280 kcal)", "lunch": "1 bowl dal tadka, 2 multigrain rotis, steamed seasonal vegetables, and cucumber raita (approx 450 kcal)", "dinner": "150g paneer bhurji, 2 multigrain rotis, and cucumber salad (approx 420 kcal)"}'::jsonb,
        'Nutritionally balanced Indian vegetarian meal plan aligned with ICMR-NIN 2024 guidelines.'
    ),
    (
        'diet_template_non_vegetarian',
        'diet_template',
        'High-Protein Non-Vegetarian 7-Day Meal Protocol',
        '{"breakfast": "2 boiled eggs or egg scramble with whole wheat toast and sauteed greens (approx 290 kcal)", "lunch": "1 bowl grilled chicken curry/dal with 1 cup brown rice and cucumber-tomato salad (approx 460 kcal)", "dinner": "150g grilled chicken/paneer with steamed broccoli, carrots, and 1 multigrain roti (approx 410 kcal)"}'::jsonb,
        'Nutritionally calibrated protein meal schedule for eggetarian and non-vegetarian patients.'
    )
ON CONFLICT (fact_key) DO UPDATE SET
    fact_value = EXCLUDED.fact_value,
    description = EXCLUDED.description,
    updated_at = NOW();
