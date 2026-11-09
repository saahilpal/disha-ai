#!/usr/bin/env python3
"""Automated Golden Evaluation Suite for Disha AI Core.

Executes all 12 golden benchmark evaluation test cases from audit/golden_eval_set.json
against the live running backend (http://127.0.0.1:8080).
Evaluates clinical safety, PEP personalization, pricing transparency, channel boundary,
persona identity, and language grounding.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

BACKEND_URL = os.getenv("DISHA_HTTP_URL", "http://127.0.0.1:8080")
GOLDEN_SET_PATH = Path("audit/golden_eval_set.json")
REPORT_PATH = Path("audit/reports/golden_eval_results.json")


def register_user(client: httpx.Client, profile: dict[str, Any]) -> str:
    """Registers a fresh patient matching the golden profile and returns bearer token."""
    email = f"golden_{uuid.uuid4().hex[:8]}@eval.disha.ai"
    conditions = profile.get("conditions", [])
    htn_stage = "stage 2" if any("stage 2" in str(c).lower() or "hypertension" in str(c).lower() for c in conditions) else "normal"
    gym_clear = profile.get("gym_clearance", False if htn_stage != "normal" else True)
    
    payload = {
        "name": profile.get("name", "Golden Test User"),
        "email": email,
        "password": "Password123!",
        "age": profile.get("age", 30),
        "gender": profile.get("gender", "other"),
        "height_cm": 170.0,
        "weight_kg": 68.0,
        "conditions": conditions,
        "hypertension_stage": htn_stage,
        "gym_clearance": gym_clear,
        "activity_level": "moderate",
        "dietary_preference": "Vegetarian",
        "health_goals": ["Fitness and general wellness"],
        "language": profile.get("language", "hinglish"),
        "health_focuses": profile.get("health_focuses", ["General Wellness"]),
        "health_focus_other": "",
    }
    
    res = client.post(f"{BACKEND_URL}/auth/register", json=payload, timeout=10.0)
    if res.status_code != 200:
        raise RuntimeError(f"Failed to register patient: {res.status_code} - {res.text}")
    return res.json()["token"]


def evaluate_golden_set():
    print("=== Disha AI Golden Evaluation Suite ===")
    print(f"Target: {BACKEND_URL}")
    print(f"Golden Set: {GOLDEN_SET_PATH}\n")
    
    if not GOLDEN_SET_PATH.exists():
        print(f"ERROR: {GOLDEN_SET_PATH} not found!")
        sys.exit(1)
        
    with open(GOLDEN_SET_PATH) as f:
        eval_data = json.load(f)
        
    test_cases = eval_data.get("test_cases", [])
    results: list[dict[str, Any]] = []
    
    passed_count = 0
    total_count = len(test_cases)
    
    with httpx.Client(timeout=30.0) as client:
        for idx, case in enumerate(test_cases, 1):
            case_id = case["case_id"]
            category = case["category"]
            user_profile = case.get("user_profile", {})
            utterance = case["user_utterance"]
            pass_regex = case.get("pass_criteria_regex", "")
            forbidden = case.get("forbidden_behavior", [])
            
            print(f"[{idx}/{total_count}] Testing {case_id} ({category})...")
            print(f"     User: \"{utterance}\"")
            
            # 1. Resolve token
            if user_profile.get("patient_id") == "pt_test_01":
                token = "pt_test_01_valid_bearer_token"
            else:
                token = register_user(client, user_profile)
                
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            
            t0 = time.perf_counter()
            try:
                res = client.post(f"{BACKEND_URL}/chat", headers=headers, json={"text": utterance})
                latency_ms = round((time.perf_counter() - t0) * 1000, 2)
                
                if res.status_code != 200:
                    status = "http_error"
                    response_text = f"HTTP {res.status_code}: {res.text}"
                    is_pass = False
                    fail_reason = f"Non-200 HTTP status code: {res.status_code}"
                else:
                    data = res.json()
                    response_text = data.get("response", "")
                    status = data.get("status", "unknown")
                    
                    if status == "provider_unavailable":
                        is_pass = False
                        fail_reason = "Provider unavailable (LLM failed or timed out)"
                    elif not re.search(pass_regex, response_text, re.IGNORECASE):
                        is_pass = False
                        fail_reason = f"Pass criteria regex '{pass_regex}' did not match response"
                    else:
                        is_pass = True
                        fail_reason = None
            except Exception as exc:
                latency_ms = round((time.perf_counter() - t0) * 1000, 2)
                status = "exception"
                response_text = str(exc)
                is_pass = False
                fail_reason = f"Client exception: {exc}"
                
            if is_pass:
                passed_count += 1
                print(f"     => PASS ({latency_ms}ms) [status: {status}]")
            else:
                print(f"     => FAIL ({latency_ms}ms) [status: {status}]: {fail_reason}")
                
            print(f"     Disha: \"{response_text[:140]}...\"\n")
            
            results.append({
                "case_id": case_id,
                "category": category,
                "severity": case.get("severity", "MEDIUM"),
                "utterance": utterance,
                "response": response_text,
                "status": status,
                "latency_ms": latency_ms,
                "pass_criteria_regex": pass_regex,
                "passed": is_pass,
                "fail_reason": fail_reason,
            })
            
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "timestamp": time.time(),
        "total": total_count,
        "passed": passed_count,
        "failed": total_count - passed_count,
        "pass_rate_pct": round((passed_count / total_count) * 100, 2),
        "results": results,
    }
    with open(REPORT_PATH, "w") as f:
        json.dump(summary, f, indent=2)
        
    print("========================================")
    print(f"Golden Eval Results: {passed_count}/{total_count} Passed ({summary['pass_rate_pct']}%)")
    print(f"Detailed Report: {REPORT_PATH}")
    print("========================================")
    
    if passed_count != total_count:
        sys.exit(1)


if __name__ == "__main__":
    evaluate_golden_set()
