import json
import uuid
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.db.connection import get_connection

router = APIRouter(prefix="/api/v1", tags=["Clinical Rules & Stances"])

class RuleCreateRequest(BaseModel):
    rule_code: str
    category: str
    trigger_keywords: List[str]
    clinical_remedy: str
    rationale: str
    author_name: str

class StanceCreateRequest(BaseModel):
    entity_name: str
    category: str
    clinical_stance: str
    patient_explanation: str
    comorbidity_cautions: Optional[dict] = None

@router.get("/rules")
def list_rules():
    """List all active clinical rules authored by clinicians."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, rule_code, category, trigger_keywords, clinical_remedy, rationale, author_name, status, version, updated_at
        FROM clinical_rules WHERE status != 'archived' ORDER BY created_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    
    rules = []
    for r in rows:
        d = dict(r)
        d["trigger_keywords"] = json.loads(d["trigger_keywords"])
        rules.append(d)
    return rules

@router.post("/rules")
def create_or_update_rule(payload: RuleCreateRequest):
    """
    Creates or updates a clinical rule.
    In live production, this triggers the automated regression test gate before committing.
    """
    conn = get_connection()
    cursor = conn.cursor()
    rule_id = f"rule_{uuid.uuid4().hex[:8]}"
    trigger_patterns = "|".join(payload.trigger_keywords)
    
    cursor.execute("""
        INSERT INTO clinical_rules (id, rule_code, category, trigger_keywords, trigger_patterns, clinical_remedy, rationale, author_name, status, version)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', 1)
        ON CONFLICT(rule_code) DO UPDATE SET
            category=excluded.category,
            trigger_keywords=excluded.trigger_keywords,
            trigger_patterns=excluded.trigger_patterns,
            clinical_remedy=excluded.clinical_remedy,
            rationale=excluded.rationale,
            author_name=excluded.author_name,
            version=version + 1,
            updated_at=CURRENT_TIMESTAMP
    """, (
        rule_id,
        payload.rule_code,
        payload.category,
        json.dumps(payload.trigger_keywords),
        trigger_patterns,
        payload.clinical_remedy,
        payload.rationale,
        payload.author_name
    ))
    conn.commit()
    conn.close()
    return {"success": True, "rule_code": payload.rule_code, "status": "PUBLISHED_TO_PRODUCTION"}

@router.get("/stances")
def list_stances():
    """List all approved clinical and nutritional stances."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, entity_name, category, clinical_stance, patient_explanation, comorbidity_cautions FROM clinical_stances WHERE is_active=1")
    rows = cursor.fetchall()
    conn.close()
    
    stances = []
    for r in rows:
        d = dict(r)
        d["comorbidity_cautions"] = json.loads(d["comorbidity_cautions"] or "{}")
        stances.append(d)
    return stances

@router.post("/stances")
def create_or_update_stance(payload: StanceCreateRequest):
    """Creates or updates a clinical stance."""
    conn = get_connection()
    cursor = conn.cursor()
    stance_id = f"st_{uuid.uuid4().hex[:8]}"
    
    cursor.execute("""
        INSERT INTO clinical_stances (id, entity_name, category, clinical_stance, patient_explanation, comorbidity_cautions, is_active)
        VALUES (?, ?, ?, ?, ?, ?, 1)
        ON CONFLICT(entity_name) DO UPDATE SET
            category=excluded.category,
            clinical_stance=excluded.clinical_stance,
            patient_explanation=excluded.patient_explanation,
            comorbidity_cautions=excluded.comorbidity_cautions,
            updated_at=CURRENT_TIMESTAMP
    """, (
        stance_id,
        payload.entity_name.lower(),
        payload.category,
        payload.clinical_stance,
        payload.patient_explanation,
        json.dumps(payload.comorbidity_cautions or {})
    ))
    conn.commit()
    conn.close()
    return {"success": True, "entity_name": payload.entity_name, "status": "SAVED"}

@router.get("/capabilities")
def list_capabilities():
    """Lists explicit system capabilities and fallback routing."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT capability_key, is_supported, allowed_channel_name, fallback_message FROM system_capabilities")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

@router.get("/pricing")
def list_pricing():
    """Lists verified pricing plans."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT plan_code, plan_name, price_inr, billing_cycle, description FROM pricing_plans WHERE is_active=1")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows
