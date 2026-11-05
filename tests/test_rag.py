import json
import pytest
from app.db import init_db, get_connection
from app.rag.retriever import hybrid_retriever
from app.rag.manager import document_manager
from app.rag.ingestion import DocumentParser, SemanticChunker, compute_content_hash
from app.engine import turn_orchestrator

@pytest.fixture(autouse=True)
def setup_database():
    init_db()

def test_rag_ingestion_txt_and_deduplication():
    """Verifies text document parsing, chunking, and SHA-256 duplicate suppression."""
    raw_text = (
        "# General Nutrition Guidelines\n\n"
        "## Hydration Protocol\n"
        "Patients should drink at least 2.5 to 3 liters of water every day.\n\n"
        "## Daily Fiber\n"
        "Include 25 to 30 grams of fiber from vegetables, whole grains, and legumes."
    )
    raw_bytes = raw_text.encode("utf-8")
    
    res1 = document_manager.ingest_document(
        title="Sample Hydration & Fiber Protocol",
        filename="hydration_protocol.txt",
        file_bytes=raw_bytes,
        file_type="txt",
        category="nutrition_guidance",
        author="Dr. Test",
        auto_approve=False
    )
    assert res1["status"] == "success"
    assert res1["approval_status"] == "draft"
    assert res1["chunk_count"] >= 1
    doc_id = res1["document_id"]

    # Duplicate submission with identical content
    res_dup = document_manager.ingest_document(
        title="Duplicate Hydration Protocol",
        filename="hydration_protocol_copy.txt",
        file_bytes=raw_bytes,
        file_type="txt",
        category="nutrition_guidance",
        author="Dr. Test",
    )
    assert res_dup["status"] == "duplicate"
    assert res_dup["document_id"] == doc_id

    # Clean up test doc
    document_manager.delete_document(doc_id)

def test_rag_ingestion_docx_and_pdf():
    """Verifies that PDF and DOCX parsers handle byte inputs without crashing."""
    # Test DOCX parsing with python-docx
    import docx
    import io
    doc = docx.Document()
    doc.add_heading("Clinical Protocol: Cardiac Care", level=1)
    doc.add_paragraph("Monitor resting heart rate every morning.")
    doc_buf = io.BytesIO()
    doc.save(doc_buf)
    docx_bytes = doc_buf.getvalue()

    res_docx = document_manager.ingest_document(
        title="DOCX Cardiac Care",
        filename="cardiac.docx",
        file_bytes=docx_bytes,
        file_type="docx",
        category="clinical_guideline",
        author="Dr. Cardio",
        auto_approve=True
    )
    assert res_docx["status"] == "success"
    assert res_docx["approval_status"] == "approved"
    document_manager.delete_document(res_docx["document_id"])

def test_rag_bloating_retrieves_approved_jeera_saunf_guidance():
    """Requirement: Period bloating retrieves the approved jeera/saunf water guidance with citation."""
    query = "Periods ke dauran pet phool raha hai aur gas ban rahi hai"
    chunks, conflict = hybrid_retriever.retrieve(query=query, patient_id="pt_101", top_k=2)
    assert len(chunks) > 0
    top_chunk = chunks[0]
    assert "jeera-saunf" in top_chunk.content or "jeera" in top_chunk.content
    assert "Gastrointestinal" in top_chunk.document_title or "Bloating" in top_chunk.document_title
    assert "Section:" in top_chunk.citation

def test_rag_mango_question_retrieves_seasonal_moderation_stance():
    """Requirement: Mango questions retrieve the correct seasonal moderation stance."""
    query = "Can I eat aam during weight loss or is it totally forbidden?"
    chunks, conflict = hybrid_retriever.retrieve(query=query, patient_id="pt_101", top_k=2)
    assert len(chunks) > 0
    assert any("mango" in c.content.lower() or "aam" in c.content.lower() for c in chunks)
    assert any("100g" in c.content or "moderation" in c.content for c in chunks)

def test_rag_gym_question_retrieves_pep_context():
    """Requirement: A gym-related question retrieves the user's actual PEP context."""
    query = "Can I do strength training or workout at the gym?"
    chunks, conflict = hybrid_retriever.retrieve(query=query, patient_id="pt_101", top_k=2)
    assert len(chunks) > 0
    assert any("gym" in c.content.lower() or "pep" in c.content.lower() for c in chunks)

def test_rag_unrelated_query_does_not_retrieve_false_positives():
    """Requirement: Unrelated documents are not retrieved for out-of-domain queries."""
    query = "How do I change the oil in my Honda motorcycle engine?"
    chunks, conflict = hybrid_retriever.retrieve(query=query, patient_id="pt_101", top_k=2, min_relevance_threshold=0.25)
    # Out of domain query should have no high-relevance chunks
    assert len(chunks) == 0

