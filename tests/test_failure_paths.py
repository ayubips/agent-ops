import sys
import time
sys.path.insert(0, ".")

from src.reliability import CircuitBreaker, CircuitOpenError, call_with_protection, RetryExhaustedError


def test_circuit_opens_after_threshold():
    breaker = CircuitBreaker(name="test", failure_threshold=3, reset_timeout=2.0)

    def always_fails():
        raise ConnectionError("simulated down service")

    # first 3 calls should each fail via RetryExhaustedError, tripping the breaker
    for i in range(3):
        try:
            call_with_protection(always_fails, step_name="test", breaker=breaker, max_retries=1, base_delay=0.1)
        except RetryExhaustedError:
            pass

    assert breaker.is_open(), "breaker should be open after threshold failures"
    print("PASS: breaker opens after threshold failures")

    # next call should reject immediately with CircuitOpenError, no retries wasted
    try:
        call_with_protection(always_fails, step_name="test", breaker=breaker, max_retries=1, base_delay=0.1)
        print("FAIL: expected CircuitOpenError")
    except CircuitOpenError:
        print("PASS: breaker rejects calls immediately while open")


def test_circuit_recovers_after_timeout():
    breaker = CircuitBreaker(name="test2", failure_threshold=1, reset_timeout=1.0)

    def fails_once_then_works():
        if breaker.failure_count == 0:
            raise ConnectionError("first call fails")
        return "recovered"

    try:
        call_with_protection(lambda: (_ for _ in ()).throw(ConnectionError("fail")),
                              step_name="test2", breaker=breaker, max_retries=1, base_delay=0.1)
    except RetryExhaustedError:
        pass

    assert breaker.is_open()
    print("PASS: breaker opened")

    time.sleep(1.1)  # wait past reset_timeout
    assert not breaker.is_open(), "breaker should allow calls again after cooldown"
    print("PASS: breaker resets after cooldown")


if __name__ == "__main__":
    test_circuit_opens_after_threshold()
    test_circuit_recovers_after_timeout()
    print("\nAll circuit breaker tests passed.")