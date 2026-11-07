"""Reliability & Chaos Evaluation Suite.

Chaos testing including HTTP 429 provider failover, consecutive failure circuit breaker,
and database disconnect/reconnection resilience.
"""
from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator

from disha_core.llm.client import (
    ConsecutiveFailureCircuitBreaker,
    DualProviderClient,
    LLMSettings,
    Provider,
    ProviderError,
)


class MockFailingPrimary(Provider):
    """Simulates consecutive HTTP 429 / Rate Limit responses."""

    def __init__(self, status_code: int = 429) -> None:
        self.call_count = 0
        self.status_code = status_code

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        self.call_count += 1
        raise ProviderError(
            f"Mock primary HTTP {self.status_code}",
            retryable=True,
            status_code=self.status_code,
        )
        if False:
            yield ""


class MockWorkingFallback(Provider):
    """Simulates healthy secondary fallback provider (e.g. Gemini Flash)."""

    def __init__(self, response_chunks: tuple[str, ...] = ("Aapka plan ", "bilkul safe hai.")) -> None:
        self.call_count = 0
        self.response_chunks = response_chunks

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        self.call_count += 1
        for chunk in self.response_chunks:
            yield chunk


class BrokenConnection:
    """Simulates a database connection that drops or fails queries."""

    async def fetch(self, query: str, *args: Any) -> Any:
        raise ConnectionResetError("Connection reset by peer")

    async def fetchval(self, query: str, *args: Any) -> Any:
        raise ConnectionResetError("Connection reset by peer")

    def transaction(self) -> Any:
        class _Tx:
            async def __aenter__(self) -> None:
                raise ConnectionResetError("Connection reset by peer")
            async def __aexit__(self, *args: Any) -> None:
                pass
        return _Tx()


async def _test_dual_provider_failover() -> tuple[bool, dict[str, Any]]:
    """Simulate consecutive HTTP 429 errors and verify seamless failover."""
    settings = LLMSettings(
        groq_api_key="mock",
        groq_model="mock-groq",
        gemini_api_key="mock",
        gemini_model="mock-gemini",
        first_token_timeout=2.0,
    )
    client = DualProviderClient(settings)
    mock_primary = MockFailingPrimary(status_code=429)
    mock_fallback = MockWorkingFallback(response_chunks=("Namaste! ", "Yeh fallback response hai."))

    # Inject mock providers
    client.providers = (mock_primary, mock_fallback)
    client.circuit = ConsecutiveFailureCircuitBreaker(threshold=2, cooldown=60.0)

    turns_output: list[str] = []

    # Turn 1: Primary fails with 429, fallback takes over
    t1_tokens = []
    async for token in client.stream("Turn 1 prompt"):
        t1_tokens.append(token)
    turns_output.append("".join(t1_tokens))

    turn1_ok = (
        turns_output[0] == "Namaste! Yeh fallback response hai."
        and mock_primary.call_count == 1
        and mock_fallback.call_count == 1
        and client.circuit.failures == 1
    )

    # Turn 2: Primary fails second time with 429, circuit trips OPEN
    t2_tokens = []
    async for token in client.stream("Turn 2 prompt"):
        t2_tokens.append(token)
    turns_output.append("".join(t2_tokens))

    turn2_ok = (
        turns_output[1] == "Namaste! Yeh fallback response hai."
        and mock_primary.call_count == 2
        and mock_fallback.call_count == 2
        and client.circuit.failures == 2
        and client.circuit.opened_at is not None
    )

    # Turn 3: Circuit is OPEN -> primary should be skipped immediately!
    t3_tokens = []
    async for token in client.stream("Turn 3 prompt"):
        t3_tokens.append(token)
    turns_output.append("".join(t3_tokens))

    turn3_ok = (
        turns_output[2] == "Namaste! Yeh fallback response hai."
        and mock_primary.call_count == 2  # Primary NOT called because circuit is OPEN
        and mock_fallback.call_count == 3
    )

    passed = turn1_ok and turn2_ok and turn3_ok
    details = {
        "turn1_failover_success": turn1_ok,
        "turn2_circuit_tripped": turn2_ok,
        "turn3_primary_skipped": turn3_ok,
        "primary_call_count": mock_primary.call_count,
        "fallback_call_count": mock_fallback.call_count,
        "circuit_failures": client.circuit.failures,
        "circuit_opened": client.circuit.opened_at is not None,
    }
    return passed, details


async def _test_database_disconnect_resilience() -> tuple[bool, dict[str, Any]]:
    """Test system resilience when database queries fail."""
    from disha_core.engine.retriever import retrieve_chunks

    broken_conn = BrokenConnection()
    caught_exception = False
    try:
        await retrieve_chunks(broken_conn, "bloating relief", use_cache=False)
    except ConnectionResetError:
        caught_exception = True

    details = {
        "caught_connection_reset": caught_exception,
        "graceful_error_propagation": caught_exception,
    }
    return caught_exception, details


def run_reliability_eval() -> dict[str, Any]:
    """Synchronous runner for the async reliability suite."""
    loop = asyncio.new_event_loop()
    try:
        failover_passed, failover_details = loop.run_until_complete(_test_dual_provider_failover())
        db_passed, db_details = loop.run_until_complete(_test_database_disconnect_resilience())
    finally:
        loop.close()

    overall_passed = failover_passed and db_passed
    score = 100.0 if overall_passed else (50.0 if (failover_passed or db_passed) else 0.0)

    return {
        "suite": "reliability_eval",
        "passed": overall_passed,
        "score": score,
        "provider_failover": {
            "passed": failover_passed,
            "details": failover_details,
        },
        "database_resilience": {
            "passed": db_passed,
            "details": db_details,
        },
    }


if __name__ == "__main__":
    import json
    res = run_reliability_eval()
    print(json.dumps(res, indent=2))

