# Agent Ops

A lightweight orchestration and observability layer for multi-step LLM agents.

Currently implements a research agent: search → fetch → synthesize, with structured
state tracking. Reliability (retries, circuit breaker, fallback, relevance checks)
and observability (structured logging, cost/latency tracking) are being layered in next.

## Status: Day 2 of 15 — happy path working end-to-end.
Known issue found in testing: garbage/off-topic queries can produce a confidently
wrong summary rather than a clear failure. This is the first item being addressed
in the reliability layer.

## Status: Day 5 of 15 — reliability layer (retry, circuit breaker, relevance
gating) complete. The garbage-query bug found in Day 2 testing is now fixed:
off-topic/junk fetched content fails explicitly instead of producing a
confident but unrelated summary.

## Status: Day 6 of 15 — reliability layer complete: retry with backoff,
fail-fast on non-retryable errors, circuit breaker, relevance gating, and
graceful fallback (degraded response instead of hard failure). Covered by
a pytest suite (9 tests).

## What's built (Day 7/15)
- Research agent pipeline: search → fetch → synthesize
- Reliability layer: exponential backoff retry, fail-fast on non-retryable
  errors (4xx), circuit breaker per dependency, relevance gating to catch
  off-topic results, graceful fallback to a degraded response
- 11 passing tests covering the reliability layer

## What's next
- Observability: structured logging of every run (tokens, cost, latency,
  status) to SQLite, with a CLI report tool
- Dockerization
- Architecture diagram

## Status: Day 9 of 15 — observability layer complete: structured logging
(runs + steps tables in SQLite) with per-step latency, token usage, and
estimated cost. Fallback-degraded runs are logged distinctly from full
LLM successes.

## Status: Day 10 of 15 — CLI report tool complete. Run `python report_cli.py`
(optionally `python report_cli.py 20` for more recent runs) to see success
rate, per-step latency/failure breakdown, total cost, and a recent-runs table
pulled from the observability logs.

## Running with Docker
Build: `docker build -t agent-ops .`
Run:   `docker run --rm --env-file .env -v "$(pwd)/logs:/app/logs" agent-ops`
Report: `docker run --rm --env-file .env -v "$(pwd)/logs:/app/logs" agent-ops python report_cli.py`

## Status: Day 11 of 15 — Dockerized. Runs with API keys passed via
--env-file, logs persisted via volume mount so data survives container
restarts.

## Status: Day 12 of 15 — full test suite (~19 tests) covering reliability
layer, search/fetch tools (mocked, no real API calls), and orchestrator
integration paths (happy path, early failure, relevance-gate rejection).