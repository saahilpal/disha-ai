#!/usr/bin/env python3
"""Interactive CLI helper for Subagent User Simulators to talk directly to Disha AI backend.

Allows an agent to dynamically register a synthetic patient and send individual conversational turns,
observing Disha's real response while automatically logging the transcript with precise timestamps and latencies.
"""

import argparse
import json
import os
import sys
import time

import httpx

BACKEND_URL = os.getenv("DISHA_HTTP_URL", "http://127.0.0.1:8080")
SESSION_DIR = "audit/simulations"


def register(
    session_name: str,
    name: str,
    age: int,
    gender: str,
    conditions: list[str],
    language: str = "hinglish",
    focuses: list[str] = None,
):
    os.makedirs(SESSION_DIR, exist_ok=True)
    session_file = os.path.join(SESSION_DIR, f"{session_name}_session.json")

    payload = {
        "name": name,
        "email": f"{session_name}.{int(time.time())}@disha.ai",
        "password": "Password123!",
        "age": age,
        "gender": gender,
        "height_cm": 175.0,
        "weight_kg": 72.0,
        "conditions": conditions,
        "hypertension_stage": "stage 2" if any("hypertension" in c.lower() for c in conditions) else "normal",
        "gym_clearance": False if any("hypertension" in c.lower() for c in conditions) else True,
        "activity_level": "moderate",
        "dietary_preference": "Vegetarian",
        "health_goals": ["Daily Health and Energy Optimization"],
        "language": language,
        "health_focuses": focuses or ["Fitness and general wellness"],
        "health_focus_other": "",
    }

    with httpx.Client(timeout=15.0) as client:
        res = client.post(f"{BACKEND_URL}/auth/register", json=payload)
        if res.status_code != 200:
            print(f"ERROR: Registration failed ({res.status_code}): {res.text}", file=sys.stderr)
            sys.exit(1)
        data = res.json()
        session_info = {
            "session_name": session_name,
            "patient_id": data["patient_id"],
            "token": data["token"],
            "user_name": name,
            "profile": payload,
            "turn_count": 0,
            "created_at": time.time(),
        }
        with open(session_file, "w") as f:
            json.dump(session_info, f, indent=2)
        print(f"SUCCESS: Registered {name} (ID: {data['patient_id']}) under session '{session_name}'.")


def send_turn(session_name: str, message: str):
    session_file = os.path.join(SESSION_DIR, f"{session_name}_session.json")
    transcript_file = os.path.join(SESSION_DIR, f"{session_name}_live_transcript.jsonl")

    if not os.path.exists(session_file):
        print(f"ERROR: Session '{session_name}' not found. Run register first.", file=sys.stderr)
        sys.exit(1)

    with open(session_file, "r") as f:
        session_info = json.load(f)

    token = session_info["token"]
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    t0 = time.perf_counter()
    try:
        with httpx.Client(timeout=20.0) as client:
            res = client.post(f"{BACKEND_URL}/chat", headers=headers, json={"text": message})
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        if res.status_code == 200:
            data = res.json()
            response_text = data.get("response", "")
            status = data.get("status", "unknown")
        else:
            response_text = f"HTTP {res.status_code}: {res.text}"
            status = "http_error"
    except Exception as e:
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        response_text = str(e)
        status = "client_exception"

    session_info["turn_count"] += 1
    turn_num = session_info["turn_count"]
    with open(session_file, "w") as f:
        json.dump(session_info, f, indent=2)

    record = {
        "turn": turn_num,
        "timestamp": time.time(),
        "elapsed_sec": round(time.time() - session_info["created_at"], 1),
        "user": message,
        "disha": response_text,
        "status": status,
        "latency_ms": latency_ms,
    }
    with open(transcript_file, "a") as f:
        f.write(json.dumps(record) + "\n")

    # Print clean response for the agent to read
    print(f"[Turn {turn_num} | {latency_ms}ms | {status}] Disha:\n{response_text}")


def main():
    parser = argparse.ArgumentParser(description="Disha Live Chat CLI for Subagents")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Register command
    reg_parser = subparsers.add_parser("register")
    reg_parser.add_argument("--session", required=True, help="Short session identifier (e.g. rohan, meera, kabir)")
    reg_parser.add_argument("--name", required=True, help="Patient full name")
    reg_parser.add_argument("--age", type=int, default=30, help="Patient age")
    reg_parser.add_argument("--gender", default="male", help="male or female")
    reg_parser.add_argument("--conditions", nargs="*", default=[], help="Medical conditions")
    reg_parser.add_argument("--language", default="hinglish", help="english, hindi, or hinglish")
    reg_parser.add_argument("--focuses", nargs="*", default=["General wellness"], help="Health focuses")

    # Send turn command
    send_parser = subparsers.add_parser("send")
    send_parser.add_argument("--session", required=True, help="Session identifier")
    send_parser.add_argument("--message", required=True, help="Message text from the user")

    args = parser.parse_args()
    if args.command == "register":
        register(args.session, args.name, args.age, args.gender, args.conditions, args.language, args.focuses)
    elif args.command == "send":
        send_turn(args.session, args.message)


if __name__ == "__main__":
    main()
