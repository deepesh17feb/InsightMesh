# Atlys Agentic Analytics System

A production-grade, multi-agent data analytics pipeline built for Atlys. The system eliminates manual data engineering by processing product feature specifications (`spec.md`) and raw event samples (`events.ndjson`) to automatically generate ClickHouse schemas, maintain a living context layer in `chDB`, and produce actionable product insights.

The system is designed with strict architectural constraints:
- **No Hidden LLM Memory**: All agents operate with `memory=False`. Context is fetched Just-In-Time (JIT) via explicit SQL queries against embedded `chDB`.
- **Decoupled Pipelines**: CUJ 1 (Ingestion Pipeline via CLI with Human-in-the-Loop gate) and CUJ 2 (Analyst Interface via FastAPI/LibreChat) are strictly separated.
- **Read-Only Analytics**: Analytical queries against ClickHouse Cloud are strictly `SELECT`-only; LLMs only receive aggregated JSON summaries.
- **Full Observability**: Every agent step, tool execution, and SQL statement is traced to Langfuse.

> 📊 **Architecture & Flow Diagrams**: For detailed visual diagrams and step-by-step walkthroughs of both Critical User Journeys, see [docs/cuj_architecture.md](docs/cuj_architecture.md).

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

# Install package in editable mode
pip install -e .
# Or install dependencies directly from root requirements.txt
pip install -r requirements.txt
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
pytest tests/test_tools.py -v

# 2. Agent Personas & Memory-Free Configuration
pytest tests/test_agents.py -v

# 3. CUJ 1 Ingestion Flow & CLI (HITL gate approve/reject paths)
pytest tests/test_ingestion_flow.py tests/test_run_ingestion.py -v

# 4. CUJ 2 Analyst Flow & FastAPI Chat Backend
pytest tests/test_analysis_flow.py tests/test_chat_backend.py -v

# 5. Full End-to-End Pipeline Rehearsal (Ingestion -> HITL -> chDB -> Multi-Cut Analysis -> Viz)
pytest tests/test_e2e_rehearsal.py -v
```

---

## 3. Actual Pipeline Execution

### Core Agent Personas & Custodianship Model

The system enforces a **strict Least-Privilege & Data Custodianship Model**:

| Agent Persona | Direct DB / Metadata Access? | Assigned Tools | Architectural Role |
| :--- | :---: | :--- | :--- |
| **`Context Librarian`** | ✅ **Sole DB & Metadata Custodian** | • `consult_internal_tables`<br>• `context_diff`<br>• `execute_ddl`<br>• `context_upsert` | **Data Governance Gatekeeper & DB Custodian**: Exclusive custodian of `chDB` (`schema_registry` + `business_context`) and ClickHouse Cloud DDL deployment. Briefs the Instrumentation Engineer with existing table schemas and versions, audits proposed DDL against business rules, manages operator proposals, and executes live DDL + registry sync upon operator approval. |
| **`Instrumentation Engineer`** | ❌ **Zero Direct DB Access** | • `infer_schema`<br>• `generate_mv`<br>• `explain_schema_rationale` | **Pure ClickHouse Systems Architect**: Operates as a pure design & reasoning engine without direct database access. Receives context briefings from the Context Librarian, computes optimal ClickHouse DDL (`ORDER BY`, `PARTITION BY`, `LowCardinality`, `TTL`), generates `SummingMergeTree` MVs, and delegates the proposed design back to the Context Librarian for auditing and deployment. |
| **`Product Analyst`** (CUJ 2) | 🔍 **Read-Only Analytics** | • `analytics_compute` (SELECT-only)<br>• `score_confidence` | **Analytics & Diagnostics Scientist**: Obtains domain context and known issues (`K1`–`K7`) through the Context Librarian, executes strictly read-only multi-cut `SELECT` queries against ClickHouse Cloud, evaluates statistical confidence, and delegates finalized insight storage to the Context Librarian. |

---

### CUJ 1: Ingestion Pipeline (Human-in-the-Loop Gated)

CUJ 1 automates schema inference from product feature specs (`spec.md`) and raw event streams (`events.ndjson`), but enforces a **strict Human-in-the-Loop (HITL) gate**: **human review and authorization is required across all surfaces, even in dry-run mode, and no DDL statement ever executes on ClickHouse Cloud without explicit human confirmation.**

#### Multi-Agent Ingestion & Custodianship Architecture
```
Feature Spec (`spec.md`) + Events (`events.ndjson`)
                     │
                     ▼
  [Instrumentation Engineer Agent]
  - Formulates 6-Pillar Architectural Decision & Rationale:
    1. Table Strategy: Registry consultation (CREATE_NEW vs REUSE vs ALTER)
    2. Primary Sorting Key: ORDER BY (timestamp, user_id) [Never leading UUID]
    3. Partitioning: PARTITION BY toYYYYMM(timestamp) [Monthly part control]
    4. Encodings: LowCardinality(String), Nullable(...), UInt8 booleans
    5. Materialized View: SummingMergeTree daily segment rollup
    6. Lifecycle Retention: TTL timestamp + INTERVAL 12 MONTH (GDPR)
                     │
                     ▼
  [Context Librarian Agent]
  - Audits Schema against chDB.business_context (Detects Gaps & Conflicts)
                     │
                     ▼
  ═══════════════════════════════════════════════════════════
  🛑 HUMAN-IN-THE-LOOP (HITL) APPROVAL GATE (Live & Dry Run)
  ═══════════════════════════════════════════════════════════
  Operator inspects Proposed DDL, MVs, 6-Pillar Rationale & Context Diff
            │                                  │
     [Type "APPROVE"]                    [Any other input]
            │                                  │
            ▼                                  ▼
   ✅ APPROVED REVIEW / DEPLOY         ❌ ABORT / REJECTED
   - Live Mode: Executes on Cloud      - Live Mode: Cloud Untouched
   - Dry Run Mode: Validates & Logs    - Dry Run: Aborts Review
   - Trace Recorded to Langfuse        - Trace Logged as Rejected
