import time
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


class RetryExhaustedError(Exception):
    """Raised when all retry attempts fail."""
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


if __name__ == "__main__":
    # test 1: a function that always succeeds
    def always_works():
        return "success!"

    result = with_retry(always_works, step_name="test_success")
    print(f"Test 1 (should succeed): {result}")

    # test 2: a function that fails twice then succeeds
    attempt_count = {"n": 0}
    def fails_twice_then_works():
        attempt_count["n"] += 1
        if attempt_count["n"] < 3:
            raise ConnectionError(f"simulated failure #{attempt_count['n']}")
        return "succeeded on attempt 3"

    result = with_retry(fails_twice_then_works, step_name="test_eventual_success", base_delay=0.5)
    print(f"Test 2 (should succeed after retries): {result}")

    # test 3: a function that always fails
    def always_fails():
        raise ConnectionError("permanent failure")

    try:
        with_retry(always_fails, step_name="test_always_fails", max_retries=3, base_delay=0.3)
    except RetryExhaustedError as e:
        print(f"Test 3 (should raise RetryExhaustedError): {e}")