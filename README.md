# Agent Ops

A lightweight orchestration and observability layer for multi-step LLM agents.

Currently implements a research agent: search → fetch → synthesize, with structured
state tracking. Reliability (retries, circuit breaker, fallback, relevance checks)
and observability (structured logging, cost/latency tracking) are being layered in next.

## Status: Day 2 of 15 — happy path working end-to-end.
Known issue found in testing: garbage/off-topic queries can produce a confidently
wrong summary rather than a clear failure. This is the first item being addressed
in the reliability layer.