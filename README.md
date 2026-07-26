# Agent Ops

A reliability and observability layer for multi-step LLM agents — built to answer
a question most agent demos skip: **what happens when a step fails?**

This project implements a research agent (search → fetch → synthesize) wrapped in
production-style infrastructure: retries with exponential backoff, circuit breakers
per dependency, a relevance gate to catch off-topic results, graceful degradation
via fallback responses, and structured observability (cost, latency, token usage)
logged to SQLite.

## Why this exists

Most "AI agent" demos show the happy path. In practice, LLM APIs rate-limit, search
APIs return junk, and dependencies go down. This project treats those as first-class
concerns rather than afterthoughts — the same way you'd treat failure handling in any
distributed system.

## Architecture

\```
                 ┌─────────────┐
   query ──────▶│ ResearchAgent│
                 └──────┬───────┘
                        │
        ┌───────────────┼───────────────┐
        ▼                ▼                ▼
   ┌─────────┐     ┌─────────┐     ┌────────────┐
   │  search  │────▶│  fetch  │────▶│ synthesize │
   │ (Tavily) │     │ (HTML)  │     │  (Groq)    │
   └────┬─────┘     └────┬────┘     └─────┬──────┘
        │                 │                 │
        └────────┬────────┴────────┬────────┘
                  ▼                 ▼
          ┌───────────────┐  ┌──────────────┐
          │  reliability   │  │ observability │
          │ retry/backoff  │  │  SQLite log   │
          │ circuit breaker│  │ cost/latency  │
          │ relevance gate │  │  per step     │
          │ fallback path  │  └──────────────┘
          └───────────────┘
\```

Each of the three pipeline steps runs through the same reliability wrapper
(`call_with_protection`): retry with exponential backoff on transient failures,
fail-fast on non-retryable errors (e.g. 401/403), and a circuit breaker that trips
after repeated failures to avoid hammering a dead dependency. Every step's outcome
— success, failure, or fallback — is logged with latency, token usage, and estimated
cost.

## What's implemented

**Pipeline**
- Search (Tavily API) → fetch (HTML extraction) → synthesize (Groq / Llama 3.3 70B)

**Reliability**
- Exponential backoff retry, capped at 3 attempts
- Fail-fast on non-retryable errors (4xx auth/permission/bad-request responses)
- Per-dependency circuit breaker (opens after 3 consecutive failures, 30s cooldown)
- Relevance gate — rejects off-topic/low-content results before spending an LLM call
- Graceful fallback — degrades to a raw-snippet response instead of hard-failing
  when synthesis is unavailable

**Observability**
- Every run and step logged to SQLite (`logs/runs.db`): status, latency, tokens,
  estimated cost, error detail
- `report_cli.py` — CLI summary: success rate, per-step latency/failure breakdown,
  total cost, recent runs table

**Testing**
- ~19 tests (pytest) covering reliability logic, mocked search/fetch failure paths,
  and orchestrator integration scenarios (happy path, early failure, relevance
  rejection)

**Deployment**
- Dockerized, runtime secrets via `--env-file`, logs persisted via volume mount

## How to run

\```bash
# Setup
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add your GROQ_API_KEY and TAVILY_API_KEY

# Run the pipeline
python -m src.orchestrator

# Run the test suite
python -m pytest tests/ -v

# View the observability report
python report_cli.py

# Docker
docker build -t agent-ops .
docker run --rm --env-file .env -v "$(pwd)/logs:/app/logs" agent-ops
\```

## Design decisions worth noting

- **Reliability logic is centralized, not scattered.** `search.py`/`fetch.py` stay
  simple and single-purpose; retry/circuit-breaker/fallback logic lives in
  `reliability.py` and wraps calls at the orchestrator level. Easier to reason about
  and test in isolation.
- **Non-retryable vs retryable errors are distinguished.** A 401 will never succeed
  on retry — retrying it anyway just wastes time and delays the circuit breaker.
  Only transient errors (timeouts, 5xx, rate limits) get the backoff treatment.
- **The relevance gate exists because of a real bug found during testing**: an
  off-topic query didn't fail — it produced a confident, well-written summary about
  something entirely unrelated. Retries and circuit breakers don't catch this
  (nothing "failed"); a lightweight keyword-overlap check does.
- **Fallback degrades gracefully rather than failing hard.** If synthesis is
  unavailable, the user gets a raw snippet instead of nothing — a deliberate choice
  about what "reliable" should mean for an end user.

## Known limitations / next steps

- Cost tracking uses a blended per-token rate rather than exact input/output split
- No caching layer — identical queries re-run the full pipeline
- SQLite schema has no migration tooling (acceptable for local dev logging,
  would need proper migrations for production use)
- Circuit breaker thresholds are hardcoded; would be config-driven in production

