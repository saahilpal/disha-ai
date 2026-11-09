-- ==============================================================================
-- DISHA AI — UNIFIED EXERCISE RAG INGESTION
-- Merges Official Physical Activity Guidelines into the Central Knowledge Base
-- Sources:
-- 1. Fit India Movement (MoHFW & MYAS, Govt of India)
-- 2. Ministry of AYUSH & MDNIY (Common Yoga Protocol, Govt of India)
-- 3. World Health Organization (WHO Physical Activity Guidelines 2020)
-- ==============================================================================

-- 1. Register Knowledge Sources
INSERT INTO knowledge_sources (id, name, license, url, version, language, domain, trust_tier)
VALUES 
    (
        'src_fit_india_2020',
        'Fit India Age-Appropriate Fitness Protocols & Guidelines (18-64 Years)',
        'GODL-India',
        'https://fitindia.gov.in/guidelines',
        '2020.1',
        'en',
        'physical_activity',
        'tier_1'
    ),
    (
        'src_ayush_cyp_2023',
        'Common Yoga Protocol (CYP) & Yogic Guidelines for Lifestyle Disorders',
        'GODL-India',
        'https://ayush.gov.in/',
        'CYP-2023',
        'hi',
        'yoga_integrative_health',
        'tier_1'
    ),
    (
        'src_who_pa_2020',
        'WHO Guidelines on Physical Activity and Sedentary Behaviour 2020',
        'CC BY-NC-SA 3.0 IGO',
        'https://www.who.int/publications/i/item/9789240015128',
        '2020.1',
        'en',
        'clinical_exercise',
        'tier_1'
    )
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    license = EXCLUDED.license,
    url = EXCLUDED.url,
    version = EXCLUDED.version,
    language = EXCLUDED.language,
    domain = EXCLUDED.domain,
    trust_tier = EXCLUDED.trust_tier;

