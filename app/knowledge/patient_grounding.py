import json
from datetime import datetime
from typing import Dict, Any, Optional
from app.db.connection import get_connection

class PatientContextResolver:
    """
    Dynamic Patient DB & PEP Grounding Resolver.
    Fetches structured patient facts and applies upstream PHI de-identification.
    """

    def __init__(self, db_path: str = None):
        self.db_path = db_path

    def get_patient_profile(self, patient_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves raw patient demographic data."""
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id, full_name, phone, gender, age, primary_goal FROM patients WHERE id = ?", (patient_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_pep_profile(self, patient_id: str) -> Dict[str, Any]:
        """Retrieves active PEP permissions and constraints."""
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT allowed_exercise_locations, target_activity, dietary_preference, medical_conditions
            FROM patient_pep WHERE patient_id = ?
        """, (patient_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return {
                "allowed_exercise": ["home"],
                "target_activity": "Light daily walking",
                "dietary_preference": "Vegetarian",
                "medical_conditions": []
            }
            
        return {
            "allowed_exercise": json.loads(row["allowed_exercise_locations"]),
            "target_activity": row["target_activity"],
            "dietary_preference": row["dietary_preference"],
            "medical_conditions": json.loads(row["medical_conditions"])
        }

    def get_meal_plan(self, patient_id: str, meal_type: str = "dinner", day_of_week: Optional[str] = None) -> Dict[str, Any]:
        """
        Retrieves specific scheduled meal from patient_diet_plans.
        Implements strict closed-domain fallback if record is missing.
        """
        target_day = day_of_week or datetime.now().strftime("%A")
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT meal_name, items_description, calories
            FROM patient_diet_plans
            WHERE patient_id = ? AND day_of_week = ? AND meal_type = ?
        """, (patient_id, target_day, meal_type.lower()))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                "found": True,
                "meal_type": meal_type,
                "day": target_day,
                "meal_name": row["meal_name"],
                "items": row["items_description"],
                "calories": row["calories"],
                "summary": f"{row['meal_name']}: {row['items_description']} (~{row['calories']} kcal)"
            }
        else:
            return {
                "found": False,
                "meal_type": meal_type,
                "day": target_day,
                "summary": f"[SYSTEM_DATA: Diet chart record not found for {target_day} {meal_type}]"
            }

    def get_pricing_summary(self) -> str:
        """Retrieves verified business pricing facts."""
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT plan_name, price_inr, description FROM pricing_plans WHERE is_active=1")
        rows = cursor.fetchall()
        conn.close()
        
        lines = []
        for r in rows:
            lines.append(f"• {r['plan_name']} (₹{r['price_inr']}): {r['description']}")
        return "\n".join(lines)

# Global singleton
patient_context_resolver = PatientContextResolver()
