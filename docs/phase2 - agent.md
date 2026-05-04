# Phase 2 — Core Agent Loop

## Goal
Implement the ReAct agent loop that powers the entire system. By the end of this
phase the agent can answer a natural language GA4 question end-to-end, using the
MCP server for data and the Docker sandbox for code execution when needed.

---

## Context & Key Decisions

**ReAct loop:** Implemented manually using the raw Anthropic SDK — no LangGraph or
other framework. The loop runs: think → tool call → observe result → think → ... →
final answer. This continues until Claude returns `stop_reason == "end_turn"`.

**Two tools available to the agent:**
- GA4 data access — via the official Google Analytics MCP server (already verified
  in Phase 1). The SDK handles MCP tool execution automatically.
- Python code execution — a native tool backed by the Docker sandbox from Phase 1.
  This one requires manual dispatch in the loop.

**Data flow for code execution:** When the agent wants to run Python, it has already
seen the GA4 data in its context window (as a tool result). It embeds that data
directly as literals in the Python code it generates. No file passing or shared
memory needed.

**Model:** `claude-sonnet-4-5`

---

## What to Build in This Phase

### 1. System Prompt
Define the agent's identity and behavior in `agent/prompts.py`. It should instruct
Claude to:
- Answer questions about GA4 analytics data for a specific property
- Use the GA4 MCP tools to fetch data
- Use the Python execution tool for advanced analysis, calculations, or
  visualizations that go beyond what GA4 returns directly
- Always return a clear, human-readable answer

Keep it concise — no need to enumerate every GA4 metric.

### 2. Native Tool Definition: `execute_python`
Define the tool schema in `agent/tools.py` — name, description, and input schema
(a single `code` string field). This is what Claude sees when deciding whether to
write and run Python. Description should make clear this runs in an isolated sandbox
with pandas, matplotlib, numpy, scipy available.

### 3. Agent Loop: `agent/runner.py`
The core of the project. Implement a function `run_agent(question: str) -> AgentResponse`
that:
- Initializes the message history with the system prompt and user question
- Calls the Anthropic SDK with both MCP servers and native tools configured
- If `stop_reason == "tool_use"`, dispatches native tool calls (execute_python)
  and appends results back to message history, then loops
- MCP tool calls are handled automatically by the SDK — no dispatch needed for those
- If `stop_reason == "end_turn"`, extracts the final text response and returns
- Includes a max iterations guard (e.g. 10) to prevent infinite loops
- Logs each iteration: what tool was called, with what inputs — useful for debugging

### 4. Response Model
Define `AgentResponse` in `agent/models.py`:
- `answer: str` — the natural language response
- `data: list[dict] | None` — raw tabular data if GA4 returned rows
- `tool_calls: list[str]` — which tools were invoked, for transparency
- `iterations: int` — how many loop iterations it took

Keep it simple for now — chart spec and PDF come in Phase 3/4.

### 5. Verification Script
`scripts/verify_agent.py` — runs 3-4 hardcoded questions against the real GA4
property and prints the full AgentResponse for each. Not automated assertions,
just manual inspection to confirm the loop works correctly end-to-end.

Example questions to test:
- "How many sessions did we have in the last 7 days?"
- "Which pages get the most traffic? Show me the top 5."
- "What percentage of our traffic comes from mobile devices? Calculate it."
  (this should trigger both GA4 tool use AND Python execution)

---

## Phase Complete When
- Agent answers a simple GA4 question using only the MCP tool
- Agent answers a question that requires Python execution (GA4 data → code → result)
- Max iterations guard works — loop terminates cleanly
- Tool calls are logged visibly during execution
- `AgentResponse` is populated correctly for both tool paths