-- 2. Ingest Guidelines into clinical_knowledge_base
-- Strict Invariant: Every guideline_content must be < 50 words
INSERT INTO clinical_knowledge_base (
    condition_tag, trigger_terms, context_header, guideline_content, required_remedy_tokens, source_citation, approval_status, clinician_id, approved_at
)
SELECT * FROM (VALUES 
(
    'EXERCISE_WALKING_CARDIO',
    'exercise walking tehalna walk brisk walk steps cardio tahalna morning walk evening walk roz subah tehalna',
    '[Scope: Cardio & Glycemic Control; Authority: Fit India MoHFW & ICMR-NIN 2024]',
    'Perform 30 to 45 minutes of brisk walking daily at a conversational pace. A 10-15 minute walk after meals effectively blunts postprandial glucose spikes without joint strain.',
    ARRAY['brisk walk', 'walking'],
    'Fit India Protocols 18-64 Years & ICMR-NIN 2024 Guideline 2',
    'draft',
    NULL,
    NULL
),
(
    'EXERCISE_SQUATS_FUNCTIONAL',
    'squats baithak dand baithak knee pain squats chair squat leg workout ghutna dard',
    '[Scope: Lower Body Functional Strength; Authority: Fit India Protocols]',
    'Practice bodyweight squats to build leg endurance. For knee sensitivity, perform chair-supported squats limiting knee bend to 45 degrees, keeping knees tracking behind toes.',
    ARRAY['squats', 'chair squats'],
    'Fit India Age-Appropriate Protocols, Section 4.2',
    'draft',
    NULL,
    NULL
),
(
    'EXERCISE_HTN_CONTRAINDICATION',
    'deadlift heavy deadlifts heavy lifting gym high bp hypertension stage 1 stage 2 blood pressure clearance',
    '[Scope: Cardiovascular Safety Invariant; Authority: WHO Guidelines 2020]',
    'High-load maximal deadlifts and breath-holding Valsalva maneuvers are strictly contraindicated in unmanaged hypertension due to acute systolic pressure spikes. Maintain light resistance with continuous breathing.',
    ARRAY['contraindicated', 'continuous breathing'],
    'WHO Guidelines on Physical Activity 2020: Hypertension',
    'draft',
    NULL,
    NULL
),
(
    'EXERCISE_JUMPING_HIGH_IMPACT',
    'jumping jacks burpees jump rope koodna knee pain ankle injury high impact',
    '[Scope: Impact Modification; Authority: Fit India Movement]',
    'High-impact jumping exercises create 3 to 4 times bodyweight impact on joints. Replace jumping jacks with low-impact step-jacks or steady brisk walking when knee or ankle pain is present.',
    ARRAY['step-jacks', 'low impact'],
    'Fit India Assessment Protocols, Section 3.3',
    'draft',
    NULL,
    NULL
),
(
    'EXERCISE_OVERHEAD_PRESS',
    'overhead press shoulder press dumbbell shoulder pain rotator cuff kandha dard high bp',
    '[Scope: Shoulder & Vascular Protection; Authority: WHO 2020 & Fit India]',
    'Avoid heavy overhead presses if rotator cuff pain or stage 2 hypertension is present. Substitute with resistance band pull-aparts or neutral-grip chest presses below shoulder height.',
    ARRAY['neutral grip', 'resistance bands'],
    'WHO Clinical Exercise Guidelines 2020',
    'draft',
    NULL,
    NULL
),
(
    'EXERCISE_CRUNCHES_LUMBAR',
    'crunches sit-ups abs workout lower back pain slip disc kamar dard spine pain',
    '[Scope: Lumbar Spine Safety; Authority: Fit India Movement]',
    'Repetitive spinal flexion in crunches aggravates lumbar disc herniation. Substitute with isometric core stabilizers like bird-dog on all fours or gentle knee planks on a soft mat.',
    ARRAY['bird-dog', 'isometric core'],
    'Fit India Protocols 18-64 Years, Section 4.3',
    'draft',
    NULL,
    NULL
),
(
    'EXERCISE_RUNNING_AEROBIC',
    'running daudna jog jogging treadmill running knee pain joint impact',
    '[Scope: Aerobic Conditioning; Authority: Fit India Movement]',
    'Running offers high cardiovascular benefits but exerts substantial repetitive strike forces. For active knee pain or joint inflammation, substitute with flat brisk walking or stationary cycling.',
    ARRAY['brisk walking', 'cycling'],
    'Fit India Protocols 18-64 Years, Section 4.1',
    'draft',
    NULL,
    NULL
),
(
    'EXERCISE_YOGA_GENTLE',
    'yoga pranayama asanas gentle yoga stretching yogabhyas sukshma vyayama mobility',
    '[Scope: Restorative Yogic Health; Authority: Ministry of AYUSH & MDNIY]',
    'Begin with gentle loosening practices (Sadilaja) and restorative yoga asanas to improve joint flexibility and circulation. Maintain rhythmic breathing and avoid straining into painful ranges.',
    ARRAY['yoga', 'loosening practices'],
    'Common Yoga Protocol (CYP), Ministry of AYUSH & MDNIY, Chapter 3',
    'draft',
    NULL,
    NULL
),
(
    'EXERCISE_YOGA_VAJRASANA',
    'vajrasana vajrasan diamond pose khana khane ke baad digestion gas pet',
    '[Scope: Postprandial Digestive Asana; Authority: Ministry of AYUSH CYP]',
    'Vajrasana is the only asana safe to practice immediately after meals to support digestive fire. Use a folded towel beneath ankles; avoid in acute knee joint inflammation.',
    ARRAY['vajrasana', 'digestion'],
    'Common Yoga Protocol, Ministry of AYUSH, Section 3.7',
    'draft',
    NULL,
    NULL
),
(
    'EXERCISE_YOGA_BHUJANGASANA',
    'bhujangasana cobra pose back pain spine stiffness asthma chest expansion',
    '[Scope: Spinal Flexibility & Respiratory; Authority: Ministry of AYUSH CYP]',
    'Bhujangasana strengthens deep back extensors and enhances respiratory volume. Keep elbows gently bent with forearms supported (Sphinx variation) to avoid lumbar compression; avoid in acute hernia.',
    ARRAY['bhujangasana', 'cobra pose'],
    'Common Yoga Protocol, Ministry of AYUSH, Section 3.11',
    'draft',
    NULL,
    NULL
),
(
    'EXERCISE_PRANAYAMA_ANULOM',
    'anulom vilom nadi shodhana breathing pranayama high bp stress anxiety saans',
    '[Scope: Autonomic Regulation & BP Management; Authority: Ministry of AYUSH CYP]',
    'Practice Nadi Shodhana (Alternate Nostril Breathing) for 5-10 minutes. It balances the autonomic nervous system, enhances vagal tone, and safely reduces elevated systolic blood pressure.',
    ARRAY['anulom vilom', 'nadi shodhana'],
    'Common Yoga Protocol, Ministry of AYUSH, Section 4.1',
    'draft',
    NULL,
    NULL
),
(
    'EXERCISE_PRANAYAMA_BHRAMARI',
    'bhramari pranayama humming bee breath stress insomnia neend anxiety nitric oxide',
    '[Scope: Stress & Endothelial Health; Authority: Ministry of AYUSH CYP]',
    'Bhramari pranayama stimulates endogenous nitric oxide release in paranasal sinuses. It soothes neural agitation, relieves anxiety, and aids restful sleep without any contraindications.',
    ARRAY['bhramari', 'humming breath'],
    'Common Yoga Protocol, Ministry of AYUSH, Section 4.2',
    'draft',
    NULL,
    NULL
),
(
    'EXERCISE_PLANK_CORE',
    'plank planks core workout pet ki exercise kumbhakasana high bp',
    '[Scope: Core Stability; Authority: Fit India Movement]',
    'Perform isometric planks from knees or against an incline to protect the spine. Maintain continuous regular breathing; strictly avoid breath-holding in patients with hypertension.',
    ARRAY['knee plank', 'continuous breathing'],
    'Fit India Protocols 18-64 Years, Section 4.3',
    'draft',
    NULL,
    NULL
),
(
    'EXERCISE_PUSHUPS_STRENGTH',
    'pushups push up press ups dand chest workout wall pushups shoulder pain',
    '[Scope: Upper Body Strength; Authority: Fit India Movement]',
    'Build chest and shoulder endurance using push-ups. Regress to standing wall push-ups or knee push-ups to minimize joint loading if shoulder impingement or wrist discomfort is present.',
    ARRAY['wall push-ups', 'knee push-ups'],
    'Fit India Protocols 18-64 Years, Section 4.2',
    'draft',
    NULL,
    NULL
)
) AS v(condition_tag, trigger_terms, context_header, guideline_content, required_remedy_tokens, source_citation, approval_status, clinician_id, approved_at)
WHERE NOT EXISTS (
    SELECT 1 FROM clinical_knowledge_base c WHERE c.condition_tag = v.condition_tag
);

-- 3. Mirror into knowledge_chunks for Provenance Attribution
INSERT INTO knowledge_chunks (source_id, domain, condition_tags, diet_tags, language, script, content, derived)
SELECT 
    CASE 
        WHEN c.condition_tag LIKE 'EXERCISE_YOGA_%' OR c.condition_tag LIKE 'EXERCISE_PRANAYAMA_%' THEN 'src_ayush_cyp_2023'
        WHEN c.condition_tag = 'EXERCISE_HTN_CONTRAINDICATION' OR c.condition_tag = 'EXERCISE_OVERHEAD_PRESS' THEN 'src_who_pa_2020'
        ELSE 'src_fit_india_2020'
    END,
    'physical_activity',
    ARRAY[c.condition_tag, 'EXERCISE_GUIDELINES'],
    ARRAY['general_health'],
    'hinglish',
    'latin',
    c.guideline_content,
    FALSE
FROM clinical_knowledge_base c
WHERE c.condition_tag LIKE 'EXERCISE_%'
  AND NOT EXISTS (
      SELECT 1 FROM knowledge_chunks k WHERE k.content = c.guideline_content
  );
