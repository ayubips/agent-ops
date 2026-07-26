import time
import requests
import pytest

from src.reliability import (
    with_retry, RetryExhaustedError,
    CircuitBreaker, call_with_protection, CircuitOpenError,
    check_relevance, LowRelevanceError,
)


def test_retry_succeeds_first_try():
    assert with_retry(lambda: "ok", step_name="t") == "ok"


def test_retry_succeeds_after_transient_failures():
    calls = {"n": 0}
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("transient")
        return "recovered"
    assert with_retry(flaky, step_name="t", base_delay=0.1) == "recovered"


def test_retry_exhausts_and_raises():
    def always_fails():
        raise ConnectionError("down")
    with pytest.raises(RetryExhaustedError):
        with_retry(always_fails, step_name="t", max_retries=2, base_delay=0.1)


def test_non_retryable_401_fails_fast():
    def raises_401():
        resp = requests.Response()
        resp.status_code = 401
        raise requests.HTTPError("unauthorized", response=resp)

    start = time.time()
    with pytest.raises(RetryExhaustedError):
        with_retry(raises_401, step_name="t", max_retries=3, base_delay=1.0)
    assert time.time() - start < 0.5, "401 should fail fast without backoff delay"


def test_circuit_breaker_opens_after_threshold():
    breaker = CircuitBreaker(name="t", failure_threshold=2, reset_timeout=1.0)
    def always_fails():
        raise ConnectionError("down")

    for _ in range(2):
        with pytest.raises(RetryExhaustedError):
            call_with_protection(always_fails, step_name="t", breaker=breaker, max_retries=1, base_delay=0.05)

    assert breaker.is_open()
    with pytest.raises(CircuitOpenError):
        call_with_protection(always_fails, step_name="t", breaker=breaker, max_retries=1, base_delay=0.05)


def test_circuit_breaker_resets_after_timeout():
    breaker = CircuitBreaker(name="t", failure_threshold=1, reset_timeout=0.5)
    def always_fails():
        raise ConnectionError("down")

    with pytest.raises(RetryExhaustedError):
        call_with_protection(always_fails, step_name="t", breaker=breaker, max_retries=1, base_delay=0.05)
    assert breaker.is_open()

    time.sleep(0.6)
    assert not breaker.is_open()


def test_relevance_passes_for_matching_content():
    check_relevance(
        query="benefits of Kubernetes autoscaling",
        texts=["Kubernetes autoscaling automatically adjusts pod replicas based on load. "
               "It monitors CPU and memory utilization across the cluster and scales resources "
               "up or down accordingly. This helps maintain application performance during traffic "
               "spikes while reducing costs during periods of low demand. Horizontal Pod Autoscaling "
               "and Cluster Autoscaler are the two primary mechanisms used to achieve this."]
    )  # should not raise


def test_relevance_fails_for_offtopic_content():
    with pytest.raises(LowRelevanceError):
        check_relevance(
            query="xyzabc nonsense query",
            texts=["The N+1 query problem is a database performance issue."]
        )


def test_relevance_fails_for_empty_texts():
    with pytest.raises(LowRelevanceError):
        check_relevance(query="anything", texts=[])

def test_fallback_returns_something_on_empty_texts():
    from src.llm_client import LLMClient
    client = LLMClient()
    result = client.fallback_summary([])
    assert result["text"]
    assert result["tokens"] == 0


def test_relevance_passes_with_multiple_texts_partial_match():
    # only ONE of two texts is relevant — should still pass since check_relevance
    # looks at combined content, not per-text
    check_relevance(
        query="Kubernetes autoscaling",
        texts=[
            "This document is about cooking recipes and has nothing to do with technology. "
            "It covers basic knife skills, ingredient preparation, and common cooking techniques "
            "used in everyday home kitchens around the world.",
            "Kubernetes autoscaling adjusts pod replicas based on load metrics such as CPU and "
            "memory usage. This allows applications to handle variable traffic efficiently while "
            "minimizing infrastructure costs during quiet periods."
        ]
    )  # should not raise