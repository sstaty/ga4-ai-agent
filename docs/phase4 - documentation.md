# Phase 4 — README & Architecture Documentation

## Goal
Make the project submission-ready with clear documentation. A reviewer should
be able to clone the repo and have a working agent in under 15 minutes.

---

## What to Build

### 1. README.md

**Overview** — one paragraph, what this is and what it does

**Prerequisites** — Docker, Python 3.14, uv, uvx

**Setup** — step by step:
1. Clone repo
2. Copy `.env.example` to `.env`, fill in keys
3. Build Docker sandbox image: `docker build -f Dockerfile.sandbox -t ga4-sandbox:latest .`
4. Run the API: `uvicorn api.main:app --reload`

**Usage** — curl examples for both endpoints plus mention Swagger UI at `/docs`

```bash
# JSON response
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What were the top 5 pages by views last 30 days?"}'

# PDF response
curl -X POST http://localhost:8000/query/pdf \
  -H "Content-Type: application/json" \
  -d '{"question": "Show me daily sessions for the last 14 days"}' \
  --output report.pdf
```

**Sample Output** — link to `docs/example_outputs/`

**Future Improvements** — see "Out of Scope" section below

---

### 2. ARCHITECTURE.md

**Overview diagram** — ASCII showing the full system:
```
User question
    ↓
FastAPI (POST /query, POST /query/pdf)
    ↓
ReAct Agent Loop (raw Anthropic SDK)
    ├── GA4 MCP Server (uvx analytics-mcp, stdio, local)
    └── execute_python (Docker sandbox)
    ↓
AgentResponse → JSON or PDF (weasyprint)
```

**Key design decisions** — short prose on each:
- Why raw Anthropic SDK over LangGraph
- Why MCP over a custom GA4 tool
- Why Docker for code execution sandbox
- Stateless design — one question per request

**Security Model** — address the task's open security question explicitly:
- GA4 access is read-only via official Google MCP server over stdio
- Credentials never leave the machine, never enter LLM context
- Python execution in Docker: no network, memory cap, CPU cap, read-only
  code mount, hard timeout

**Observability** — LangFuse tracing on every agent run, capturing tool calls,
inputs, outputs, and iteration count per request

---

### 3. Out of Scope — Deliberate Decisions

Include this section in ARCHITECTURE.md to show architectural awareness.
Each item was explicitly considered and skipped for the reasons noted.

**LangGraph / agent framework**
Considered but skipped — the ReAct loop here is a simple linear cycle with
no branching state or multi-agent coordination. Raw SDK is more transparent,
easier to debug, and sufficient for this scope. LangGraph would add abstraction
without benefit.

**Multi-turn conversation**
The task specifies a single question → answer pattern ("vzorový výstup na
základe otázky"). Stateless design is simpler, more predictable, and
production-appropriate for an analytics query tool. Multi-turn would require
session state management and history storage.

**Frontend / UI**
The task explicitly allows CLI, API, or WebSockets. A REST API is the most
production-appropriate choice. A simple HTML frontend was considered but skipped
— the PDF export serves as the human-readable output, and Swagger UI at `/docs`
provides easy local testing without extra frontend complexity.

**Model routing**
Routing simple queries to Haiku and complex ones to Sonnet/Opus would reduce
cost and improve quality. Skipped due to scope — model is configurable via
`.env` (`ANTHROPIC_MODEL`) so switching is straightforward. A production
implementation would classify query complexity before dispatching.

**Async job pattern**
A proper production API for long-running tasks (10-120s) would use an async
job pattern: `POST /query` returns a `job_id` immediately, `GET /jobs/{id}`
polls for results. Skipped for this task — blocking HTTP is acceptable for a
single-user local demo and keeps the architecture simple.

**Evals / test suite**
Lightweight pytest evals were considered. Skipped in favour of real LangFuse
traces and example outputs which are more convincing evidence of correct
behaviour for a hiring task. A production system would have a golden dataset
and automated regression testing on agent behaviour.

**Provider abstraction (LiteLLM)**
Abstracting the LLM provider via LiteLLM would allow swapping Claude for other
models. Skipped — the task specifies Claude explicitly. Adding LiteLLM would be
a one-line change if needed.

**SSE / WebSocket streaming**
Streaming agent reasoning and partial results to the client would improve
perceived latency. The task lists WebSockets as an option. Skipped — adds
significant complexity for a demo where the full response is the deliverable.

---

## Final Checklist
- [ ] Fresh clone + README setup works end to end
- [ ] `.env` and service account JSON are gitignored
- [ ] `docs/example_outputs/` committed with sample JSON and PDF
- [ ] `uv.lock` committed
- [ ] No debug prints or hardcoded values left in
- [ ] LangFuse keys in `.env.example` with placeholder values
