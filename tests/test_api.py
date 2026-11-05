import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_root_endpoint():
    res = client.get("/")
    assert res.status_code == 200
    assert res.json()["status"] == "online"

def test_browser_html_root_and_demo():
    res_html = client.get("/", headers={"accept": "text/html"})
    assert res_html.status_code == 200
    assert "Disha AI" in res_html.text

    res_demo = client.get("/demo")
    assert res_demo.status_code == 200
    assert "Disha AI" in res_demo.text

def test_static_assets():
    res_css = client.get("/static/style.css")
    assert res_css.status_code == 200
    assert "voice-orb" in res_css.text

    res_js = client.get("/static/app.js")
    assert res_js.status_code == 200
    assert "triggerManualBargeIn" in res_js.text

def test_synthesize_endpoint():
    res = client.post("/synthesize", json={"text": "Namaste Ramesh ji"})
    assert res.status_code == 200
    assert res.headers["content-type"] == "audio/mpeg"


def test_health_endpoint():
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["database_connected"] is True

def test_chat_endpoint_success():
    payload = {
        "patient_id": "pt_101",
        "utterance": "Aaj dinner mein kya hai?",
        "session_id": "test_sess_01",
        "turn_number": 1,
    }
    res = client.post("/chat", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["session_id"] == "test_sess_01"
    assert data["is_emergency"] is False
    assert len(data["final_response"]) > 0

def test_chat_endpoint_empty_utterance_rejected():
    res = client.post("/chat", json={"patient_id": "pt_101", "utterance": "   "})
    assert res.status_code == 400

def test_get_patient_profile_success():
    res = client.get("/patient/pt_101")
    assert res.status_code == 200
    data = res.json()
    assert data["patient"]["id"] == "pt_101"
    assert "allowed_exercise" in data["pep"]
    assert len(data["meals"]) > 0

def test_get_patient_profile_not_found():
    res = client.get("/patient/pt_nonexistent")
    assert res.status_code == 404

def test_get_and_create_clinical_rules():
    # Fetch existing rules
    res = client.get("/rules")
    assert res.status_code == 200
    data = res.json()
    assert len(data["rules"]) > 0
    assert len(data["stances"]) > 0

    # Create new rule
    new_rule = {
        "rule_code": "RULE_TEST_HEADACHE",
        "category": "symptom_remedy",
        "trigger_keywords": ["headache", "sar dard"],
        "trigger_pattern": r"\b(headache|sar\s+dard)\b",
        "clinical_remedy": "Advise drinking 500ml water and resting in a dark quiet room.",
        "author_name": "Dr. Testing",
    }
    res = client.post("/rules", json=new_rule)
    assert res.status_code == 200
    assert res.json()["status"] == "success"

def test_websocket_call_flow():
    with client.websocket_connect("/ws/call") as ws:
        # Send text utterance
        ws.send_json({
            "type": "utterance",
            "patient_id": "pt_101",
            "text": "Aaj dinner mein kya hai?",
            "synthesize_audio": False,
        })
        resp = ws.receive_json()
        assert resp["type"] == "turn_result"
        assert resp["is_emergency"] is False
        assert len(resp["text"]) > 0

        # Send interrupt signal
        ws.send_json({
            "type": "interrupt",
            "played_fraction": 0.4,
        })
        resp_interrupt = ws.receive_json()
        assert resp_interrupt["type"] == "interrupted"

def test_onboarding_and_profile_crud():
    # 1. Create a new patient profile through onboarding
    new_profile = {
        "full_name": "Priya Sharma",
        "age": 29,
        "gender": "Female",
        "height_cm": 163.0,
        "weight_kg": 58.0,
        "activity_level": "Active",
        "primary_goal": "PCOS management and balanced nutrition",
        "medical_conditions": ["PCOS"],
        "dietary_preference": "Vegetarian",
        "allowed_exercise": ["Gym", "Walking", "Yoga"],
        "phone": "+919876543299"
    }
    create_res = client.post("/patient", json=new_profile)
    assert create_res.status_code == 200
    created_data = create_res.json()
    new_pid = created_data["patient_id"]
    assert new_pid.startswith("pt_")
    assert created_data["patient"]["full_name"] == "Priya Sharma"
    assert created_data["pep"]["dietary_preference"] == "Vegetarian"

    # 2. Retrieve the new patient profile
    get_res = client.get(f"/patient/{new_pid}")
    assert get_res.status_code == 200
    assert len(get_res.json()["meals"]) == 21  # 7 days * 3 meals

    # 3. Update the patient profile (e.g. changed weight and activity)
    update_res = client.put(f"/patient/{new_pid}", json={
        "weight_kg": 57.0,
        "primary_goal": "Strength and hormone balance"
    })
    assert update_res.status_code == 200
    assert update_res.json()["patient"]["weight_kg"] == 57.0
    assert update_res.json()["patient"]["primary_goal"] == "Strength and hormone balance"

def test_voice_turn_flow():
    res = client.post("/voice-turn", json={
        "patient_id": "pt_101",
        "utterance": "What should I eat for dinner?"
    })
    assert res.status_code == 200
    data = res.json()
    assert "final_response" in data
    assert "turn_id" in data

def test_rag_api_endpoints():
    # 1. List documents
    list_res = client.get("/rag/documents")
    assert list_res.status_code == 200
    docs = list_res.json()["documents"]
    assert len(docs) >= 3

    # 2. Upload a new document as draft
    upload_res = client.post("/rag/upload", json={
        "title": "API Uploaded Clinical Guide",
        "filename": "api_guide.txt",
        "file_type": "txt",
        "category": "clinical_remedy",
        "content_text": "# API Remedy\n\n## Ginger Water\nSip warm ginger water for morning nausea.",
        "author": "Dr. Test API",
        "auto_approve": False
    })
    assert upload_res.status_code == 200
    doc_id = upload_res.json()["document_id"]
    assert upload_res.json()["approval_status"] == "draft"

    # 3. Test that draft is not returned by query
    query_res = client.post("/rag/query", json={
        "query": "morning nausea ginger water",
        "patient_id": "pt_101",
        "top_k": 3
    })
    assert query_res.status_code == 200
    chunks = query_res.json()["chunks"]
    assert all(c["document_id"] != doc_id for c in chunks)

    # 4. Approve document
    approve_res = client.post(f"/rag/documents/{doc_id}/approve")
    assert approve_res.status_code == 200
    assert approve_res.json()["approval_status"] == "approved"

    # 5. Now query again, chunk should be retrieved
    query_approved_res = client.post("/rag/query", json={
        "query": "morning nausea ginger water",
        "patient_id": "pt_101",
        "top_k": 3
    })
    assert query_approved_res.status_code == 200
    chunks_after = query_approved_res.json()["chunks"]
    assert any(c["document_id"] == doc_id for c in chunks_after)

    # 6. Delete test document
    del_res = client.delete(f"/rag/documents/{doc_id}")
    assert del_res.status_code == 200
    assert del_res.json()["deleted"] is True

def test_rules_regex_test_and_rollback_endpoints():
    # Test regex playground
    test_res = client.post("/rules/test", json={
        "test_utterance": "Mujhe subah se pet me bahut bloating ho raha hai",
        "pattern": r"(?i)\b(bloating|pet\s+phool)\b",
        "keywords": ["bloating", "gas"]
    })
    assert test_res.status_code == 200
    data = test_res.json()
    assert data["matched"] is True
    assert "bloating" in data["keyword_hits"]

def test_rules_invalid_regex_rejected():
    res = client.post("/rules", json={
        "rule_code": "RULE_INVALID_REGEX",
        "category": "safety",
        "trigger_keywords": ["broken"],
        "trigger_pattern": r"[unclosed bracket",
        "clinical_remedy": "Some text",
        "author_name": "Test QA",
    })
    assert res.status_code == 400
    assert "Invalid regex" in res.json()["detail"]

def test_chat_stream_persistence():
    import uuid
    fresh_pid = f"pt_stream_{uuid.uuid4().hex[:6]}"
    res = client.post("/chat/stream", json={
        "patient_id": fresh_pid,
        "utterance": "Weight is now 74.5 kg",
        "session_id": "sess_stream_01",
        "turn_number": 1,
    })
    assert res.status_code == 200
    assert "text/event-stream" in res.headers["content-type"]
    body = res.text
    assert "[DONE]" in body

    # Verify message was saved to conversation history
    hist_res = client.get(f"/conversations/{fresh_pid}")
    assert hist_res.status_code == 200
    msgs = hist_res.json()["messages"]
    assert len(msgs) >= 2  # user and assistant
    assert any(m["role"] == "user" and "74.5" in m["content"] for m in msgs)

    # Verify memory was recorded
    mem_res = client.get(f"/patient/{fresh_pid}/memories")
    assert mem_res.status_code == 200
    mems = mem_res.json()["memories"]
    assert any(m["key"] == "weight_kg" and "74.5" in m["value"] for m in mems)

def test_fresh_user_clean_slate():
    import uuid
    fresh_pid = f"pt_fresh_{uuid.uuid4().hex[:6]}"
    chat_res = client.post("/chat", json={
        "patient_id": fresh_pid,
        "utterance": "Hello, good morning!",
        "turn_number": 1,
    })
    assert chat_res.status_code == 200
    data = chat_res.json()
    # Must NOT assume Ramesh
    assert "Ramesh" not in data["final_response"]
    assert "112" not in data["final_response"]  # Not an emergency

    # Patient has no prior meals
    profile_res = client.get(f"/patient/{fresh_pid}")
    assert len(profile_res.json()["meals"]) == 0


