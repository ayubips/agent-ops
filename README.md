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