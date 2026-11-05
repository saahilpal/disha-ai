# Disha AI — Clinical Voice AI Health Coach

Deterministic Hinglish Voice Follow-Up Engine with Sub-Second Turn Latency and Clinical Safety Guardrails.

---

## Quickstart

### 1. Environment Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Run Application
```bash
python -m uvicorn app.main:app --port 8000 --reload
```
Open [http://localhost:8000](http://localhost:8000) in your browser.

### 3. Run Automated Tests
```bash
pytest -v
```
Runs 38 tests across all 8 production failure scenarios, sub-millisecond safety guardrails, sentence buffering, barge-in interruption, and REST/WebSocket endpoints.

---

## Architecture & Failure Coverage

| # | Production Failure Mode | Deterministic Solution |
|---|---|---|
| 1 | **Hallucinated Pricing** | Verified pricing catalog in SQLite + Regex output boundary (₹0 / ₹1,499 only). |
| 2 | **Missed Clinical Remedy** | Doctor-authored carminative rule enforcing warm jeera-saunf water for bloating. |
| 3 | **False Delivery Promise (WhatsApp)** | Channel boundary filter intercepting external promises and rewriting to in-app *"My Plan"*. |
| 4 | **Persona Violation (Human Doctor Claim)** | Hard persona invariant disclosing *"Main Disha hoon, aapki AI health coach"*. |
| 5 | **Missed Red-Flag Emergency** | Pre-turn regex circuit breaker (<0.1ms) aborting LLM turn and guiding ambulance 112 triage. |
| 6 | **Ignored System Data (Dinner Lookup)** | Dynamic meal retrieval from SQLite by IST day of week + closed-domain fallback. |
| 7 | **Ignored PEP Context (Gym vs Home)** | PEP constraint injection acknowledging doctor clearance for gym progressive strength training. |
| 8 | **Clinical Stance Contradiction (Mango Ban)**| Institutional clinical stance permitting seasonal moderation (100g, daytime, protein pairing). |

