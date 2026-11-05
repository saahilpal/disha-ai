-- Disha Clinical Voice AI - SQLite DDL Schema with FTS5

-- 1. Clinical Rules authored by doctors and dietitians
CREATE TABLE IF NOT EXISTS clinical_rules (
    id TEXT PRIMARY KEY,
    rule_code TEXT UNIQUE NOT NULL,
    category TEXT NOT NULL,                        -- 'symptom_remedy', 'diet_protocol', 'exercise_safety'
    trigger_keywords TEXT NOT NULL,                -- JSON array: ["bloating", "pet phoolna", "gas"]
    trigger_patterns TEXT NOT NULL,                -- Regex pattern string
    clinical_remedy TEXT NOT NULL,                 -- Approved remedy: "Warm jeera-saunf water twice a day"
    rationale TEXT NOT NULL,                       -- Clinical justification
    author_name TEXT NOT NULL,                     -- Doctor/Dietitian name
    status TEXT NOT NULL DEFAULT 'active',         -- 'draft', 'active', 'archived'
    version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Full-Text Search FTS5 Virtual Table for sub-millisecond BM25 keyword matching
CREATE VIRTUAL TABLE IF NOT EXISTS clinical_rules_fts USING fts5(
    rule_code,
    category,
    trigger_keywords,
    clinical_remedy,
    content='clinical_rules',
    content_rowid='rowid'
);

-- Triggers to maintain FTS5 synchronization with clinical_rules table
CREATE TRIGGER IF NOT EXISTS trg_clinical_rules_ai AFTER INSERT ON clinical_rules BEGIN
    INSERT INTO clinical_rules_fts(rowid, rule_code, category, trigger_keywords, clinical_remedy)
    VALUES (new.rowid, new.rule_code, new.category, new.trigger_keywords, new.clinical_remedy);
END;

CREATE TRIGGER IF NOT EXISTS trg_clinical_rules_ad AFTER DELETE ON clinical_rules BEGIN
    INSERT INTO clinical_rules_fts(clinical_rules_fts, rowid, rule_code, category, trigger_keywords, clinical_remedy)
    VALUES ('delete', old.rowid, old.rule_code, old.category, old.trigger_keywords, old.clinical_remedy);
END;

CREATE TRIGGER IF NOT EXISTS trg_clinical_rules_au AFTER UPDATE ON clinical_rules BEGIN
    INSERT INTO clinical_rules_fts(clinical_rules_fts, rowid, rule_code, category, trigger_keywords, clinical_remedy)
    VALUES ('delete', old.rowid, old.rule_code, old.category, old.trigger_keywords, old.clinical_remedy);
    INSERT INTO clinical_rules_fts(rowid, rule_code, category, trigger_keywords, clinical_remedy)
    VALUES (new.rowid, new.rule_code, new.category, new.trigger_keywords, new.clinical_remedy);
END;

-- 2. Clinical Stances on foods, fasting, and supplements
CREATE TABLE IF NOT EXISTS clinical_stances (
    id TEXT PRIMARY KEY,
    entity_name TEXT UNIQUE NOT NULL,              -- e.g. 'mangoes', 'intermittent_fasting'
    category TEXT NOT NULL,                        -- 'nutrition', 'supplements', 'lifestyle'
    clinical_stance TEXT NOT NULL,                 -- Approved consensus stance
    patient_explanation TEXT NOT NULL,             -- Friendly Hinglish coaching response
    comorbidity_cautions TEXT,                     -- JSON: {"diabetes": "limit to 50g with protein"}
    is_active BOOLEAN NOT NULL DEFAULT 1,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Explicit System Capabilities & Delivery Channels
CREATE TABLE IF NOT EXISTS system_capabilities (
    id TEXT PRIMARY KEY,
    capability_key TEXT UNIQUE NOT NULL,           -- 'whatsapp_delivery', 'sms_notifications', 'in_app_diet_chart'
    is_supported BOOLEAN NOT NULL DEFAULT 0,
    allowed_channel_name TEXT,
    fallback_message TEXT NOT NULL,                -- "Diet chart Disha mobile app ke 'My Plan' tab mein available hai"
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Authorized Pricing Plans & Business Catalog
CREATE TABLE IF NOT EXISTS pricing_plans (
    id TEXT PRIMARY KEY,
    plan_code TEXT UNIQUE NOT NULL,                -- 'BASIC_CARE', 'PREMIUM_COACH'
    plan_name TEXT NOT NULL,
    price_inr INTEGER NOT NULL,                    -- 0 for basic follow-ups, 1499 for premium
    billing_cycle TEXT NOT NULL,                   -- 'free_with_doctor', 'monthly'
    description TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT 1
);

-- 5. Patients Profile
CREATE TABLE IF NOT EXISTS patients (
    id TEXT PRIMARY KEY,
    full_name TEXT NOT NULL,
    phone TEXT NOT NULL,
    gender TEXT,
    age INTEGER,
    primary_goal TEXT NOT NULL,                    -- 'weight_loss', 'hba1c_reduction', 'pcos_reversal'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 6. Personalized Exercise & Eating Plan (PEP)
CREATE TABLE IF NOT EXISTS patient_pep (
    id TEXT PRIMARY KEY,
    patient_id TEXT UNIQUE NOT NULL REFERENCES patients(id),
    allowed_exercise_locations TEXT NOT NULL,      -- JSON array: ["gym", "home", "outdoors"]
    target_activity TEXT NOT NULL,                 -- "Strength training 3x/week + 8k steps"
    dietary_preference TEXT NOT NULL,              -- "Vegetarian", "Eggetarian", "Non-Vegetarian"
    medical_conditions TEXT NOT NULL,              -- JSON array: ["hypertension", "PCOS"]
    emergency_contact_name TEXT NOT NULL,
    emergency_contact_phone TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 7. Dynamic Weekly Meal Plans
CREATE TABLE IF NOT EXISTS patient_diet_plans (
    id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL REFERENCES patients(id),
    day_of_week TEXT NOT NULL,                     -- 'Monday', 'Tuesday', ..., 'Sunday'
    meal_type TEXT NOT NULL,                       -- 'breakfast', 'lunch', 'dinner', 'snack'
    meal_name TEXT NOT NULL,
    items_description TEXT NOT NULL,               -- e.g. "Paneer bhurji (150g), 2 multigrain rotis, cucumber salad"
    calories INTEGER,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(patient_id, day_of_week, meal_type)
);

-- 8. Voice Call Sessions
CREATE TABLE IF NOT EXISTS call_sessions (
    id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL REFERENCES patients(id),
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'ACTIVE',         -- 'COMPLETED', 'EMERGENCY_HALTED', 'ABORTED'
    total_turns INTEGER DEFAULT 0,
    p95_latency_ms REAL,
    consent_obtained BOOLEAN DEFAULT 1
);

-- 9. Immutable Turn Audit Ledger
CREATE TABLE IF NOT EXISTS call_turns (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES call_sessions(id),
    turn_number INTEGER NOT NULL,
    user_utterance TEXT NOT NULL,
    pre_guardrail_status TEXT NOT NULL,            -- 'PASS', 'EMERGENCY_TRIGGERED'
    retrieved_rule_codes TEXT,                     -- JSON array
    raw_llm_response TEXT,
    post_guardrail_status TEXT NOT NULL,           -- 'CLEAN', 'INTERCEPTED_WHATSAPP', 'INTERCEPTED_PERSONA', 'REMEDY_INJECTED'
    final_response TEXT NOT NULL,
    latency_breakdown TEXT NOT NULL,               -- JSON: {vad_ms, stt_ms, rag_ms, llm_ttft_ms, tts_ttfb_ms, total_ms}
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 10. Clinical Emergency Escalations
CREATE TABLE IF NOT EXISTS emergency_escalations (
    id TEXT PRIMARY KEY,
    turn_id TEXT NOT NULL REFERENCES call_turns(id),
    patient_id TEXT NOT NULL REFERENCES patients(id),
    red_flag_category TEXT NOT NULL,               -- 'cardiovascular', 'respiratory', 'neurological'
    detected_phrases TEXT NOT NULL,
    triage_action_taken TEXT NOT NULL,
    care_ops_notified BOOLEAN DEFAULT 0,
    sms_fallback_triggered BOOLEAN DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'PENDING',        -- 'PENDING', 'DOCTOR_CALLED', 'RESOLVED'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 11. Pinned Golden Regression Benchmark Suite
CREATE TABLE IF NOT EXISTS regression_test_suite (
    id TEXT PRIMARY KEY,
    test_code TEXT UNIQUE NOT NULL,
    failure_category TEXT NOT NULL,                -- 'wrong_statement', 'missed_action', 'missing_fact'
    input_utterance TEXT NOT NULL,
    patient_context TEXT NOT NULL,                 -- JSON context
    expected_phrases TEXT NOT NULL,                -- JSON: ["jeera", "saunf"]
    forbidden_phrases TEXT NOT NULL,               -- JSON: ["whatsapp", "human", "₹999"]
    should_emergency_halt BOOLEAN DEFAULT 0,
    is_active BOOLEAN DEFAULT 1
);