```

---

#### 1. Instrumentation Engineer 6-Pillar Decision Rationale

Before any operator approval is requested, the **Instrumentation Engineer** synthesizes a rigorous architectural decision breakdown covering six foundational database pillars:

| Pillar | Architecture Decision | Engineering Rationale & Tradeoff |
| :--- | :--- | :--- |
| **1. Table Strategy** | `CREATE_NEW`, `REUSE_EXISTING`, or `ALTER_EXISTING` | Consults `chDB.schema_registry` and ClickHouse Cloud. If schema exists, reuses or proposes non-breaking `ALTER TABLE ADD COLUMN`. If distinct domain, creates a dedicated table to isolate partition directories, TTL lifecycles, and ingestion locks. |
| **2. Primary Key (`ORDER BY`)** | `(timestamp, user_id)` | Enforces dense primary index locality (1 mark / 8192 rows) for fast range pruning and funnel cohort analysis. **Strict Guardrail**: High-cardinality IDs (`id`, `event_id`, UUIDs) are **never** placed in leading position, avoiding sparse index bloat. |
| **3. Partitioning (`PARTITION BY`)** | `toYYYYMM(timestamp)` | Organizes data into monthly parts. Prevents part churn ("Too many parts" error) while allowing ClickHouse to skip entire monthly parts during analytical cuts and drop cold months cleanly. |
| **4. Encodings & Types** | `LowCardinality`, `Nullable`, `UInt8` | Applies `LowCardinality(String)` to bounded categorical strings (`device_type`, `os`, `country`, `payment_method`) for 5–10× dictionary compression and SIMD cache execution. Wraps sparse keys in `Nullable(...)` and booleans in `UInt8` (1 byte). |
| **5. Rollup MV** | `SummingMergeTree` (`{table}_daily_mv`) | Automatically pre-aggregates event volume and unique users along segment dimensions at write time, eliminating full-table raw scans for Product Analysts during common cuts. |
| **6. Retention (TTL)** | `TTL timestamp + INTERVAL 12 MONTH` | Enforces automated data lifecycle purging in background merges for GDPR compliance and cold storage cost optimization. |

---

#### 2. Command-Line Interface (CLI with HITL Gate)

##### Live Interactive Mode (HITL Deployment Gate)
The CLI prints the full 6-pillar decision breakdown, DDL, MV, and Context Diff Audit, then prompts the operator:
```bash
python -m atlys_agentic.run_ingestion --spec_dir "problem statment/specs/01_express_checkout" --table express_checkout
```
Terminal prompt:
```text
================================================================================
🧠 INSTRUMENTATION ENGINEER ARCHITECTURAL DECISION & RATIONALE
================================================================================
• Target Table: express_checkout
• Executive Summary: Proposes dedicated table express_checkout ordered by (timestamp, user_id)...
--- 1. Table Strategy Decision ---
  Strategy: CREATE_NEW
  Recommendation: Consulted internal schema registry. Dedicated table created.
