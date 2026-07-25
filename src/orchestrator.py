from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
import uuid
import time

from src.tools import search, fetch
from src.llm_client import LLMClient


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

    def run(self, query: str) -> RunState:
        state = RunState(query=query)

        start = time.time()
        search_result = search.run(query)
        latency = (time.time() - start) * 1000
        state.steps.append(StepResult(
            name="search", status=StepStatus.SUCCESS,
            output=search_result, latency_ms=latency
        ))

        start = time.time()
        fetch_result = fetch.run(search_result["urls"])
        latency = (time.time() - start) * 1000
        state.steps.append(StepResult(
            name="fetch", status=StepStatus.SUCCESS,
            output=fetch_result, latency_ms=latency
        ))

        start = time.time()
        synth_result = self.llm.synthesize(fetch_result["texts"])
        latency = (time.time() - start) * 1000
        state.steps.append(StepResult(
            name="synthesize", status=StepStatus.SUCCESS,
            output=synth_result, latency_ms=latency,
            tokens_used=synth_result["tokens"]
        ))

        return state


if __name__ == "__main__":
    agent = ResearchAgent()
    state = agent.run("latest developments in AI agent orchestration")

    print(f"\nRun ID: {state.run_id}")
    print(f"Query: {state.query}\n")
    for step in state.steps:
        print(f"[{step.name}] {step.status.value} — {step.latency_ms:.0f}ms")
    print(f"\nFinal summary:\n{state.steps[-1].output['text']}")