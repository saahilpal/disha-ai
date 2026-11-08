-- Disha AI Core: ICMR Clinical Stances & Reference Micro-Chunks (<50 words)
-- Authority: Institutional Clinical Protocols & Dietary Guidelines

-- 1. Condition 1: GI Bloating Remedy (Approved Micro-Chunk)
INSERT INTO clinical_knowledge_base (
    condition_tag,
    trigger_terms,
    context_header,
    guideline_content,
    required_remedy_tokens,
    source_citation,
    approval_status,
    clinician_id,
    approved_at
) VALUES (
    'GI_BLOATING',
    'bloating gas pet phoolna acidity indigestion',
    '[Scope: Functional Dyspepsia; Authority: Institutional Clinical Protocol]',
    'Suggest warm jeera or saunf water and light walking post meals. Avoid raw salads, carbonated beverages, and heavy legumes after 7 PM.',
    ARRAY['jeera', 'saunf'],
    'Institutional Clinical Protocol',
    'approved',
    'clin_lead_01',
    NOW()
);

-- 2. Condition 2: Seasonal Fruit Allowance (Approved Micro-Chunk)
INSERT INTO clinical_knowledge_base (
    condition_tag,
    trigger_terms,
    context_header,
    guideline_content,
    required_remedy_tokens,
    source_citation,
    approval_status,
    clinician_id,
    approved_at
) VALUES (
    'FRUIT_MODERATION',
    'mango aam fruit sugar weight loss diet',
    '[Scope: Weight Management; Authority: Institutional Dietary Protocol]',
    'Fresh seasonal mango is permitted in moderation up to 100g daily during afternoon hours. Avoid mango shakes, added sugar, or consuming post dinner.',
    ARRAY['moderation', '100g'],
    'Institutional Dietary Protocol',
    'approved',
    'clin_lead_02',
    NOW()
);

-- 3. Condition 3: Knee & Joint Pain Care (Approved Micro-Chunk)
INSERT INTO clinical_knowledge_base (
    condition_tag,
    trigger_terms,
    context_header,
    guideline_content,
    required_remedy_tokens,
    source_citation,
    approval_status,
    clinician_id,
    approved_at
) VALUES (
    'KNEE_PAIN_CARE',
    'knee pain ghutno ka dard ghutne me dard knee stiffness osteoarthritis joint mobility quad strengthening low impact walking',
    '[Scope: Musculoskeletal Care; Authority: Institutional Clinical Protocol]',
    'For knee discomfort or joint stiffness, prefer low-impact walking on flat surfaces, quad isometrics, and warm compresses. Avoid deep squats, high jumping, and twisting loads.',
    ARRAY['walking', 'quad'],
    'Institutional Clinical Protocol',
    'approved',
    'clin_lead_01',
    NOW()
);

-- 3. Seed Test Profile: pt_test_01
INSERT INTO patient_pep (
    patient_id,
    hypertension_stage,
    gym_clearance,
    allowed_modalities,
    restricted_modalities,
    updated_at
) VALUES (
    'pt_test_01',
    'Stage 1',
    TRUE,
    ARRAY['gym', 'walking'],
    ARRAY['heavy_deadlifts', 'valsalva_maneuver'],
    NOW()
) ON CONFLICT (patient_id) DO UPDATE SET
    hypertension_stage = EXCLUDED.hypertension_stage,
    gym_clearance = EXCLUDED.gym_clearance,
    allowed_modalities = EXCLUDED.allowed_modalities,
    restricted_modalities = EXCLUDED.restricted_modalities,
    updated_at = NOW();

-- 4. Seed Diet Schedules for pt_test_01 (Cover all 7 days for dinner)
INSERT INTO patient_diet_schedules (
    patient_id,
    day_of_week,
    meal_type,
    prescribed_items,
    is_active
) VALUES 
    ('pt_test_01', 'monday', 'dinner', '150g paneer bhurji, 2 multigrain rotis, cucumber salad (approx 420 kcal)', TRUE),
    ('pt_test_01', 'tuesday', 'dinner', '150g paneer bhurji, 2 multigrain rotis, cucumber salad (approx 420 kcal)', TRUE),
    ('pt_test_01', 'wednesday', 'dinner', '150g paneer bhurji, 2 multigrain rotis, cucumber salad (approx 420 kcal)', TRUE),
    ('pt_test_01', 'thursday', 'dinner', '150g paneer bhurji, 2 multigrain rotis, cucumber salad (approx 420 kcal)', TRUE),
    ('pt_test_01', 'friday', 'dinner', '150g paneer bhurji, 2 multigrain rotis, cucumber salad (approx 420 kcal)', TRUE),
    ('pt_test_01', 'saturday', 'dinner', '150g paneer bhurji, 2 multigrain rotis, cucumber salad (approx 420 kcal)', TRUE),
    ('pt_test_01', 'sunday', 'dinner', '150g paneer bhurji, 2 multigrain rotis, cucumber salad (approx 420 kcal)', TRUE)
ON CONFLICT (patient_id, day_of_week, meal_type) DO UPDATE SET
    prescribed_items = EXCLUDED.prescribed_items,
    is_active = EXCLUDED.is_active;

-- 5. Seed Patient Access Token for pt_test_01 ('pt_test_01_valid_bearer_token')
-- sha256('pt_test_01_valid_bearer_token') = 4323e4210e527022e3ea85f1c7e92bf18b335a9f604ecab81c37d4e5f76b4a3a
INSERT INTO patient_access_tokens (
    token_hash,
    patient_id,
    created_at,
    expires_at
) VALUES (
    '4323e4210e527022e3ea85f1c7e92bf18b335a9f604ecab81c37d4e5f76b4a3a',
    'pt_test_01',
    NOW(),
    NOW() + INTERVAL '1 year'
) ON CONFLICT (token_hash) DO NOTHING;
