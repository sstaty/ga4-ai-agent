# Architecture

## Overview

```
User question
    ↓
FastAPI  POST /query     → AgentResponse JSON
         POST /query/pdf → PDF binary
    ↓
ReAct Agent Loop  (raw Anthropic SDK, max 10 iterations)
    ├── GA4 MCP Server  (uvx analytics-mcp, stdio subprocess)
    │       └── Google Analytics Data API (read-only)
    └── execute_python  (Docker sandbox)
            └── ga4-sandbox image: pandas, matplotlib, numpy, scipy
    ↓
AgentResponse
    ├── answer: str          markdown prose from Claude
    └── tool_calls: list     name + full input + parsed output per call
    ↓  (PDF path only)
agent/pdf.py
    ├── _parse_rows()        GA4 RunReport → flat list[dict]
    ├── _format_rows()       YYYYMMDD → YYYY-MM-DD
    ├── _chart_b64()         matplotlib → base64 PNG
    ├── Jinja2 render        templates/report.html
    └── weasyprint / reportlab → PDF bytes
```

---

## Key Design Decisions

**Raw Anthropic SDK over LangGraph**
The ReAct loop is a simple linear cycle: call Claude → inspect `stop_reason` → dispatch tool → append result → repeat. There is no branching state, parallel tool execution, or multi-agent coordination. The raw SDK makes every step explicit and easy to debug. LangGraph would add a graph abstraction without adding capability at this scope.

**MCP over a custom GA4 tool**
`analytics-mcp` is the official Google MCP server for the Analytics Data API. It handles authentication, request serialisation, pagination, and schema — all work a custom tool would have to duplicate and maintain. Running it as a stdio subprocess keeps the agent codebase small and ensures we stay in sync with the official client.

**Docker for code execution**
Claude can generate arbitrary Python. Running it in a subprocess with `exec()` gives no isolation guarantees. Each `execute_python` call spawns a fresh Docker container with: no network access (`--network=none`), 256 MB RAM cap, 0.5 CPU quota, 10-second hard timeout, and the script mounted read-only. The container is removed immediately after the run. This makes code execution safe by default with no policy enforcement required in the agent logic.

**Stateless design**
Each HTTP request is a fully independent agent run. There is no conversation history and no session state between requests. This makes the system simple to reason about, trivial to scale horizontally, and predictable under load. Multi-turn would require session storage and history truncation logic that adds complexity without benefit for an analytics query tool.

**LangFuse for observability**
Agent behaviour is hard to debug from logs alone. LangFuse captures the full trace of every run: each iteration as a span, each Claude call as a generation (with token counts), and each tool invocation with its input and output. This is optional — if no keys are configured, tracing is silently skipped. The API response is kept clean: `tool_calls` exposes inputs and outputs for auditability but Claude's internal reasoning stays in LangFuse only.

---

## Security Model

**GA4 data access**
- Read-only via the official Google Analytics Data API.
- Credentials are loaded from a local file path set in `GOOGLE_APPLICATION_CREDENTIALS`. They are never passed to Claude and never appear in LLM context.
- The MCP server runs as a local stdio subprocess. No credentials leave the machine.

**Python code execution**
- Every `execute_python` call runs in a fresh Docker container.
- Constraints per container: `--network=none`, 256 MB RAM, 0.5 CPU, 10-second hard timeout, code script mounted read-only.
- The container is removed after each run regardless of exit code.
- The agent system prompt instructs Claude to embed GA4 data as inline literals in generated code, never to reference file paths or external resources.

---

## Observability

LangFuse tracing activates automatically when `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are present in `.env`. Leave them blank to disable.

Each agent run produces one trace with the following nested structure:

```
trace: run_agent
└── span: iteration-1
    ├── generation: claude      (input messages, output blocks, token usage)
    └── tool: run_report        (input params, GA4 response)
└── span: iteration-2
    ├── generation: claude
    └── tool: execute_python    (code input, stdout/stderr/exit_code)
```

Total latency and status (`success` / `max_iterations` / `error`) are attached to the root trace.

---

## Out of Scope — Deliberate Decisions

**LangGraph / agent framework**
The ReAct loop here is a simple linear cycle with no branching state or multi-agent coordination. Raw SDK is more transparent, easier to debug, and sufficient for this scope. LangGraph would add a graph abstraction without adding capability.

**Multi-turn conversation**
The task specifies a single question → answer pattern. Stateless design is simpler, more predictable, and production-appropriate for an analytics query tool. Multi-turn would require session state management and history storage with truncation logic.

**Frontend / UI**
A REST API is the most production-appropriate choice for an analytics agent. The PDF export serves as the human-readable output format. Swagger UI at `/docs` provides easy local testing. A frontend was considered but would add complexity without demonstrating anything new about the agent architecture.

**Model routing**
Routing simple queries to Haiku and complex ones to Sonnet/Opus would reduce cost and improve quality. Skipped due to scope — the model is configurable via `ANTHROPIC_MODEL` in `.env`, so switching is a one-line change. A production implementation would classify query complexity before dispatching.

**Async job pattern**
A production API for long-running tasks (10–120 s) would use an async job pattern: `POST /query` returns a `job_id` immediately, `GET /jobs/{id}` polls for results. Skipped — blocking HTTP with a configurable timeout is acceptable for a local single-user deployment and keeps the architecture simple. The timeout field on each request provides a safety valve.

**Evals / test suite**
Lightweight pytest evals were considered. Skipped in favour of real LangFuse traces and committed example outputs, which are more convincing evidence of correct behaviour for a hiring task. A production system would have a golden dataset and automated regression testing on agent behaviour.

**Provider abstraction (LiteLLM)**
Abstracting the LLM provider via LiteLLM would allow swapping Claude for other models. Skipped — the task specifies Claude explicitly. Adding LiteLLM would be a one-line change if needed.

**SSE / WebSocket streaming**
Streaming agent reasoning and partial results would improve perceived latency. Skipped — adds significant complexity for a demo where the complete response is the deliverable. The PDF export in particular requires the full response before it can be generated.
