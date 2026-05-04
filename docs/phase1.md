# Phase 1 — Project Skeleton & GA4 MCP Verification

## Goal
Establish the project foundation and verify that both external dependencies work
before any agent logic is written. This phase is about infrastructure confidence,
not features.

---

## Context & Key Decisions

**What we're building:** An AI agent that answers natural language questions about
Google Analytics (GA4) data, with the ability to write and execute Python code for
advanced analysis. Stack: raw Anthropic SDK, FastAPI, Docker sandbox for code execution.

**GA4 access:** Via the official Google GA4 MCP server running locally over stdio.
Credentials (Google service account JSON) never leave the machine — the MCP server
process handles all GA4 API calls directly.

**Demo property:** Use Google's public demo property (`213025502`) for all
development and testing. No GA4 property ownership required.

**Python version:** 3.14

---

## What to Build in This Phase

### 1. Project Structure
Standard Python project layout with `pyproject.toml`. Separate modules for `agent/`,
`sandbox/`, `api/`, `tests/`, and a `scripts/` folder for throwaway verification scripts.
Include `.env.example` with three variables: `ANTHROPIC_API_KEY`,
`GOOGLE_APPLICATION_CREDENTIALS` (path to service account JSON),
and `GA4_PROPERTY_ID`.

### 2. Settings
Single `config.py` using pydantic-settings. Loads from `.env`. All other modules
import settings from here — no `os.environ` scattered around.

### 3. Docker Sandbox Image
A `Dockerfile.sandbox` based on `python:3.14-slim` with data science libraries
pre-installed (pandas, matplotlib, numpy, scipy — pin exact versions).
Runs as a non-root user. User builds this once locally; the image is never
committed to the repo.

### 4. Sandbox Runner
A function in `sandbox/runner.py` that accepts a Python code string, runs it in a
Docker container from the sandbox image, and returns stdout/stderr/exit code.
Security constraints: no network access, memory cap, CPU cap, read-only code mount,
hard timeout. Returns a structured result dict — never raises on execution failure,
always returns the error as data so the agent can reason about it.

### 5. FastAPI Skeleton
Minimal `api/main.py` with a single `/health` endpoint. No agent logic yet.
Just confirms the app starts.

### 6. Verification Scripts
Two throwaway scripts in `scripts/` — not part of the agent, just smoke tests:
- `verify_sandbox.py` — runs a few code snippets through the sandbox, asserts
  correct output, asserts network is blocked, asserts pandas works
- `verify_ga4.py` — connects to the GA4 MCP server via the Anthropic SDK beta
  interface, sends a simple hardcoded question about the demo property, prints
  the response. Confirms credentials work and MCP connectivity is functional.

---

## Dependencies to Include
- `anthropic` (with MCP beta support)
- `fastapi`, `uvicorn`
- `pydantic`, `pydantic-settings`
- `python-dotenv`
- `google-analytics-data` (for any direct GA4 client use later)
- dev: `pytest`, `pytest-asyncio`, `pytest-mock`

---

## Phase Complete When
- `verify_sandbox.py` passes (basic exec, pandas, network isolation)
- `verify_ga4.py` returns real data from the demo property
- `/health` endpoint responds
- `.env` and service account JSON are gitignored and not committed
