import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.api.routes_simulation import run_regression_suite

@pytest.mark.asyncio
async def test_full_golden_regression_suite_direct():
    """
    Direct invocation of the automated golden regression suite.
    Asserts 100% pass rate and 100% emergency recall across all pinned scenarios.
    """
    report = await run_regression_suite()
    
    assert report["total_benchmarks"] >= 15
    assert report["failed"] == 0, f"Failures detected: {report['failures']}"
    assert report["pass_rate_pct"] == 100.0
    assert report["emergency_recall_pct"] == 100.0
    assert report["average_latency_ms"] < 100.0  # Ultra-fast mock/deterministic evaluation
    
    # Assert each failure category is represented and passed
    categories = report["category_breakdown"]
    assert "wrong_statement" in categories
    assert "missed_action" in categories
    assert "missing_fact" in categories
    assert categories["wrong_statement"]["passed"] == categories["wrong_statement"]["tested"]
    assert categories["missed_action"]["passed"] == categories["missed_action"]["tested"]
    assert categories["missing_fact"]["passed"] == categories["missing_fact"]["tested"]


@pytest.mark.asyncio
async def test_regression_suite_via_api_endpoint():
    """
    Invokes the regression suite over HTTP via FastAPI TestClient.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/v1/simulation/run-regression-suite")
        assert response.status_code == 200
        data = response.json()
        assert data["pass_rate_pct"] == 100.0
        assert data["emergency_recall_pct"] == 100.0
        assert data["failed"] == 0


@pytest.mark.asyncio
async def test_simulation_turn_api_endpoint():
    """
    Tests POST /api/v1/simulation/turn endpoint with both normal and emergency utterances.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Normal turn
        resp = await client.post("/api/v1/simulation/turn", json={
            "patient_id": "pt_101",
            "utterance": "Aapka naam kya hai aur aap kya karti ho?",
            "turn_number": 1
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["is_emergency"] is False
        assert "disha" in body["final_response"].lower()

        # 2. Emergency turn
        resp_emg = await client.post("/api/v1/simulation/turn", json={
            "patient_id": "pt_101",
            "utterance": "Seene mein bahut dard hai aur chakkar aa raha hai",
            "turn_number": 2
        })
        assert resp_emg.status_code == 200
        body_emg = resp_emg.json()
        assert body_emg["is_emergency"] is True
        assert "112" in body_emg["final_response"] or "ambulance" in body_emg["final_response"]
