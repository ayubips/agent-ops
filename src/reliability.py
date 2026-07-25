import time
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


class RetryExhaustedError(Exception):
    """Raised when all retry attempts fail."""
    pass


class CircuitOpenError(Exception):
    """Raised when a call is rejected because the circuit is open."""
    pass


def with_retry(fn, step_name: str, max_retries: int = 3, base_delay: float = 1.0):
    """
    Calls fn() with exponential backoff on failure.
    Retries max_retries times, then raises RetryExhaustedError with the last error attached.
    """
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            return fn()
        except Exception as e:
            last_error = e
            logging.warning(f"[{step_name}] attempt {attempt}/{max_retries} failed: {e}")
            if attempt < max_retries:
                delay = base_delay * (2 ** (attempt - 1))
                logging.info(f"[{step_name}] retrying in {delay:.1f}s...")
                time.sleep(delay)

    raise RetryExhaustedError(f"[{step_name}] failed after {max_retries} attempts: {last_error}")


class CircuitBreaker:
    """
    Tracks failures for a named dependency. After `failure_threshold`
    consecutive failures, the circuit "opens" and rejects calls immediately
    (no wasted retries/latency) until `reset_timeout` seconds pass, at which
    point it allows calls through again (half-open) to test recovery.
    """
    def __init__(self, name: str, failure_threshold: int = 3, reset_timeout: float = 30.0):
        self.name = name
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.failure_count = 0
        self.opened_at = None

    def is_open(self) -> bool:
        if self.opened_at is None:
            return False
        if time.time() - self.opened_at >= self.reset_timeout:
            logging.info(f"[circuit:{self.name}] cooldown elapsed, moving to half-open")
            self.opened_at = None
            self.failure_count = 0
            return False
        return True

    def record_success(self):
        if self.failure_count > 0:
            logging.info(f"[circuit:{self.name}] recovered, resetting failure count")
        self.failure_count = 0
        self.opened_at = None

    def record_failure(self):
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold and self.opened_at is None:
            self.opened_at = time.time()
            logging.warning(f"[circuit:{self.name}] OPENED after {self.failure_count} failures — "
                             f"rejecting calls for {self.reset_timeout}s")

    def call(self, fn):
        if self.is_open():
            raise CircuitOpenError(f"[circuit:{self.name}] is open, call rejected")
        try:
            result = fn()
            self.record_success()
            return result
        except Exception:
            self.record_failure()
            raise


def call_with_protection(fn, step_name: str, breaker: CircuitBreaker, max_retries: int = 3, base_delay: float = 1.0):
    """
    Checks the circuit breaker first (fails fast if open), then retries with
    backoff if the circuit is closed. A full retry exhaustion counts as one
    failure event against the breaker.
    """
    if breaker.is_open():
        raise CircuitOpenError(f"[{step_name}] circuit open, skipping call")

    try:
        result = with_retry(fn, step_name=step_name, max_retries=max_retries, base_delay=base_delay)
        breaker.record_success()
        return result
    except RetryExhaustedError:
        breaker.record_failure()
        raise


if __name__ == "__main__":
    # --- retry tests ---
    def always_works():
        return "success!"
    print(f"Test 1 (should succeed): {with_retry(always_works, step_name='test_success')}")

    attempt_count = {"n": 0}
    def fails_twice_then_works():
        attempt_count["n"] += 1
        if attempt_count["n"] < 3:
            raise ConnectionError(f"simulated failure #{attempt_count['n']}")
        return "succeeded on attempt 3"
    print(f"Test 2 (should succeed after retries): "
          f"{with_retry(fails_twice_then_works, step_name='test_eventual_success', base_delay=0.5)}")

    def always_fails():
        raise ConnectionError("permanent failure")
    try:
        with_retry(always_fails, step_name="test_always_fails", max_retries=3, base_delay=0.3)
    except RetryExhaustedError as e:
        print(f"Test 3 (should raise RetryExhaustedError): {e}")

    # --- circuit breaker test ---
    breaker = CircuitBreaker(name="demo", failure_threshold=2, reset_timeout=2.0)
    for i in range(3):
        try:
            call_with_protection(always_fails, step_name="demo", breaker=breaker, max_retries=1, base_delay=0.1)
        except (RetryExhaustedError, CircuitOpenError) as e:
            print(f"Test 4 attempt {i+1}: {type(e).__name__} — {e}")