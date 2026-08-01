# Atlys Agentic Analytics System

A production-grade, multi-agent data analytics pipeline built for Atlys. The system eliminates manual data engineering by processing product feature specifications (`spec.md`) and raw event samples (`events.ndjson`) to automatically generate ClickHouse schemas, maintain a living context layer in `chDB`, and produce actionable product insights.

The system is designed with strict architectural constraints:
- **No Hidden LLM Memory**: All agents operate with `memory=False`. Context is fetched Just-In-Time (JIT) via explicit SQL queries against embedded `chDB`.
- **Decoupled Pipelines**: CUJ 1 (Ingestion Pipeline via CLI with Human-in-the-Loop gate) and CUJ 2 (Analyst Interface via FastAPI/LibreChat) are strictly separated.
- **Read-Only Analytics**: Analytical queries against ClickHouse Cloud are strictly `SELECT`-only; LLMs only receive aggregated JSON summaries.
- **Full Observability**: Every agent step, tool execution, and SQL statement is traced to Langfuse.

---

## 1. Setup & Installation

### Prerequisites
- Python 3.11+
- (Optional) Docker for running LibreChat UI

### Install Dependencies
```bash
# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

### Install Dependencies
```bash
# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install package in editable mode
pip install -e .
# Or install dependencies directly
pip install -r src/atlys_agentic/requirements.txt
```

### Configure Credentials
Copy the example environment file and fill in your ClickHouse, Gemini, and Langfuse credentials:
```bash
cp src/atlys_agentic/config/.env.example src/atlys_agentic/config/.env
```

Key environment variables in `src/atlys_agentic/config/.env`:
- `CLICKHOUSE_HOST`, `CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD`, `CLICKHOUSE_PORT`, `CLICKHOUSE_SECURE`
- `CLICKHOUSE_DATABASE` (e.g. `clickathon`)
- `LLM_MODEL` (e.g. `gemini/gemini-2.5-flash` or `gemini/gemini-flash-latest`)
- `GEMINI_API_KEY`
- `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`
- `CHDB_PATH` (defaults to `./chdb_data`)
- `CREWAI_TRACING_ENABLED=false`
- `CREWAI_DISABLE_TELEMETRY=true`

---

## 2. Running Automated Tests

The repository includes a comprehensive test suite covering paths, deterministic tools, memory-free agents, dynamic flows, CLI entry points, and end-to-end rehearsals.

### Run All Tests
```bash
pytest -v
```

### Run Tests by Component
```bash
# 1. Deterministic Agent Tools (schema inference, MVs, DDL execute, context diff/upsert, confidence)
pytest src/atlys_agentic/tests/test_tools.py -v

# 2. Agent Personas & Memory-Free Configuration
pytest src/atlys_agentic/tests/test_agents.py -v

# 3. CUJ 1 Ingestion Flow & CLI (HITL gate approve/reject paths)
pytest src/atlys_agentic/tests/test_ingestion_flow.py src/atlys_agentic/tests/test_run_ingestion.py -v

# 4. CUJ 2 Analyst Flow & FastAPI Chat Backend
pytest src/atlys_agentic/tests/test_analysis_flow.py src/atlys_agentic/tests/test_chat_backend.py -v

# 5. Full End-to-End Pipeline Rehearsal (Ingestion -> HITL -> chDB -> Multi-Cut Analysis -> Viz)
pytest src/atlys_agentic/tests/test_e2e_rehearsal.py -v
```

---

## 3. Actual Pipeline Execution

### CUJ 1: Ingestion Pipeline (DevOps / CLI)

To ingest a new feature specification and event stream into ClickHouse Cloud:

```bash
python -m atlys_agentic.run_ingestion --spec_dir "problem statment/specs/01_express_checkout" --table express_checkout
```

#### What Happens During Execution:
1. **Context Initialization**: `chdb_client` parses `base_context.md` into chunked, versioned rows in `business_context`.
2. **Schema Inference (`Instrumentation Engineer`)**:
   - Analyzes `events.ndjson` and `spec.md`.
   - Generates production ClickHouse DDL with `(timestamp, user_id)` ORDER BY key, `toYYYYMM(timestamp)` partitioning, 12-month TTL, and `LowCardinality(String)` types.
   - Generates daily segment rollup Materialized View (`SummingMergeTree`) if segment columns exist.
3. **Human-in-the-Loop (HITL) Gate**:
   - Prints the proposed DDL and Materialized View to the console.
   - Prompts the operator: `Type APPROVE to execute on ClickHouse Cloud: `.
   - If the operator types `APPROVE`, execution proceeds. Any other input aborts cleanly without modifying ClickHouse Cloud.
4. **Cloud Execution & Schema Registry**:
   - Executes DDL on ClickHouse Cloud.
   - Records versioned schema snapshot in `chDB.schema_registry`.
5. **Context Audit (`Context Librarian`)**:
   - Diffs table columns against `business_context`.
   - Flags contradictions (e.g. conversion-rate denominator conflicts) and undocumented columns.
   - Upserts newly discovered columns into `business_context` and logs changes in `context_changelog`.

---

### CUJ 2: Analyst Interface (FastAPI / LibreChat)

The Analyst interface runs as an OpenAI-compatible HTTP service that can be queried via curl, Python, or connected directly to LibreChat.

#### 1. Start the Chat Backend
```bash
uvicorn atlys_agentic.run_chat:app --host 0.0.0.0 --port 8008 --reload
```

#### 2. Test via curl
```bash
curl -X POST http://localhost:8008/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "atlys-analyst",
    "messages": [
      {"role": "user", "content": "Is there an iOS OTP drop on Express Checkout?"}
    ]
  }'
```

#### What Happens During Analysis:
1. **JIT Context Retrieval**: Queries `chDB.business_context` for known issues (`K1`–`K7`) and domain definitions.
2. **Multi-Cut Analysis**: Pushes aggregation queries to ClickHouse across mandatory dimensions (`device_type`, `geoip_country_code`, `destination`).
3. **Known-Issue Routing**: Matches question keywords to known anomalies (e.g. `K1: iOS WebKit OTP autofill regression`).
4. **Confidence Scoring**: Computes deterministic confidence score $f(N, \Delta, \text{match}, \text{cuts}) \in [0, 1]$.
5. **Synthesis**: Produces a structured PM markdown report, logs the insight into `chDB.insights`, and returns the OpenAI-formatted payload with Langfuse trace ID.

#### 3. Run Programmatically via Python
```python
from atlys_agentic.flows import analysis_flow

# Runs JIT context retrieval from chDB, executes multi-cut ClickHouse queries, and scores confidence
result = analysis_flow.run(
    question="Is there an iOS OTP drop on Express Checkout?",
    spec_id="01_express_checkout",
    base_sql="SELECT * FROM otp_entered"
)

print(result["answer_md"])
print("Confidence:", result["confidence"]["score"])
print("Known issue matched:", result["known_issue_match"])
print("Multi-cut dimensions:", list(result["cuts"].keys()))
```

#### 4. Connect to LibreChat (UI)
Start the pre-configured LibreChat container:
```bash
docker compose -f atlys_agentic/librechat/docker-compose.librechat.yml up -d
```
Open `http://localhost:3080` in your browser and select the **Atlys Analyst** model endpoint.

---

### CrewAI LLM Smoke Test

To verify direct end-to-end integration between CrewAI, Gemini LLM (via LiteLLM), and Langfuse tracing:

```bash
python -m atlys_agentic.crew --spec_id 01_express_checkout --table express_checkout
```
Prints the synthesized reasoning and outputs the active Langfuse trace URL.


