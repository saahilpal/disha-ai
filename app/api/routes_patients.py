import json
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.db.connection import get_connection
from app.knowledge.patient_grounding import patient_context_resolver

router = APIRouter(prefix="/api/v1", tags=["Patients & PEP"])

class PEPUpdateRequest(BaseModel):
    allowed_exercise_locations: List[str]
    target_activity: str
    dietary_preference: str
    medical_conditions: List[str]

@router.get("/patients")
def list_patients():
    """Lists registered test patients."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, full_name, phone, gender, age, primary_goal FROM patients")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

@router.get("/patients/{patient_id}")
def get_patient_details(patient_id: str):
    """Retrieves full patient profile, active PEP permissions, and today's meal plan."""
    profile = patient_context_resolver.get_patient_profile(patient_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Patient not found")
        
    pep = patient_context_resolver.get_pep_profile(patient_id)
    dinner = patient_context_resolver.get_meal_plan(patient_id, meal_type="dinner")
    lunch = patient_context_resolver.get_meal_plan(patient_id, meal_type="lunch")
    breakfast = patient_context_resolver.get_meal_plan(patient_id, meal_type="breakfast")
    
    return {
        "profile": profile,
        "pep": pep,
        "diet_plan": {
            "breakfast": breakfast,
            "lunch": lunch,
            "dinner": dinner
        }
    }

@router.put("/patients/{patient_id}/pep")
def update_patient_pep(patient_id: str, payload: PEPUpdateRequest):
    """Updates patient PEP permissions (e.g. approving gym workouts)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE patient_pep
        SET allowed_exercise_locations = ?,
            target_activity = ?,
            dietary_preference = ?,
            medical_conditions = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE patient_id = ?
    """, (
        json.dumps(payload.allowed_exercise_locations),
        payload.target_activity,
        payload.dietary_preference,
        json.dumps(payload.medical_conditions),
        patient_id
    ))
    conn.commit()
    conn.close()
    return {"success": True, "patient_id": patient_id, "status": "PEP_UPDATED"}
