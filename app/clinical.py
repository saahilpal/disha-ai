import json
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple
from app.db import get_connection

IST = timezone(timedelta(hours=5, minutes=30))

class ClinicalContextResolver:
    """Grounds conversation in verified patient data, PEP, meal plans, and clinical rules."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path

    def get_patient(self, patient_id: str) -> Optional[Dict[str, Any]]:
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_pep(self, patient_id: str) -> Dict[str, Any]:
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM patient_pep WHERE patient_id = ?", (patient_id,)).fetchone()
        conn.close()
        if not row:
            return {
                "allowed_exercise": ["home", "walking"],
                "target_activity": "Light daily walking",
                "dietary_preference": "Vegetarian",
                "medical_conditions": [],
            }
        return {
            "allowed_exercise": json.loads(row["allowed_exercise"]),
            "target_activity": row["target_activity"],
            "dietary_preference": row["dietary_preference"],
            "medical_conditions": json.loads(row["medical_conditions"]),
        }

    def get_meal(
        self,
        patient_id: str,
        day_of_week: Optional[str] = None,
        meal_type: str = "dinner"
    ) -> Dict[str, Any]:
        """Fetches scheduled meal for the given day (IST by default), or returns closed-domain fallback."""
        target_day = day_of_week or datetime.now(IST).strftime("%A")
        conn = get_connection(self.db_path)
        row = conn.execute("""
            SELECT meal_name, items_description, calories
            FROM patient_meals
            WHERE patient_id = ? AND day_of_week = ? AND meal_type = ?
        """, (patient_id, target_day, meal_type.lower())).fetchone()
        conn.close()

        if row:
            return {
                "found": True,
                "day": target_day,
                "meal_type": meal_type,
                "meal_name": row["meal_name"],
                "items": row["items_description"],
                "calories": row["calories"],
                "summary": f"{row['meal_name']}: {row['items_description']} (~{row['calories']} kcal)",
            }
        return {
            "found": False,
            "day": target_day,
            "meal_type": meal_type,
            "summary": f"[SYSTEM_DATA: Diet chart record not found for {target_day} {meal_type}]",
        }

    def get_pricing_text(self) -> str:
        conn = get_connection(self.db_path)
        rows = conn.execute("SELECT plan_name, price_inr, description FROM pricing_plans").fetchall()
        conn.close()
        return "\n".join(f"- {r['plan_name']} (₹{r['price_inr']}): {r['description']}" for r in rows)

    def retrieve_knowledge(self, query: str, patient_id: Optional[str] = None) -> Tuple[List[str], List[str]]:
        """
        Retrieves doctor-approved clinical documents via Two-Tier Hybrid RAG,
        plus institutional clinical rules and stances.
        Returns (list_of_facts, required_remedy_tokens).
        """
        from app.rag.retriever import hybrid_retriever

        facts: List[str] = []
        required_tokens: List[str] = []
        lower = (query or "").lower()

        # 1. Hybrid RAG Retrieval (FTS5 BM25 + Dense Semantic Cosine + RRF)
        chunks, conflict_warning = hybrid_retriever.retrieve(query=query, patient_id=patient_id, top_k=3)
        for chk in chunks:
            facts.append(f"Approved Reference {chk.citation}: {chk.content}")
            if any(w in lower for w in ["bloat", "gas", "phool", "distension", "indigestion", "pet bhari"]) and any(w in chk.content.lower() for w in ["jeera", "saunf"]):
                required_tokens.extend(["jeera", "saunf"])

        if conflict_warning:
            facts.append(f"[SYSTEM WARNING: {conflict_warning}]")

        # 2. Doctor-authored Clinical Rules & Institutional Stances (Direct DB check)
        conn = get_connection(self.db_path)
        
        stances = conn.execute("SELECT entity_name, clinical_stance, patient_explanation FROM clinical_stances").fetchall()
        for s in stances:
            entity = s["entity_name"].lower()
            if entity in lower or (entity == "mangoes" and any(k in lower for k in ["mango", "aam", "dusseheri", "alphonso"])):
                facts.append(
                    f"Institutional Stance on {s['entity_name'].title()}: {s['clinical_stance']} "
                    f"Guidance: {s['patient_explanation']}"
                )

        rules = conn.execute("SELECT rule_code, trigger_pattern, clinical_remedy FROM clinical_rules WHERE status='active'").fetchall()
        for r in rules:
            if re.search(r["trigger_pattern"], lower):
                facts.append(f"Clinical Protocol ({r['rule_code']}): {r['clinical_remedy']}")
                if "bloating" in r["rule_code"].lower() and "jeera" not in required_tokens:
                    required_tokens.extend(["jeera", "saunf"])

        conn.close()
        return facts, list(set(required_tokens))

clinical_resolver = ClinicalContextResolver()