--- 2. Primary Sorting Key (ORDER BY) ---
  ORDER BY (timestamp, user_id): Orders records chronologically with high temporal locality...
--- 3. Partitioning Strategy (PARTITION BY) ---
  PARTITION BY toYYYYMM(timestamp): Organizes data into monthly directory partitions...
--- 4. Encodings & Data Types ---
  Applied LowCardinality(String) to 4 bounded categorical columns...
--- 5. Materialized View Rollup ---
  Materialized View (express_checkout_daily_mv): Uses SummingMergeTree...
--- 6. Data Lifecycle Retention (TTL) ---
  TTL timestamp + INTERVAL 12 MONTH: Automatically purges data older than 12 months...

--- Proposed ClickHouse DDL ---
CREATE TABLE IF NOT EXISTS express_checkout (...) ENGINE = MergeTree() ...

--- Proposed Materialized View (SummingMergeTree) ---
CREATE MATERIALIZED VIEW IF NOT EXISTS express_checkout_daily_mv ...

--- Context Diff Audit (Context Librarian) ---
  • New Attributes to Sync (4): express_checkout.device_type, ...
================================================================================

[LIVE DEPLOYMENT MODE]
Type APPROVE to execute on ClickHouse Cloud: 
```
- **Approved (`APPROVE`)**: Applies DDL to ClickHouse Cloud, records schema snapshot in `chDB.schema_registry`, and synchronizes new columns with `chDB.business_context`.
- **Rejected (Any other input)**: Aborts immediately (`human_gate_rejected` trace). Cloud and chDB remain untouched.

##### Dry-Run Mode (HITL Proposal Review Gate)
In Dry-Run mode, the CLI prints the full 6-pillar architectural decision breakdown and **prompts the human operator to confirm review of the proposal**:
```bash
python -m atlys_agentic.run_ingestion --spec_dir "problem statment/specs/01_express_checkout" --table express_checkout --dry-run
```
Terminal prompt:
```text
[DRY RUN MODE — Non-Mutating Proposal Review]
Type APPROVE to confirm proposal review (or press Enter/reject to abort): 
```
- **Approved (`APPROVE`)**: Confirms and logs operator review in Langfuse (`human_gate_dry_run` trace). ClickHouse Cloud and `chDB` remain untouched.
- **Rejected**: Logs operator rejection.

---

#### 3. Visual Web Portals (HITL Web Interfaces)

##### Option A: Built-in FastAPI Web Dashboard
Start the platform backend and open **`http://localhost:8008/ui/ingestion`** (or `http://localhost:8008/`):
```bash
uvicorn atlys_agentic.run_chat:app --host 0.0.0.0 --port 8008 --reload
```
1. **Feature Spec Selector**: Choose any spec (`01_express_checkout`, `02_group_family`, etc.) with automatic table name inference.
2. **Phase 1 — Run Dry Run (Generate Proposal & Reasoning)**: Inspect proposed ClickHouse DDL, SummingMergeTree MV, Context Diff Audit, and the expandable **6-Pillar Technical Deep Dive** card.
3. **Phase 2 — HITL Review & Approval Gates**:
   - **`✅ Acknowledge & Approve Dry-Run (HITL Review)`**: Confirms and logs human operator review of the dry-run proposal.
   - **`🚀 Approve & Deploy to ClickHouse Cloud`**: Deploys the approved schema to ClickHouse Cloud with confirmation gate.

##### Option B: Streamlit Ingestion Portal
Launch the Streamlit portal:
```bash
streamlit run src/atlys_agentic/ui_ingestion.py
# or via entrypoint:
atlys-ui
```
- **Dry-Run Review Gate**: Checkbox `[x] I have reviewed and approve this dry-run schema proposal and architectural rationale` unlocks the **`✅ Confirm & Approve Dry-Run Review`** action.
- **Live Deployment Gate**: Checkbox `[x] I authorize executing this DDL on ClickHouse Cloud table` unlocks the **`🚀 Approve & Deploy to ClickHouse Cloud`** action.
- **Sidebar Registry Tools**: **`🧹 Clear Schemas`** and **`🔄 Reset chDB`**.

---

### CUJ 2: Analyst Interface (FastAPI / LibreChat)

The Analyst interface runs as an OpenAI-compatible HTTP service that can be queried via curl, Python, or connected directly to LibreChat.

---

#### 1. How to Up the Backend Service

The unified FastAPI backend (`src/atlys_agentic/run_chat.py`) serves both the **CUJ 1 Web Ingestion Portal** and the **CUJ 2 OpenAI-Compatible Chat API** for LibreChat.

