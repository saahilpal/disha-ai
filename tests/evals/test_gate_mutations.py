"""Pytest Suite for Gate Mutation Self-Tests (Section 11).

Executes synthetic defect injections against repository and quality gates to prove
that every planted defect fails closed:
1. Planted hardcoded reply
2. Planted secret leak
3. Planted dead file
4. Planted duplicate file overlap
5. Planted test count reduction
"""
from __future__ import annotations

from scripts.benchmark_gate_mutations import (
    run_mutation_1_hardcoded_reply,
    run_mutation_2_secret_leak,
    run_mutation_3_dead_file,
    run_mutation_4_file_overlap,
    run_mutation_5_deleted_test,
)


def test_gate_mutation_1_hardcoded_reply() -> None:
    res = run_mutation_1_hardcoded_reply()
    assert res["caught"] is True, f"Gate failed to catch hardcoded price: {res}"


def test_gate_mutation_2_secret_leak() -> None:
    res = run_mutation_2_secret_leak()
    assert res["caught"] is True, f"Gate failed to catch secret leak: {res}"


def test_gate_mutation_3_dead_file() -> None:
    res = run_mutation_3_dead_file()
    assert res["caught"] is True, f"Gate failed to catch dead temporary file: {res}"


def test_gate_mutation_4_file_overlap() -> None:
    res = run_mutation_4_file_overlap()
    assert res["caught"] is True, f"Gate failed to catch duplicate file overlap: {res}"


def test_gate_mutation_5_deleted_test() -> None:
    res = run_mutation_5_deleted_test()
    assert res["caught"] is True, f"Gate failed to catch test count reduction: {res}"
