# GA4 AI Agent

An AI agent that answers natural language questions about Google Analytics 4 data and can write/execute Python code for advanced analysis.

**Stack:** Anthropic SDK · FastAPI · Docker (sandboxed code execution) · GA4 MCP server (local stdio)

---

## Prerequisites

- Python 3.14+ via [uv](https://docs.astral.sh/uv/)
- Docker Desktop (for the sandbox)
- An Anthropic API key
- A Google account with access to at least one GA4 property

---

## Setup

### 1. Install dependencies

```bash
uv sync
```

### 2. Configure environment

```bash
cp .env.example .env
```

Fill in `.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_APPLICATION_CREDENTIALS=/path/to/oauth_token.json
GA4_PROPERTY_ID=123456789
```

### 3. Authenticate with Google

`GOOGLE_APPLICATION_CREDENTIALS` accepts either a **service account key** or an **OAuth2 user token** (recommended for personal accounts).

#### Option A — OAuth2 (recommended)

1. In [Google Cloud Console](https://console.cloud.google.com), go to **APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID**. Choose **Desktop app** and download the JSON as `credentials.json` in the project root.

2. Enable the **Google Analytics Data API** in your GCP project (APIs & Services → Enable APIs).

3. Add your Google account as a test user: **APIs & Services → OAuth consent screen → Test users**.

4. Run the auth script:
   ```bash
   uv run python scripts/setup_oauth.py
   ```
   A browser window opens for consent on the first run. Subsequent runs silently refresh the token.

5. Copy the printed path into `GOOGLE_APPLICATION_CREDENTIALS` in `.env`.

#### Option B — Service account

Set `GOOGLE_APPLICATION_CREDENTIALS` to the path of your service account key JSON. The service account must have Viewer access to the GA4 property.

### 4. Build the Docker sandbox image

Required once before running the agent or sandbox tests:

```bash
docker build -f Dockerfile.sandbox -t ga4-sandbox .
```

### 5. Verify everything works

```bash
# Check GA4 connectivity
uv run python scripts/verify_ga4.py

# Check the Docker sandbox
uv run python scripts/verify_sandbox.py
```

---

## Running the API server

```bash
uv run uvicorn api.main:app --reload
```

---

## Architecture

```
HTTP request → api/main.py (FastAPI)
                    ↓
               agent/ (Anthropic SDK + tools)
               ├── GA4 MCP server (stdio, local)   ← reads GA4 data
               └── sandbox/runner.py (Docker)       ← executes generated Python
```

**Sandbox security constraints per container:** `--network=none`, 256 MB RAM, 0.5 CPU, 10s hard timeout, code mounted read-only.

GA4 credentials never leave the machine — the MCP server runs as a local subprocess.