##### Option A: Uvicorn (Recommended for Development)
```bash
uvicorn atlys_agentic.run_chat:app --host 0.0.0.0 --port 8008 --reload
```

##### Option B: Python Module
```bash
python -m atlys_agentic.run_chat
```

##### Option C: Package CLI Entrypoint
```bash
atlys-chat
```

##### Verify Backend Health
Ensure the backend is up and responding:
```bash
curl http://localhost:8008/healthz
# Expected response: {"status":"ok"}
```

##### Backend Service Endpoints
| Endpoint | Method | Purpose |
| :--- | :--- | :--- |
| `http://localhost:8008/` or `/ui/ingestion` | `GET` | Interactive Web Portal for CUJ 1 Schema Ingestion & HITL approval |
| `http://localhost:8008/v1/chat/completions` | `POST` | OpenAI-compatible endpoint used by LibreChat and curl |
| `http://localhost:8008/healthz` | `GET` | Service liveness healthcheck |
| `http://localhost:8008/api/specs` | `GET` | Lists available feature specifications |
| `http://localhost:8008/api/ingest/propose` | `POST` | Generates DDL & context diff proposals (Dry-run) |
| `http://localhost:8008/api/ingest/approve` | `POST` | Deploys schema to ClickHouse Cloud & updates `chDB` registry |
| `http://localhost:8008/api/analyze/query` | `POST` | Programmatic analyst query execution |

> ⚠️ **Important**: The backend service **must be running on host port 8008** before sending queries from LibreChat, as LibreChat's Docker container forwards requests to `http://host.docker.internal:8008/v1`.

---

#### 2. Test Backend via curl
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

---

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

---

#### 4. Connect to LibreChat (Separate Dedicated Agent Personas)

A pre-configured LibreChat stack is included in `src/atlys_agentic/librechat/librechat.yaml`. The two CUJs are mapped to **two separate, dedicated agent personas** in LibreChat:

| Agent in LibreChat Dropdown | Model Identifier | Dedicated CUJ Scope | Key Capabilities |
| :--- | :--- | :--- | :--- |
| **`Atlys Instrumentation Engineer`** | `atlys-instrumentation` | **CUJ 1: Schema Ingestion & Evolution** | • Feature spec discovery (*"Show specs"*)<br>• 6-pillar ClickHouse storage rationale (`ORDER BY`, `PARTITION BY`, `LowCardinality`, `SummingMergeTree`, `TTL`)<br>• Technical follow-up questions & ClickHouse deep dives<br>• Schema amendments (*"Add column promo_code Nullable(String)"*)<br>• In-chat Human-in-the-Loop (HITL) cloud deployment (*"APPROVE <table_name>"*) |
| **`Atlys Product Analyst`** | `atlys-analyst` | **CUJ 2: Telemetry Diagnostics & Root Cause Analysis** | • Funnel drop-off and conversion rate analysis<br>• Multi-cut segment breakdowns (`device_type`, `geoip_country_code`, `destination`)<br>• Known anomaly correlation (`K1`–`K7`)<br>• Deterministic statistical confidence scoring ($f(N, \Delta, \text{match})$)<br>• Structured PM diagnostic reports |

##### Step 1: Start the LibreChat Stack
Make sure the backend service is running on host port `8008`, then launch LibreChat and MongoDB with Docker Compose:
```bash
docker compose -f src/atlys_agentic/librechat/docker-compose.librechat.yml up -d
```

##### Step 2: Open LibreChat in Your Browser
- **LibreChat Web UI URL**: **`http://localhost:3080`**

##### Step 3: Register or Log In
- On first visit, register a local user account (Registration is enabled: `ALLOW_REGISTRATION=true`, email verification disabled: `CHECK_EMAIL_VERIFICATION=false`).
- Sign in with your registered credentials.

##### Step 4: Select Your Agent in LibreChat

In the top-left model dropdown, select the agent persona for your task:

###### 🛠️ Option 1: Choose "Atlys Instrumentation Engineer" (CUJ 1 Ingestion)
- **Discover Specs**: *"What specs are available for ingestion?"*
- **Propose Schema**: *"Propose schema for 01_express_checkout"*
  - Returns 6-pillar ClickHouse storage rationale, Table DDL, `SummingMergeTree` Materialized View, and Context Diff Audit.
