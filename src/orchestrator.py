from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
import uuid
import time

from src.tools import search, fetch
from src.llm_client import LLMClient
from src.reliability import (
    with_retry, RetryExhaustedError, CircuitBreaker,
    call_with_protection, CircuitOpenError,
    check_relevance, LowRelevanceError
)
from src.observability import init_db, log_run_start, log_step, log_run_finish


class StepStatus(Enum):
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class StepResult:
    name: str
    status: StepStatus
    output: dict = None
    error: str = None
    latency_ms: float = 0
    tokens_used: int = 0


@dataclass
class RunState:
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    query: str = ""
    steps: list = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.utcnow)


class ResearchAgent:
    def __init__(self):
        self.llm = LLMClient()
        self.search_breaker = CircuitBreaker(name="search", failure_threshold=3, reset_timeout=30)
        self.fetch_breaker = CircuitBreaker(name="fetch", failure_threshold=3, reset_timeout=30)
        self.llm_breaker = CircuitBreaker(name="llm", failure_threshold=3, reset_timeout=30)
        init_db()

    def run(self, query: str) -> RunState:
        state = RunState(query=query)
        log_run_start(state.run_id, query)

        # Step 1: search (retry + circuit breaker)
        start = time.time()
        try:
            search_result = call_with_protection(
                lambda: search.run(query), step_name="search",
                breaker=self.search_breaker
            )
            status = StepStatus.SUCCESS
            error = None
        except (RetryExhaustedError, CircuitOpenError) as e:
            search_result = {"urls": [], "snippets": []}
            status = StepStatus.FAILED
            error = str(e)
        latency = (time.time() - start) * 1000
        state.steps.append(StepResult(
            name="search", status=status, output=search_result,
            error=error, latency_ms=latency
        ))

        if status == StepStatus.FAILED:
            return state  # no point continuing without search results

        # Step 2: fetch (retry + circuit breaker)
        start = time.time()
        try:
            fetch_result = call_with_protection(
                lambda: fetch.run(search_result["urls"]), step_name="fetch",
                breaker=self.fetch_breaker
            )
            status = StepStatus.SUCCESS
            error = None
        except (RetryExhaustedError, CircuitOpenError) as e:
            fetch_result = {"texts": [], "failed_urls": []}
            status = StepStatus.FAILED
            error = str(e)
        latency = (time.time() - start) * 1000
        state.steps.append(StepResult(
            name="fetch", status=status, output=fetch_result,
            error=error, latency_ms=latency
        ))

        if not fetch_result["texts"]:
            state.steps.append(StepResult(
                name="synthesize", status=StepStatus.FAILED,
                error="no fetched content available to synthesize"
            ))
            return state

        # Relevance gate — catches off-topic/junk results before an LLM call
        try:
            check_relevance(query, fetch_result["texts"])
        except LowRelevanceError as e:
            state.steps.append(StepResult(
                name="synthesize", status=StepStatus.FAILED,
                error=f"relevance check failed: {e}"
            ))
            return state

        # Step 3: synthesize (retry + circuit breaker, with graceful fallback)
        start = time.time()
        try:
            synth_result = call_with_protection(
                lambda: self.llm.synthesize(fetch_result["texts"]),
                step_name="synthesize", breaker=self.llm_breaker
            )
            status = StepStatus.SUCCESS
            error = None
            tokens = synth_result["tokens"]
        except (RetryExhaustedError, CircuitOpenError) as e:
            # degrade gracefully instead of failing the whole run
            synth_result = self.llm.fallback_summary(fetch_result["texts"])
            status = StepStatus.SUCCESS  # fallback counts as a (degraded) success
            error = f"used fallback: {e}"
            tokens = 0
        latency = (time.time() - start) * 1000
        state.steps.append(StepResult(
            name="synthesize", status=status, output=synth_result,
            error=error, latency_ms=latency, tokens_used=tokens
        ))

        return state


if __name__ == "__main__":
    agent = ResearchAgent()
    state = agent.run("latest developments in AI agent orchestration")

    print(f"\nRun ID: {state.run_id}")
    print(f"Query: {state.query}\n")
    for step in state.steps:
        print(f"[{step.name}] {step.status.value} — {step.latency_ms:.0f}ms" +
              (f" — NOTE: {step.error}" if step.error else ""))

    last_step = state.steps[-1]
    if last_step.output and last_step.output.get("text"):
        print(f"\nFinal summary:\n{last_step.output['text']}")
    else:
        print(f"\nPipeline failed at step '{last_step.name}': {last_step.error}")