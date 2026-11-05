import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional
from app.config import settings

def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Creates SQLite connection configured with WAL mode for concurrent reads/writes."""
    target = db_path or settings.DATABASE_PATH
    Path(target).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target, timeout=10.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn

@contextmanager
def get_db(db_path: Optional[str] = None) -> Generator[sqlite3.Connection, None, None]:
    """Safe transaction context manager with automatic rollback on error."""
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def get_setting(key: str, default: str = "", db_path: Optional[str] = None) -> str:
    try:
        conn = get_connection(db_path)
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        conn.close()
        return row["value"] if row else default
    except Exception:
        return default

def set_setting(key: str, value: str, db_path: Optional[str] = None):
    with get_db(db_path) as conn:
        conn.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", (key, value))

def init_db(db_path: Optional[str] = None):
    """Initializes tables and seeds default test patient and clinical fixtures."""
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        
        # 1. Patients & Personal Encounter Profile (PEP)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS patients (
                id TEXT PRIMARY KEY,
                full_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                age INTEGER,
                gender TEXT,
                height_cm REAL,
                weight_kg REAL,
                activity_level TEXT,
                primary_goal TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Schema migration check for existing databases
        cursor.execute("PRAGMA table_info(patients);")
        existing_cols = {row["name"] for row in cursor.fetchall()}
        if "height_cm" not in existing_cols:
            cursor.execute("ALTER TABLE patients ADD COLUMN height_cm REAL;")
        if "weight_kg" not in existing_cols:
            cursor.execute("ALTER TABLE patients ADD COLUMN weight_kg REAL;")
        if "activity_level" not in existing_cols:
            cursor.execute("ALTER TABLE patients ADD COLUMN activity_level TEXT;")
        if "field_metadata" not in existing_cols:
            cursor.execute("ALTER TABLE patients ADD COLUMN field_metadata TEXT;")
        if "updated_at" not in existing_cols:
            cursor.execute("ALTER TABLE patients ADD COLUMN updated_at TIMESTAMP;")

        # Conversational History & Persistence (A. Conversation History)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversation_messages (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'chat',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_conv_user_session ON conversation_messages(user_id, session_id, created_at);")

        # Conversational Memory System (B. User Memory)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_memories (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                category TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'confirmed',
                confidence REAL DEFAULT 1.0,
                source_utterance TEXT,
                extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_user_key ON user_memories(user_id, category, key);")

        # Dynamic Personalised Exercise Plan (C. Personalised Exercise Plan - PEP)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_pep_plans (
                id TEXT PRIMARY KEY,
                user_id TEXT UNIQUE NOT NULL,
                status TEXT NOT NULL DEFAULT 'empty',
                fitness_goals_summary TEXT DEFAULT '',
                allowed_activities TEXT DEFAULT '[]',
                target_frequency TEXT DEFAULT '',
                prescribed_modalities TEXT DEFAULT '[]',
                contraindications TEXT DEFAULT '[]',
                weekly_schedule TEXT DEFAULT '{}',
                step_goal INTEGER DEFAULT 0,
                clinical_notes TEXT DEFAULT '',
                version INTEGER DEFAULT 1,
                generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_pep_user ON user_pep_plans(user_id);")

        # Rate Limiting & Usage Tracking (Protection for Gemini Free Quota)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_usage_logs (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                model TEXT NOT NULL,
                call_type TEXT NOT NULL,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_usage_user_time ON api_usage_logs(user_id, created_at);")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS patient_pep (
                patient_id TEXT PRIMARY KEY REFERENCES patients(id),
                allowed_exercise TEXT NOT NULL,      -- JSON array: ["gym", "home"]
                target_activity TEXT NOT NULL,
                dietary_preference TEXT NOT NULL,
                medical_conditions TEXT NOT NULL,    -- JSON array
                emergency_contact_phone TEXT NOT NULL
            );
        """)
        
        # 2. Dynamic Weekly Meal Plans
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS patient_meals (
                id TEXT PRIMARY KEY,
                patient_id TEXT NOT NULL REFERENCES patients(id),
                day_of_week TEXT NOT NULL,           -- 'Monday'..'Sunday'
                meal_type TEXT NOT NULL,             -- 'breakfast', 'lunch', 'dinner'
                meal_name TEXT NOT NULL,
                items_description TEXT NOT NULL,
                calories INTEGER,
                UNIQUE(patient_id, day_of_week, meal_type)
            );
        """)
        
        # 3. Clinical Rules authored by medical team
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS clinical_rules (
                id TEXT PRIMARY KEY,
                rule_code TEXT UNIQUE NOT NULL,
                category TEXT NOT NULL,
                severity TEXT NOT NULL DEFAULT 'mandatory',
                trigger_keywords TEXT NOT NULL,      -- JSON array: ["bloating", "pet phoolna"]
                trigger_pattern TEXT NOT NULL,       -- Regex
                clinical_remedy TEXT NOT NULL,
                author_name TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                is_active INTEGER NOT NULL DEFAULT 1,
                previous_version_id TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Migration check for clinical_rules columns
        cursor.execute("PRAGMA table_info(clinical_rules);")
        rule_cols = {row["name"] for row in cursor.fetchall()}
        if "severity" not in rule_cols:
            cursor.execute("ALTER TABLE clinical_rules ADD COLUMN severity TEXT DEFAULT 'mandatory';")
        if "version" not in rule_cols:
            cursor.execute("ALTER TABLE clinical_rules ADD COLUMN version INTEGER DEFAULT 1;")
        if "is_active" not in rule_cols:
            cursor.execute("ALTER TABLE clinical_rules ADD COLUMN is_active INTEGER DEFAULT 1;")
        if "previous_version_id" not in rule_cols:
            cursor.execute("ALTER TABLE clinical_rules ADD COLUMN previous_version_id TEXT;")
        if "updated_at" not in rule_cols:
            cursor.execute("ALTER TABLE clinical_rules ADD COLUMN updated_at TIMESTAMP;")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS clinical_rule_versions (
                id TEXT PRIMARY KEY,
                rule_code TEXT NOT NULL,
                version INTEGER NOT NULL,
                category TEXT NOT NULL,
                severity TEXT NOT NULL,
                trigger_keywords TEXT NOT NULL,
                trigger_pattern TEXT NOT NULL,
                clinical_remedy TEXT NOT NULL,
                author_name TEXT NOT NULL,
                action TEXT NOT NULL,
                change_summary TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)

        # 3b. RAG Documents, Chunks, and SQLite FTS5 index
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                filename TEXT NOT NULL,
                file_type TEXT NOT NULL,
                category TEXT NOT NULL,
                source_hash TEXT UNIQUE NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                approval_status TEXT NOT NULL DEFAULT 'draft',
                author TEXT NOT NULL,
                patient_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS document_chunks (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                chunk_index INTEGER NOT NULL,
                heading TEXT NOT NULL,
                content TEXT NOT NULL,
                embedding_json TEXT,
                metadata_json TEXT,
                patient_id TEXT
            );
        """)

        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS document_chunks_fts USING fts5(
                chunk_id UNINDEXED,
                heading,
                content,
                tokenize = 'unicode61'
            );
        """)
        
        # 4. Institutional Clinical Stances (e.g., mangoes, fasting)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS clinical_stances (
                entity_name TEXT PRIMARY KEY,        -- 'mangoes'
                category TEXT NOT NULL,
                clinical_stance TEXT NOT NULL,
                patient_explanation TEXT NOT NULL,
                cautions TEXT                        -- JSON dict
            );
        """)
        
        # 5. Verified Business Pricing Catalog
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pricing_plans (
                plan_code TEXT PRIMARY KEY,
                plan_name TEXT NOT NULL,
                price_inr INTEGER NOT NULL,
                billing_cycle TEXT NOT NULL,
                description TEXT NOT NULL
            );
        """)
        
        # 6. Audit Ledger for Call Sessions & Turns
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS call_sessions (
                id TEXT PRIMARY KEY,
                patient_id TEXT NOT NULL REFERENCES patients(id),
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                total_turns INTEGER DEFAULT 0,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS call_turns (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES call_sessions(id),
                turn_number INTEGER NOT NULL,
                user_utterance TEXT NOT NULL,
                pre_guardrail_status TEXT NOT NULL,
                retrieved_rules TEXT,
                raw_llm_response TEXT,
                post_guardrail_status TEXT NOT NULL,
                final_response TEXT NOT NULL,
                latency_ms REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # 7. Acute Red-Flag Emergency Triage Audit
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS emergency_escalations (
                id TEXT PRIMARY KEY,
                turn_id TEXT NOT NULL REFERENCES call_turns(id),
                patient_id TEXT NOT NULL REFERENCES patients(id),
                category TEXT NOT NULL,
                detected_phrases TEXT NOT NULL,
                triage_action TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # SEED DATA: Patient pt_101 (Ramesh Kumar)
        cursor.execute("""
            INSERT OR REPLACE INTO patients (id, full_name, phone, age, gender, height_cm, weight_kg, activity_level, primary_goal)
            VALUES ('pt_101', 'Ramesh Kumar', '+919876543210', 48, 'Male', 172.0, 78.5, 'Moderate', 'Weight loss and BP control');
        """)
        cursor.execute("""
            INSERT OR REPLACE INTO patient_pep (patient_id, allowed_exercise, target_activity, dietary_preference, medical_conditions, emergency_contact_phone)
            VALUES (
                'pt_101',
                ?,
                'Strength training 3x/week + 8k steps walking',
                'Vegetarian',
                ?,
                '+919876543211'
            );
        """, (json.dumps(["gym", "home", "walking"]), json.dumps(["mild_hypertension"])))

        # SEED DATA: Weekly Meals for pt_101
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        for day in days:
            cursor.execute("""
                INSERT OR REPLACE INTO patient_meals (id, patient_id, day_of_week, meal_type, meal_name, items_description, calories)
                VALUES (?, 'pt_101', ?, 'dinner', 'High-Protein Balanced Dinner', '150g paneer bhurji, 2 multigrain rotis, cucumber salad', 420);
            """, (f"meal_din_{day}", day))
            cursor.execute("""
                INSERT OR REPLACE INTO patient_meals (id, patient_id, day_of_week, meal_type, meal_name, items_description, calories)
                VALUES (?, 'pt_101', ?, 'lunch', 'Wholesome Dal & Sabzi', '1 bowl moong dal tadka, 1 cup brown rice, mix veg sabzi, curd', 480);
            """, (f"meal_lun_{day}", day))

        # SEED DATA: Clinical Rules (Failure #2: Bloating remedy)
        cursor.execute("""
            INSERT OR REPLACE INTO clinical_rules (id, rule_code, category, trigger_keywords, trigger_pattern, clinical_remedy, author_name, status)
            VALUES (
                'rule_01',
                'RULE_BLOATING_REMEDY',
                'symptom_remedy',
                ?,
                '(?i)\\b(bloating|pet\\s+(phool|bhari|me\\s+gas)|gas\\s+ban|period\\s+bloating)\\b',
                'Advise drinking warm jeera-saunf (cumin-fennel) water twice daily to soothe gas and abdominal distension.',
                'Dr. Ananya Sharma (Lead Dietitian)',
                'active'
            );
        """, (json.dumps(["bloating", "pet phoolna", "gas", "pet bhari", "period bloating"]),))

        # SEED DATA: Clinical Stances (Failure #8: Mango for weight loss)
        cursor.execute("""
            INSERT OR REPLACE INTO clinical_stances (entity_name, category, clinical_stance, patient_explanation, cautions)
            VALUES (
                'mangoes',
                'nutrition',
                'Permitted in seasonal moderation (max 100g/day) with meals; avoid late at night.',
                'Aam seasonal fruit hai aur moderation mein bilkul le sakte hain! Din ke waqt aadha aam (100g) enjoy karein, protein ya fiber ke sath.',
                ?
            );
        """, (json.dumps({"max_grams_per_day": 100, "ideal_timing": "daytime"}),))

        # SEED DATA: Pricing Catalog (Failure #1: Hallucinated pricing)
        cursor.execute("""
            INSERT OR REPLACE INTO pricing_plans (plan_code, plan_name, price_inr, billing_cycle, description)
            VALUES
                ('BASIC_CARE', 'Doctor Follow-Up Plan', 0, 'free_with_doctor', 'Doctor ke treatment plan ke sath Disha basic voice follow-up calls 100% free hain.'),
                ('PREMIUM_COACH', 'Personal Nutritionist Care', 1499, 'monthly', 'Dedicated 1-on-1 personal dietitian aur customized diet plans ₹1,499 prati mahina.');
        """)

        # SEED DATA: Approved Clinical RAG Documents & Chunks
        from app.rag.embeddings import SemanticVectorizer
        rag_seed_docs = [
            {
                "id": "doc_bloating_guideline",
                "title": "Disha Clinical Protocol: Gastrointestinal & Bloating Care",
                "filename": "clinical_bloating_protocol_v2.1.txt",
                "file_type": "txt",
                "category": "clinical_remedy",
                "source_hash": "hash_bloating_v2_1",
                "version": 2,
                "approval_status": "approved",
                "author": "Dr. Ananya Sharma (Lead Dietitian)",
                "patient_id": None,
                "chunks": [
                    {
                        "id": "chk_bloat_01",
                        "heading": "Symptom Triage: Abdominal Bloating and Gas",
                        "content": "For patients reporting post-meal bloating, menstrual distension, or abdominal heaviness: Advise drinking warm jeera-saunf (cumin-fennel) water twice daily. Boil one teaspoon each of cumin and fennel seeds in water, strain, and sip warm after meals to soothe smooth muscle spasms and relieve gas without medication side effects."
                    },
                    {
                        "id": "chk_bloat_02",
                        "heading": "Chronic Constipation and Digestion Support",
                        "content": "Increase daily dietary fiber through whole vegetables and maintain 3 liters of water intake. Gentle walking after meals stimulates peristalsis."
                    }
                ]
            },
            {
                "id": "doc_mango_nutrition",
                "title": "National Nutrition Board: Seasonal Fruits & Mango Moderation in Weight Management",
                "filename": "nutrition_mango_moderation_v1.4.txt",
                "file_type": "txt",
                "category": "nutrition_guidance",
                "source_hash": "hash_mango_v1_4",
                "version": 1,
                "approval_status": "approved",
                "author": "Dr. Vikram Seth (Chief Clinical Nutritionist)",
                "patient_id": None,
                "chunks": [
                    {
                        "id": "chk_mango_01",
                        "heading": "Mango (Aam) Consumption Guidelines",
                        "content": "Mangoes (including Dusseheri, Alphonso, Safeda) are nutrient-dense seasonal fruits containing vitamin A, C, and dietary fiber. In calorie-controlled and weight loss regimens, mangoes are permitted in seasonal moderation. Recommended portion is around 100g (about half a medium mango) during daytime hours, paired with protein or dietary fiber to prevent blood glucose spikes. Avoid eating mangoes late at night."
                    }
                ]
            },
            {
                "id": "doc_pep_guidelines",
                "title": "Disha Physical Exercise Protocol (PEP) & Hypertension Guidelines",
                "filename": "pep_exercise_guidelines_v1.0.txt",
                "file_type": "txt",
                "category": "pep_reference",
                "source_hash": "hash_pep_v1_0",
                "version": 1,
                "approval_status": "approved",
                "author": "Dr. Rajesh K (Sports Medicine Specialist)",
                "patient_id": None,
                "chunks": [
                    {
                        "id": "chk_pep_01",
                        "heading": "Gym Workout Clearance for Mild Hypertension",
                        "content": "Patients cleared under Disha Personal Exercise Protocol (PEP) for gym workouts may perform resistance training and gym exercises 3 times per week. Begin with light machines and warm-ups, maintain steady breathing without straining, and stay well hydrated throughout."
                    }
                ]
            },
            {
                "id": "doc_unapproved_draft",
                "title": "Experimental Unverified Detox Fasting Regimen (Draft)",
                "filename": "experimental_detox_draft_v0.1.txt",
                "file_type": "txt",
                "category": "experimental",
                "source_hash": "hash_unapproved_v0_1",
                "version": 1,
                "approval_status": "draft",
                "author": "Unverified Contributor",
                "patient_id": None,
                "chunks": [
                    {
                        "id": "chk_draft_01",
                        "heading": "Extreme Raw Juice Cleanse",
                        "content": "Patients must drink only raw unpasteurized juice 6 times a day and avoid all solid food for 7 days."
                    }
                ]
            },
            {
                "id": "doc_patient_private_pt101",
                "title": "Ramesh Kumar Confidential Doctor Consultation Summary",
                "filename": "ramesh_kumar_private_notes_v1.0.txt",
                "file_type": "txt",
                "category": "patient_consultation",
                "source_hash": "hash_ramesh_private_v1",
                "version": 1,
                "approval_status": "approved",
                "author": "Dr. Ananya Sharma",
                "patient_id": "pt_101",
                "chunks": [
                    {
                        "id": "chk_ramesh_01",
                        "heading": "Confidential Physician Consultation for Ramesh",
                        "content": "Patient Ramesh Kumar is strictly advised to monitor morning systolic blood pressure before breakfast. Target daily step goal is 8,000 steps with salt intake restricted to under 4 grams daily."
                    }
                ]
            }
        ]

        for d in rag_seed_docs:
            cursor.execute("""
                INSERT OR REPLACE INTO documents (id, title, filename, file_type, category, source_hash, version, approval_status, author, patient_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (d["id"], d["title"], d["filename"], d["file_type"], d["category"], d["source_hash"], d["version"], d["approval_status"], d["author"], d["patient_id"]))

            for chk in d["chunks"]:
                emb = SemanticVectorizer.encode(chk["content"])
                cursor.execute("""
                    INSERT OR REPLACE INTO document_chunks (id, document_id, chunk_index, heading, content, embedding_json, patient_id)
                    VALUES (?, ?, 0, ?, ?, ?, ?)
                """, (chk["id"], d["id"], chk["heading"], chk["content"], json.dumps(emb), d["patient_id"]))

                cursor.execute("DELETE FROM document_chunks_fts WHERE chunk_id = ?", (chk["id"],))
                cursor.execute("""
                    INSERT INTO document_chunks_fts (chunk_id, heading, content)
                    VALUES (?, ?, ?)
                """, (chk["id"], chk["heading"], chk["content"]))

# Auto-seed on first import if database does not exist
if not Path(settings.DATABASE_PATH).exists():
    init_db()