- **Ask Follow-Ups**: *"Why did you use SummingMergeTree?"* or *"Why is user_id second in ORDER BY?"*
- **Modify Schema**: *"Add column promo_code Nullable(String)"*
- **Authorize Deployment**: Type **`APPROVE express_checkout`** to deploy live to ClickHouse Cloud and snapshot into `chDB.schema_registry`.
- *(Note: If an analytics question is asked, the agent provides a polite scope notice directing you to switch to the Product Analyst persona).*

###### 📊 Option 2: Choose "Atlys Product Analyst" (CUJ 2 Telemetry & RCA)
- **Investigate Drops**: *"Is there an iOS OTP drop on Express Checkout during verification?"*
- **Segment Cuts**: *"Break down Express Checkout conversion by device type and country."*
- Returns live multi-cut ClickHouse aggregations, known issue correlation (`K1`), and statistical confidence scores.
- *(Note: If a schema proposal request is asked, the agent provides a polite scope notice directing you to switch to the Instrumentation Engineer persona).*

---

##### LibreChat Endpoint Configuration (`src/atlys_agentic/librechat/librechat.yaml`)
```yaml
version: 1.1.5
cache: true
endpoints:
  custom:
    - name: "Atlys Instrumentation Engineer"
      apiKey: "dummy-key-not-checked"
      baseURL: "http://host.docker.internal:8008/v1"
      models:
        default: ["atlys-instrumentation"]
        fetch: false
      titleConvo: false
      titleModel: "atlys-instrumentation"
      modelDisplayLabel: "Atlys Instrumentation Engineer (CUJ 1 Ingestion)"

    - name: "Atlys Product Analyst"
      apiKey: "dummy-key-not-checked"
      baseURL: "http://host.docker.internal:8008/v1"
      models:
        default: ["atlys-analyst"]
        fetch: false
      titleConvo: false
      titleModel: "atlys-analyst"
      modelDisplayLabel: "Atlys Product Analyst (CUJ 2 Analytics)"
```

---

### CrewAI LLM Smoke Test

To verify direct end-to-end integration between CrewAI, Gemini LLM (via LiteLLM), and Langfuse tracing:

```bash
python -m atlys_agentic.crew --spec_id 01_express_checkout --table express_checkout
```
Prints the synthesized reasoning and outputs the active Langfuse trace URL.

---

## 4. Metadata Architecture & Industry Context (`chDB`)

InsightMesh maintains four foundational metadata tables inside an embedded, zero-dependency `chDB` (ClickHouse Embedded) storage layer. These primitives embody key innovations from the modern data stack:

| Metadata Table | Core Purpose | Industry Equivalent & Pioneers | When & Why It Became Popular | Role in InsightMesh |
| :--- | :--- | :--- | :--- | :--- |
| **`schema_registry`** | Contract & DDL Versioning | **Confluent Schema Registry**, AWS Glue Data Catalog | **~2015**: Rapid growth of event-driven architectures led to downstream breaking changes; schema registries enforced compatibility rules. | Tracks active table versions, column lists, and DDL history. Decides whether to `CREATE_NEW`, `REUSE_EXISTING`, or `ALTER_EXISTING`. |
| **`business_context`** | Semantic Layer & Business Glossary | **Looker LookML**, **dbt Semantic Layer (MetricFlow)**, Atlan | **~2012–2021**: Solved metric divergence (conflicting definitions across teams) and centralized data quality caveats in code. | Single source of truth for business logic, metric definitions (e.g. conversion denominators), and known technical issues (`K1`–`K7`). |
| **`context_changelog`** | Lineage & Governance Audit Trail | **OpenLineage**, **Marquez** (Linux Foundation), Monte Carlo | **~2020–2022**: Data observability revolution; compliance and root-cause analysis demanded immutable audit trails of metadata changes. | Append-only audit log tracking every definition updated by the **Context Librarian** along with author agent and Langfuse trace ID. |
| **`insights`** | Durable Analytical Memory Store | **Feature Stores** (Feast, Tecton), Langfuse Agent Observability | **~2020–2025**: Analytical findings previously died in Slack/slides; AI agents require durable memory to avoid repeating or hallucinating past findings. | Persists structured anomaly diagnoses, multi-cut segment deltas, and statistical confidence scores produced by the **Product Analyst**. |

### UI Registry Management
The Streamlit portal (`src/atlys_agentic/ui_ingestion.py`) provides direct controls in the sidebar:
- **`🧹 Clear Schemas`**: Truncates `schema_registry` so all incoming feature specs are evaluated as fresh `CREATE_NEW` tables while preserving learned business context.
- **`🔄 Reset chDB`**: Performs a full factory reset across all 4 metadata tables and re-seeds `business_context` fresh from `base_context.md`.



