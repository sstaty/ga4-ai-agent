# Phase 3 — FastAPI Endpoint & PDF Export

## Goal
Wire the agent into a production-ready REST API with structured JSON responses
and PDF export capability. By the end of this phase the project is fully usable
via HTTP and the bonus requirement (PDF export) is complete.

---

## Context & Key Decisions

**Two endpoints:** `POST /query` always returns `AgentResponse` JSON.
`POST /query/pdf` always returns PDF binary with `Content-Type: application/pdf`.
Each endpoint has a single predictable response type. Both share the same
underlying agent call internally.

**PDF content:** The PDF should contain the natural language answer, a data table
and a chart if the question is visual in nature (time series, breakdowns,
comparisons). Chart is generated via matplotlib as an image embedded in the PDF.
Use weasyprint to convert an HTML template to PDF. If weasyprint fails on Windows
due to GTK dependencies, fall back to reportlab.

**Charts only in PDF:** No chart spec in the JSON response. Charts are a PDF
concern only, keeping the JSON response clean.

**Multiple GA4 queries supported:** The agent may call `run_report` multiple times
in one run (e.g. comparing two date ranges, or fetching different dimensions).
The PDF generator handles this by filtering `tool_calls` for all `run_report`
entries and rendering each dataset as a separate table/chart.

**Stateless:** Each request is a fully independent agent run. No conversation
history, no session state.

**Timeout:** Wrap the agent run in `asyncio.wait_for`. Default 120 seconds,
overridable per request. Return HTTP 504 if exceeded.

**Model via settings:** `ANTHROPIC_MODEL` read from `.env` via settings object.

**Full trace in LangFuse, not in API response.** The API response exposes tool
calls for auditability but not Claude's internal reasoning — that lives in
LangFuse.

---

## What to Build

### 1. Response Models
Define in `agent/models.py`:

```python
class ToolCall(BaseModel):
    name: str
    input: dict
    output: str | None

class AgentResponse(BaseModel):
    answer: str
    tool_calls: list[ToolCall]
    error: str | None
```

No `data` field — GA4 results are accessible via `tool_calls` filtered by
`run_report` entries. No duplication.

### 2. Request Model
Define in `api/main.py` or `api/models.py`:

```python
class QueryRequest(BaseModel):
    question: str
    timeout: int = 120
```

### 3. PDF Generation
A utility in `agent/pdf.py` that accepts an `AgentResponse` and converts it
to PDF bytes. Internally:
- Filters `tool_calls` for `run_report` entries to extract GA4 datasets
- For each dataset generates a matplotlib chart using this type selection:
  - Date/time dimension present → line chart
  - Categorical dimension, <=10 categories → bar chart
  - Exactly 2 columns, <=6 rows → pie chart
  - Default → bar chart
- Renders an HTML template via Jinja2 with answer, data tables, and charts
  embedded as base64 images
- Converts HTML to PDF via weasyprint

Template (`templates/report.html`) includes:
- Title: "GA4 Analytics Report"
- Generation timestamp
- Answer text
- For each GA4 dataset: data table + chart image (base64 embedded)
- Clean minimal styling

Returns `bytes`.

### 4. FastAPI App
Update `api/main.py`:
- `GET /health` — already exists
- `POST /query` — accepts `QueryRequest`, runs agent, returns `AgentResponse` JSON
- `POST /query/pdf` — accepts `QueryRequest`, runs agent, returns PDF binary
- Both endpoints share the same internal agent call
- `asyncio.wait_for` using `request.timeout` on both
- HTTP 504 on timeout, HTTP 500 on unexpected errors
- CORS middleware enabled

### 5. Runner Update
Update `agent/runner.py` to populate `list[ToolCall]` with full inputs and
outputs for every tool call — both GA4 MCP calls and `execute_python`.

Also apply the async fix: wrap `run_code` subprocess call in
`asyncio.get_event_loop().run_in_executor(None, ...)`.

---

## Dependencies to Add
- `weasyprint` — HTML to PDF
- `matplotlib` — chart generation
- `jinja2` — HTML template rendering

---

## Implementation Deviations

### `ToolCall.output` is `Any`, not `str | None`
The plan specified `output: str | None`. During testing, MCP tool outputs were valid JSON strings being double-serialised into the API response. The type was changed to `Any` and the loop now tries `json.loads(content)` before storing — if it parses, the dict/list is stored directly; otherwise the raw string is kept. `execute_python` output stays a string (not valid JSON).

### `AgentResponse` drops `data` and `iterations`
Both fields existed in the pre-Phase-3 model. Removed as planned — `data` is redundant since GA4 results are accessible via `tool_calls`, and `iterations` is internal detail that belongs in LangFuse traces, not the API response.

### `json` import re-added to `loop.py`
Removed in the initial refactor, then re-added to support the `json.loads(content)` call for `ToolCall.output` parsing.

### PDF uses reportlab fallback on Windows (weasyprint GTK unavailable)
WeasyPrint requires GTK native libraries which are not available on Windows without manual setup. The reportlab fallback path is the active path in development. Both paths produce valid PDFs — weasyprint will work in Linux/Docker deployments without changes.

### GA4 RunReport response requires custom flattening in PDF generator
The plan assumed `run_report` output would be a flat `list[dict]`. The actual MCP response is a nested RunReport object: `{dimension_headers, metric_headers, rows: [{dimension_values, metric_values}]}`. `_parse_rows()` in `agent/pdf.py` detects and flattens this format into `[{dim: val, metric: val}]`.

### Additional PDF improvements added post-plan
- **Markdown table stripping**: Claude's answer often includes a markdown table summary. For PDF, `strip_markdown_tables()` removes these from the answer text to avoid duplication with the proper HTML table rendered below.
- **Date formatting**: GA4 date dimension returns `YYYYMMDD` strings. `_format_rows()` detects date-like columns and reformats to `YYYY-MM-DD` for both table display and chart x-axis labels.
- **Meaningful dataset titles**: Instead of "Data Table 1", titles are derived from column names via `_dataset_title()` — e.g. `"Sessions by Date"`, `"Screen Page Views by Page Path"`.
- **Page-break CSS**: Added `page-break-inside: avoid; break-inside: avoid` to table and chart elements to prevent mid-element page splits.
- **`markdown` dependency added**: Used to convert Claude's markdown answer to HTML for proper bold/italic rendering in the PDF.

---

## Phase Complete When
- `POST /query` returns valid `AgentResponse` JSON with full `tool_calls`
- `tool_calls` includes inputs and outputs for all GA4 and Python tool calls
- PDF export contains answer, data table(s), and chart(s)
- Multiple GA4 queries in one run produce multiple tables/charts in PDF
- Timeout returns HTTP 504, default 120s, overridable via request
- `run_code` is async-safe
- Test with:

```bash
# JSON
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What were the top 5 pages by views last 30 days?"}'

# PDF
curl -X POST http://localhost:8000/query/pdf \
  -H "Content-Type: application/json" \
  -d '{"question": "Show me daily sessions for the last 14 days"}' \
  --output report.pdf
```
