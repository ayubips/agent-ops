import time
import logging
import re
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


# --- Retry logic ---

class RetryExhaustedError(Exception):
    """Raised when all retry attempts fail."""
    pass


def _is_non_retryable(exc: Exception) -> bool:
    """
    Returns True for errors that will never succeed on retry — auth failures,
    permission errors, bad requests. Retrying these just wastes time and
    delays the circuit breaker from doing its job.
    """
    if isinstance(exc, requests.HTTPError):
        status = exc.response.status_code if exc.response is not None else None
        # 400/401/403/404 are permanent — retrying won't fix bad credentials
        # or a missing resource. 429 (rate limit) and 5xx ARE worth retrying.
        if status in (400, 401, 403, 404):
            return True
    return False


def with_retry(fn, step_name: str, max_retries: int = 3, base_delay: float = 1.0):
    """
    Calls fn() with exponential backoff on failure.
    Non-retryable errors (auth/permission/bad request) fail immediately
    without wasting retry attempts. Retries max_retries times for transient
    errors, then raises RetryExhaustedError.
    """
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            return fn()
        except Exception as e:
            last_error = e

            if _is_non_retryable(e):
                logging.warning(f"[{step_name}] non-retryable error, failing fast: {e}")
                raise RetryExhaustedError(f"[{step_name}] non-retryable failure: {e}")

            logging.warning(f"[{step_name}] attempt {attempt}/{max_retries} failed: {e}")
            if attempt < max_retries:
                delay = base_delay * (2 ** (attempt - 1))
                logging.info(f"[{step_name}] retrying in {delay:.1f}s...")
                time.sleep(delay)

    raise RetryExhaustedError(f"[{step_name}] failed after {max_retries} attempts: {last_error}")


# --- Circuit breaker ---

class CircuitOpenError(Exception):
    """Raised when a call is rejected because the circuit is open."""
    pass


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


# --- Relevance / quality check ---

class LowRelevanceError(Exception):
    """Raised when fetched content doesn't meaningfully overlap with the query."""
    pass


def _tokenize(text: str) -> set:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def check_relevance(query: str, texts: list[str], min_overlap: int = 2, min_text_length: int = 200):
    """
    Cheap, fast guard before spending an LLM call on synthesis.
    Rejects: empty texts, texts too short to be meaningful, or texts that share
    no keywords at all with the query (a strong signal of an off-topic/junk result).
    This is intentionally lightweight — not a semantic check, just a sanity filter.
    """
    if not texts:
        raise LowRelevanceError("no fetched texts to synthesize from")

    combined_length = sum(len(t) for t in texts)
    if combined_length < min_text_length:
        raise LowRelevanceError(f"fetched content too short ({combined_length} chars) to be useful")

    query_tokens = _tokenize(query)
    query_tokens = {t for t in query_tokens if len(t) > 3}

    combined_tokens = _tokenize(" ".join(texts))
    overlap = query_tokens & combined_tokens

    if len(overlap) < min_overlap:
        raise LowRelevanceError(
            f"no keyword overlap between query and fetched content "
            f"(query terms: {query_tokens}, found: 0 matching)"
        )


# --- Standalone tests ---

if __name__ == "__main__":
    # Test 1: always succeeds
    def always_works():
        return "success!"
    print(f"Test 1 (should succeed): {with_retry(always_works, step_name='test_success')}")

    # Test 2: fails twice then succeeds
    attempt_count = {"n": 0}
    def fails_twice_then_works():
        attempt_count["n"] += 1
        if attempt_count["n"] < 3:
            raise ConnectionError(f"simulated failure #{attempt_count['n']}")
        return "succeeded on attempt 3"
    print(f"Test 2 (should succeed after retries): "
          f"{with_retry(fails_twice_then_works, step_name='test_eventual_success', base_delay=0.5)}")

    # Test 3: always fails (transient error type)
    def always_fails():
        raise ConnectionError("permanent failure")
    try:
        with_retry(always_fails, step_name="test_always_fails", max_retries=3, base_delay=0.3)
    except RetryExhaustedError as e:
        print(f"Test 3 (should raise RetryExhaustedError): {e}")

    # Test 4: circuit breaker trips after threshold, then rejects fast
    breaker = CircuitBreaker(name="demo", failure_threshold=2, reset_timeout=2.0)
    for i in range(3):
        try:
            call_with_protection(always_fails, step_name="demo", breaker=breaker, max_retries=1, base_delay=0.1)
        except (RetryExhaustedError, CircuitOpenError) as e:
            print(f"Test 4 attempt {i+1}: {type(e).__name__} — {e}")

    # Test 5: non-retryable 401 fails fast, no backoff delay
    def raises_401():
        resp = requests.Response()
        resp.status_code = 401
        raise requests.HTTPError("401 test error", response=resp)

    start = time.time()
    try:
        with_retry(raises_401, step_name="test_401", max_retries=3, base_delay=1.0)
    except RetryExhaustedError as e:
        elapsed = time.time() - start
        print(f"Test 5 (401 should fail fast, no retries): {elapsed:.2f}s — {e}")

    # Test 6: relevant content passes
    try:
        check_relevance(
            query="benefits of Kubernetes autoscaling",
            texts=["Kubernetes autoscaling automatically adjusts pod replicas based on load and resource usage metrics."]
        )
        print("Test 6 (relevant content should pass): PASS")
    except LowRelevanceError as e:
        print(f"Test 6 FAILED (should have passed): {e}")

    # Test 7: off-topic content fails
    try:
        check_relevance(
            query="xyzabc nonsense query",
            texts=["The N+1 query problem is a common database performance issue in ORM-based applications."]
        )
        print("Test 7 FAILED (should have raised LowRelevanceError)")
    except LowRelevanceError as e:
        print(f"Test 7 (off-topic content should fail): PASS — {e}")

    # Test 8: empty texts fails
    try:
        check_relevance(query="anything", texts=[])
        print("Test 8 FAILED (should have raised on empty texts)")
    except LowRelevanceError as e:
        print(f"Test 8 (empty texts should fail): PASS — {e}")

    print("\nAll reliability.py standalone tests complete.")