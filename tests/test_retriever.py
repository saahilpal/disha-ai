import pytest
from app.knowledge.retriever import hybrid_retriever
from app.knowledge.patient_grounding import patient_context_resolver

def test_hybrid_retrieval_bloating():
    query = "Mujhe periods ke time pet phoolna aur bloating lag rahi hai"
    results = hybrid_retriever.retrieve(query, top_k=2)
    assert len(results) > 0
    top = results[0]
    assert "bloating" in top.code_or_entity.lower()
    assert "jeera" in top.content.lower()
    assert "saunf" in top.required_remedy_tokens

def test_hybrid_retrieval_mango_stance():
    query = "Kya weight loss ke dauran aam khana allowed hai?"
    results = hybrid_retriever.retrieve(query, top_k=2)
    assert len(results) > 0
    mango_items = [r for r in results if "mango" in r.code_or_entity.lower()]
    assert len(mango_items) > 0
    assert "moderation" in mango_items[0].content.lower()

def test_patient_pep_gym_permissions():
    pep = patient_context_resolver.get_pep_profile("pt_101")
    assert "gym" in pep["allowed_exercise"]
    assert "home" in pep["allowed_exercise"]

def test_patient_dinner_diet_plan():
    meal = patient_context_resolver.get_meal_plan("pt_101", meal_type="dinner", day_of_week="Wednesday")
    assert meal["found"] is True
    assert "paneer bhurji" in meal["items"].lower()
    assert meal["calories"] == 420

def test_patient_missing_meal_closed_domain_fallback():
    # Non-existent day or unassigned meal
    meal = patient_context_resolver.get_meal_plan("pt_101", meal_type="midnight_snack", day_of_week="Funday")
    assert meal["found"] is False
    assert "record not found" in meal["summary"].lower()

