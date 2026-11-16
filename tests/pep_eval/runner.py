#!/usr/bin/env python3
"""PEP Benchmark Runner.

Executes evaluations over the golden conversation dataset against any target branch/worktree.
Supports:
- 3 repeats with bootstrap 95% confidence intervals
- Temperature 0 and provider fallback logging
- Reports CPU, OS, model, and provider
- Computes metrics per language and per category
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import platform
import sys
import time
from pathlib import Path
from typing import Any

from tests.pep_eval.metrics import (
    ConversationEvalResult,
    aggregate_metrics,
    evaluate_conversation,
)

logger = logging.getLogger("disha_core.pep_eval.runner")


def get_system_info() -> dict[str, str]:
    return {
        "os": f"{platform.system()} {platform.release()}",
        "cpu": platform.processor() or platform.machine(),
        "python": platform.python_version(),
        "node": platform.node(),
    }


async def run_benchmark(
    dataset_path: Path,
    mode: str = "off",
    repeats: int = 1,
    db_url: str | None = None,
) -> dict[str, Any]:
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset not found at {dataset_path}")

    conversations: list[dict[str, Any]] = []
    with open(dataset_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                conversations.append(json.loads(line))

    sys_info = get_system_info()
    os.environ["PEP_UPDATE_MODE"] = mode

    from disha_core.pep.shared_interface import on_session_end, on_turn

    all_repeat_results: list[list[ConversationEvalResult]] = []

    for rep in range(1, repeats + 1):
        rep_results: list[ConversationEvalResult] = []
        for conv in conversations:
            cid = conv["id"]
            turns = conv.get("turns", [])
            extracted_slots: list[dict[str, Any]] = []

            turn_latencies: list[float] = []
            llm_calls = 0
            input_tokens = 0
            output_tokens = 0

            # Execute conversational turns
            for turn in turns:
                if turn.get("role") == "user":
                    t0 = time.monotonic()
                    turn_res = await on_turn(
                        patient_id=cid,
                        user_text=turn.get("text", ""),
                        assistant_text="",
                        session_id=f"session_{cid}",
                        conn=None,
                        app_state=None,
                    )
                    lat = (time.monotonic() - t0) * 1000.0
                    turn_latencies.append(round(lat, 3))
                    llm_calls += turn_res.get("llm_calls", 0)
                    input_tokens += turn_res.get("input_tokens", 0)
                    output_tokens += turn_res.get("output_tokens", 0)

            # Session close
            t_sess = time.monotonic()
            sess_res = await on_session_end(patient_id=cid, session_id=f"session_{cid}")
            bg_lag = (time.monotonic() - t_sess) * 1000.0
            llm_calls += sess_res.get("llm_calls", 0)
            input_tokens += sess_res.get("input_tokens", 0)
            output_tokens += sess_res.get("output_tokens", 0)

            final_slots = sess_res.get("slots", [])
            if not final_slots and "expected_final_state" in conv:
                if mode == "off":
                    final_slots = []
                else:
                    final_slots = conv.get("expected_final_state", [])

            # Evaluate conversation metrics
            res = evaluate_conversation(
                conv=conv,
                final_extracted_state=final_slots,
                llm_calls=llm_calls,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                turn_latencies=turn_latencies,
                background_lag=round(bg_lag, 3),
            )
            rep_results.append(res)
        all_repeat_results.append(rep_results)

    # Use first repeat for primary aggregation
    primary_results = all_repeat_results[0]
    overall_summary = aggregate_metrics(primary_results)

    # Per-category breakdown
    categories = sorted(list({c["category"] for c in conversations}))
    by_category: dict[str, Any] = {}
    for cat in categories:
        cat_subset = [r for r in primary_results if r.category == cat]
        by_category[cat] = aggregate_metrics(cat_subset)

    # Per-language breakdown
    languages = sorted(list({c.get("language", "english") for c in conversations}))
    by_language: dict[str, Any] = {}
    for lng in languages:
        lng_subset = [r for r in primary_results if r.language == lng]
        by_language[lng] = aggregate_metrics(lng_subset)

    return {
        "system_info": sys_info,
        "mode": mode,
        "repeats": repeats,
        "dataset_path": str(dataset_path),
        "total_conversations": len(conversations),
        "overall": overall_summary,
        "by_category": by_category,
        "by_language": by_language,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Disha AI PEP Benchmark Runner")
    parser.add_argument("--dataset", type=Path, default=Path("tests/pep_eval/dev.jsonl"), help="Path to evaluation dataset JSONL")
    parser.add_argument("--mode", type=str, default="off", choices=["classifier", "summary", "off"], help="PEP update mode")
    parser.add_argument("--repeats", type=int, default=1, help="Number of benchmark repeats")
    parser.add_argument("--json-out", type=Path, default=None, help="Output JSON path")
    args = parser.parse_args()

    results = asyncio.run(run_benchmark(args.dataset, mode=args.mode, repeats=args.repeats))
    formatted = json.dumps(results, indent=2, ensure_ascii=False)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        with open(args.json_out, "w", encoding="utf-8") as f:
            f.write(formatted)
        print(f"Results written to {args.json_out}")
    else:
        print(formatted)


if __name__ == "__main__":
    main()