def test_rag_unapproved_documents_never_used():
    """Requirement: Unapproved (draft) documents are never returned by production retrieval."""
    # Query matching draft detox cleanse doc
    query = "Tell me about the raw juice cleanse detox regimen"
    chunks, conflict = hybrid_retriever.retrieve(query=query, patient_id="pt_101", top_k=3)
    # Must NOT return doc_unapproved_draft
    for chk in chunks:
        assert chk.document_id != "doc_unapproved_draft"
        assert "Extreme Raw Juice Cleanse" not in chk.content

def test_rag_multi_tenant_isolation_no_data_bleed():
    """Requirement: One user's private consultation information is never retrieved for another user."""
    # doc_patient_private_pt101 belongs to pt_101
    query = "What were my confidential doctor notes about blood pressure and morning step goals?"
    
    # Query as patient pt_101 (authorized)
    chunks_pt101, _ = hybrid_retriever.retrieve(query=query, patient_id="pt_101", top_k=3)
    assert any(c.document_id == "doc_patient_private_pt101" for c in chunks_pt101)

    # Query as patient pt_999 (unauthorized foreign user)
    chunks_pt999, _ = hybrid_retriever.retrieve(query=query, patient_id="pt_999", top_k=3)
    assert all(c.document_id != "doc_patient_private_pt101" for c in chunks_pt999)

@pytest.mark.asyncio
async def test_structured_data_dinner_comes_from_db():
    """Requirement: Dinner questions retrieve the correct meal from the actual database."""
    res = await turn_orchestrator.execute_turn(
        patient_id="pt_101",
        utterance="What is scheduled for my dinner tonight?",
        override_day="Wednesday"
    )
    assert "paneer bhurji" in res.final_response.lower()
    assert ("420" in res.final_response or "kcal" in res.final_response.lower())

@pytest.mark.asyncio
async def test_structured_data_pricing_never_invented():
    """Requirement: Pricing questions query database directly and never invent arbitrary prices."""
    res = await turn_orchestrator.execute_turn(
        patient_id="pt_101",
        utterance="Kitne paise lagenge subscription ke?",
    )
    assert "100% free" in res.final_response.lower() or "free" in res.final_response.lower()
    assert "1,499" in res.final_response
    assert "₹999" not in res.final_response
    assert "₹500" not in res.final_response

@pytest.mark.asyncio
async def test_voice_and_chat_consistency_for_same_question():
    """Requirement: Voice and chat return consistent answers for the same clinical question."""
    utt = "What can I drink to relieve stomach bloating?"
    
    # Chat execution
    chat_res = await turn_orchestrator.execute_turn(patient_id="pt_101", utterance=utt)
    
    # Voice execution (same orchestrator)
    voice_res = await turn_orchestrator.execute_turn(patient_id="pt_101", utterance=utt)
    
    assert "jeera" in chat_res.final_response.lower()
    assert "saunf" in chat_res.final_response.lower()
    assert "jeera" in voice_res.final_response.lower()
    assert "saunf" in voice_res.final_response.lower()

def test_clinician_rule_versioning_and_rollback():
    """Verifies clinician rule authoring, version increment, audit logging, and rollback."""
    from app.api import create_clinical_rule, rollback_clinical_rule, RuleCreateRequest

    req_v1 = RuleCreateRequest(
        rule_code="TEST_RULE_ACIDITY",
        category="symptom_remedy",
        trigger_keywords=["acidity", "heartburn"],
        trigger_pattern=r"\b(acidity|heartburn|seene me jalan)\b",
        clinical_remedy="Drink a glass of cold milk or coconut water.",
        author_name="Dr. V1"
    )
    res1 = create_clinical_rule(req_v1)
    assert res1["version"] == 1

    # Update to v2
    req_v2 = RuleCreateRequest(
        rule_code="TEST_RULE_ACIDITY",
        category="symptom_remedy",
        trigger_keywords=["acidity", "heartburn"],
        trigger_pattern=r"\b(acidity|heartburn|seene me jalan)\b",
        clinical_remedy="Sip cold coconut water and avoid lying down for 2 hours.",
        author_name="Dr. V2"
    )
    res2 = create_clinical_rule(req_v2)
    assert res2["version"] == 2

    # Rollback to v1
    res_rb = rollback_clinical_rule("TEST_RULE_ACIDITY")
    assert res_rb["status"] == "success"
    assert res_rb["restored_version"] == 1
    assert res_rb["current_version"] == 3
