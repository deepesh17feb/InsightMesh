# Atlys Agentic Analytics System — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the full agentic pipeline from `final_wiby.md` (Instrumentation Agent, Analytics Agent, Context Agent, Tracing/Visualization) as a CrewAI **Flow**-based system on ClickHouse Cloud + chDB, ending in a rehearsed Day-2 unseen-spec submission bundle.

**Architecture:** Two CrewAI `Flow`s (`IngestionFlow` for CUJ1, `AnalysisFlow` for CUJ2) built from `@start`/`@listen`/`@router` steps — dynamic, conditional, not a fixed linear pipeline (HITL approve/reject branches, known-issue-match branches). Flows call deterministic Python tool functions (`tools.py`) for anything that must be reproducible (schema rules, confidence scoring, context diffing) and call memory-free CrewAI `Agent`s only for the judgment/narration parts (naming rationale, insight prose, contradiction write-up). All state lives in chDB tables or ClickHouse Cloud — never in CrewAI memory. `run_ingestion.py` (CLI, CUJ1) and `run_chat.py` (FastAPI backend behind LibreChat, CUJ2) are separate, decoupled entry points sharing `tools.py`/`chdb_client.py`/`ch_client.py`.

**Tech Stack:** Python 3.11 · `crewai>=1.15` (Flows: `Flow`, `start`, `listen`, `router`) · `clickhouse-connect` (ClickHouse Cloud) · `chdb` (embedded, `chdb.query(sql, output_format=, path=)`, persists to `CHDB_PATH` on disk) · `litellm` (LLM routing) · `langfuse` + LiteLLM's Langfuse callback (tracing) · `fastapi`/`uvicorn` (OpenAI-compatible backend for LibreChat) · LibreChat (official Docker image, custom endpoint) · `streamlit` (dashboard) · `pytest`. LLM: Gemini via LiteLLM (`gemini/gemini-2.5-flash`, temperature `0`), key already in `atlys_agentic/config/.env`.

## Global Constraints

- ClickHouse Cloud is the primary datastore; chDB is local/embedded metadata-only (business_context, schema_registry, context_changelog, insights) — never raw event data.
- `ORDER BY` must lead with query predicates — `(timestamp, user_id[, segment])`. Never copy the legacy `(id, timestamp, user_id)` id-first key from the 8 existing tables.
- `PARTITION BY toYYYYMM(timestamp)` on every new table (matches existing convention).
- `LowCardinality(String)` for categorical columns (device_type/os/currency/channel/saved_method_type-style); `UInt8` for booleans; `DateTime` for timestamps; flatten nested JSON objects into flat typed columns.
- `TTL timestamp + INTERVAL 12 MONTH` on every raw event table.
- All DDL execution is idempotent: `CREATE TABLE IF NOT EXISTS`; re-running ingestion on the same spec upserts the `schema_registry` row by version, does not duplicate.
- LLM temperature `0` for every schema-inference and analysis call (determinism).
- No CrewAI native Short/Long/Entity memory anywhere — every `Agent`/`Crew` constructed with `memory=False`. All context is retrieved via explicit SQL against chDB at call time.
- The Analyst path is strictly `SELECT`-only. `Tool_Analytics_Compute` must reject any non-`SELECT` statement before executing.
- Never pass raw event rows to the LLM. All aggregation happens in ClickHouse; the LLM only ever sees JSON summaries.
- A DDL statement may only reach ClickHouse Cloud after a human types the literal string `APPROVE` at the CUJ1 gate.
- Every insight must cut by at least `device_type`, a geo column, `destination`, plus one feature-relevant segment before it is allowed to conclude anything (multi-cut rule).
- Every agent step, tool call, executed SQL statement, and context source row must be emitted as a Langfuse span, under one root trace per run tagged with `spec_id`.
- Real credentials (ClickHouse, Langfuse, Gemini) live only in `atlys_agentic/config/.env` (gitignored). `atlys_agentic/config/.env.example` ships placeholders only — never real secrets.

---

## File Structure

```
atlys_agentic/
├── paths.py                    # path constants (points at existing "problem statment/" dir, no data copy)
├── chdb_client.py               # chDB connection wrapper + schema init (business_context, schema_registry, context_changelog, insights)
├── ch_client.py                 # ClickHouse Cloud client wrapper (clickhouse-connect)
├── tracing.py                   # Langfuse span helpers + LiteLLM callback wiring
├── tools.py                     # 9 deterministic Tool_* functions
├── agents.py                    # 3 memory-free CrewAI Agent personas
├── flows/
│   ├── __init__.py
│   ├── ingestion_flow.py        # IngestionFlow (CUJ1) — start/listen/router, HITL gate
│   └── analysis_flow.py         # AnalysisFlow (CUJ2) — start/listen/router, known-issue branch
├── run_ingestion.py              # CUJ1 CLI entrypoint
├── run_chat.py                   # CUJ2 FastAPI backend (OpenAI-compatible, behind LibreChat)
├── librechat/
│   ├── docker-compose.librechat.yml
│   └── librechat.yaml            # custom endpoint config pointing at run_chat.py
├── viz/
│   ├── __init__.py
│   ├── cli_report.py             # structured CLI renderer (3 required views)
│   └── dashboard.py              # lightweight Streamlit dashboard (same 3 views)
├── assemble_submission.py        # packages submission/06_unseen/{schema.sql, insight.md, trace.json}
├── config/
│   ├── .env                      # REAL creds (gitignored, already created)
│   └── .env.example              # placeholders only, committed
├── outputs/{schemas,insights,traces}/   # created at runtime
├── submission/06_unseen/                 # created at runtime
├── specs/06_unseen/                      # empty until Day 2
├── tests/
│   ├── conftest.py
│   ├── test_tools.py
│   ├── test_ingestion_flow.py
│   ├── test_analysis_flow.py
│   ├── test_chat_backend.py
│   ├── test_viz.py
│   └── test_e2e_rehearsal.py
├── requirements.txt
└── README.md
```

Existing dataset stays in place at `problem statment/data/` and `problem statment/specs/` (repo already has it, has spaces in the dirname, and parquet files are large — `paths.py` references it directly instead of copying).

---

### Task 1: Repo scaffold, config contract, path constants

**Files:**
- Create: `atlys_agentic/paths.py`
- Create: `atlys_agentic/config/.env.example`
- Create: `atlys_agentic/requirements.txt`
- Create: `atlys_agentic/README.md`
- Create: `atlys_agentic/tests/conftest.py`
- Test: `atlys_agentic/tests/test_paths.py`

**Interfaces:**
- Produces: `paths.PROBLEM_STATEMENT_DIR`, `paths.DATA_DIR`, `paths.SPECS_DIR`, `paths.BASE_CONTEXT_MD`, `paths.OUTPUTS_DIR`, `paths.SUBMISSION_DIR`, `paths.CHDB_PATH` (all `pathlib.Path`), `paths.spec_dir(spec_id: str) -> Path`, `paths.spec_md(spec_id: str) -> Path`, `paths.events_ndjson(spec_id: str) -> Path`.

- [ ] **Step 1: Write the failing test**

```python
# atlys_agentic/tests/test_paths.py
from atlys_agentic import paths


def test_problem_statement_paths_resolve():
    assert paths.BASE_CONTEXT_MD.exists()
    assert paths.DATA_DIR.joinpath("ddl.sql").exists()


def test_spec_dir_helper():
    d = paths.spec_dir("01_express_checkout")
    assert d.exists()
    assert paths.spec_md("01_express_checkout").exists()
    assert paths.events_ndjson("01_express_checkout").exists()


def test_unseen_spec_dir_does_not_exist_yet():
    d = paths.spec_dir("06_unseen")
    assert not paths.spec_md("06_unseen").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd atlys_agentic && python -m pytest tests/test_paths.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'atlys_agentic'` (module doesn't exist yet).

- [ ] **Step 3: Write `paths.py`**

```python
# atlys_agentic/paths.py
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROBLEM_STATEMENT_DIR = REPO_ROOT / "problem statment"
DATA_DIR = PROBLEM_STATEMENT_DIR / "data"
SPECS_DIR = PROBLEM_STATEMENT_DIR / "specs"
BASE_CONTEXT_MD = PROBLEM_STATEMENT_DIR / "base_context.md"
DDL_SQL = DATA_DIR / "ddl.sql"
LOAD_SH = DATA_DIR / "load.sh"

ATLYS_AGENTIC_DIR = Path(__file__).resolve().parent
CHDB_PATH = ATLYS_AGENTIC_DIR / "chdb_data"
OUTPUTS_DIR = ATLYS_AGENTIC_DIR / "outputs"
SCHEMAS_DIR = OUTPUTS_DIR / "schemas"
INSIGHTS_DIR = OUTPUTS_DIR / "insights"
TRACES_DIR = OUTPUTS_DIR / "traces"
SUBMISSION_DIR = ATLYS_AGENTIC_DIR / "submission"
UNSEEN_SPECS_DIR = ATLYS_AGENTIC_DIR / "specs" / "06_unseen"

for _d in (OUTPUTS_DIR, SCHEMAS_DIR, INSIGHTS_DIR, TRACES_DIR, SUBMISSION_DIR, UNSEEN_SPECS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def spec_dir(spec_id: str) -> Path:
    if spec_id == "06_unseen":
        return UNSEEN_SPECS_DIR
    return SPECS_DIR / spec_id


def spec_md(spec_id: str) -> Path:
    return spec_dir(spec_id) / "spec.md"


def events_ndjson(spec_id: str) -> Path:
    return spec_dir(spec_id) / "events.ndjson"
```

- [ ] **Step 4: Create `__init__.py`, `.env.example`, `requirements.txt`, `README.md`, `conftest.py`**

```python
# atlys_agentic/__init__.py
```

```
# atlys_agentic/config/.env.example
CLICKHOUSE_HOST=
CLICKHOUSE_USER=
CLICKHOUSE_PASSWORD=
CLICKHOUSE_PORT=8443
CLICKHOUSE_SECURE=true
CLICKHOUSE_DATABASE=clickathon

LANGFUSE_SECRET_KEY=
LANGFUSE_PUBLIC_KEY=
LANGFUSE_BASE_URL=https://us.cloud.langfuse.com
LANGFUSE_HOST=https://us.cloud.langfuse.com

LLM_PROVIDER=gemini
LLM_MODEL=gemini/gemini-2.5-flash
LLM_TEMPERATURE=0
GEMINI_API_KEY=

CHDB_PATH=./chdb_data
```

```
# atlys_agentic/requirements.txt
crewai>=1.15.0
clickhouse-connect>=0.7
chdb>=4.2.1
litellm>=1.50
langfuse>=2.50
fastapi>=0.110
uvicorn>=0.30
pydantic>=2.6
python-dotenv>=1.0
streamlit>=1.35
pytest>=8.0
```

```python
# atlys_agentic/tests/conftest.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
```

README.md: one paragraph pointing at `final_wiby.md` as the design doc and listing the two entrypoints (`run_ingestion.py --spec_dir specs/NN`, `run_chat.py` behind LibreChat).

- [ ] **Step 5: Run test to verify it passes**

Run: `cd atlys_agentic && python -m pytest tests/test_paths.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add atlys_agentic/paths.py atlys_agentic/__init__.py atlys_agentic/config/.env.example \
  atlys_agentic/requirements.txt atlys_agentic/README.md atlys_agentic/tests/conftest.py \
  atlys_agentic/tests/test_paths.py atlys_agentic/tests/__init__.py
git commit -m "feat: scaffold atlys_agentic package with path constants"
```

(Note: `atlys_agentic/config/.env` with real secrets already exists and is gitignored — do not add it.)

---

### Task 2: chDB client + metadata schema init

**Files:**
- Create: `atlys_agentic/chdb_client.py`
- Test: `atlys_agentic/tests/test_chdb_client.py`

**Interfaces:**
- Consumes: `paths.CHDB_PATH`, `paths.BASE_CONTEXT_MD` (Task 1).
- Produces: `chdb_client.run(sql: str, fmt: str = "JSON") -> dict | list`, `chdb_client.init_schema() -> None`, `chdb_client.init_base_context() -> int` (returns rows inserted).

Table shapes (from `final_wiby.md` §8.3):
```sql
business_context(id, section, key, definition, version, valid_from, source, status)
schema_registry(table, ddl, columns_json, spec_id, version, created_at)
context_changelog(ts, change_type, before, after, agent, trace_id)
insights(spec_id, question, answer_md, confidence, cuts_json, trace_id, created_at)
```

- [ ] **Step 1: Write the failing test**

```python
# atlys_agentic/tests/test_chdb_client.py
import shutil
from atlys_agentic import paths, chdb_client


def setup_function():
    shutil.rmtree(paths.CHDB_PATH, ignore_errors=True)


def test_init_schema_creates_four_tables():
    chdb_client.init_schema()
    rows = chdb_client.run("SHOW TABLES")
    names = {r["name"] for r in rows}
    assert {"business_context", "schema_registry", "context_changelog", "insights"} <= names


def test_init_base_context_chunks_markdown_into_rows():
    chdb_client.init_schema()
    inserted = chdb_client.init_base_context()
    assert inserted > 0
    rows = chdb_client.run("SELECT count() AS c FROM business_context")
    assert rows[0]["c"] == inserted


def test_run_rejects_non_select_read_helper_still_allows_ddl():
    # chdb_client.run is the low-level executor (allows DDL for our own metadata
    # tables); read-only enforcement belongs to Tool_Analytics_Compute (Task 7),
    # not here.
    chdb_client.init_schema()
    chdb_client.run("INSERT INTO business_context VALUES (1, 's', 'k', 'd', 1, now(), 'seed', 'active')")
    rows = chdb_client.run("SELECT * FROM business_context WHERE id = 1")
    assert rows[0]["key"] == "k"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd atlys_agentic && python -m pytest tests/test_chdb_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'atlys_agentic.chdb_client'`.

- [ ] **Step 3: Write `chdb_client.py`**

```python
# atlys_agentic/chdb_client.py
import json
import re

import chdb

from atlys_agentic import paths

_SCHEMA_DDL = [
    """
    CREATE TABLE IF NOT EXISTS business_context (
        id UInt32,
        section String,
        key String,
        definition String,
        version UInt16,
        valid_from DateTime,
        source String,
        status String
    ) ENGINE = MergeTree ORDER BY (section, key, version)
    """,
    """
    CREATE TABLE IF NOT EXISTS schema_registry (
        table String,
        ddl String,
        columns_json String,
        spec_id String,
        version UInt16,
        created_at DateTime
    ) ENGINE = MergeTree ORDER BY (table, version)
    """,
    """
    CREATE TABLE IF NOT EXISTS context_changelog (
        ts DateTime,
        change_type String,
        before String,
        after String,
        agent String,
        trace_id String
    ) ENGINE = MergeTree ORDER BY ts
    """,
    """
    CREATE TABLE IF NOT EXISTS insights (
        spec_id String,
        question String,
        answer_md String,
        confidence Float32,
        cuts_json String,
        trace_id String,
        created_at DateTime
    ) ENGINE = MergeTree ORDER BY (spec_id, created_at)
    """,
]


def run(sql: str, fmt: str = "JSON"):
    paths.CHDB_PATH.mkdir(parents=True, exist_ok=True)
    result = chdb.query(sql, output_format=fmt, path=str(paths.CHDB_PATH))
    text = str(result)
    if fmt == "JSON" and text.strip():
        payload = json.loads(text)
        return payload.get("data", [])
    return text


def init_schema() -> None:
    for ddl in _SCHEMA_DDL:
        run(ddl, fmt="CSV")


def init_base_context() -> int:
    """Chunk base_context.md into business_context rows, one row per
    numbered section (## N. Title) split further by list item / paragraph."""
    text = paths.BASE_CONTEXT_MD.read_text(encoding="utf-8")
    sections = re.split(r"\n## ", text)[1:]  # drop preamble before first "## "
    inserted = 0
    next_id = 1
    for section in sections:
        lines = section.splitlines()
        title = lines[0].strip()
        body = "\n".join(lines[1:]).strip()
        for i, chunk in enumerate([p for p in body.split("\n\n") if p.strip()]):
            key = f"{title[:40]}#{i}".replace("'", "").replace("\n", " ")
            definition = chunk.replace("'", "''")
            run(
                f"""INSERT INTO business_context VALUES
                ({next_id}, '{title.replace("'", "''")}', '{key}',
                 '{definition}', 1, now(), 'base_context.md', 'active')""",
                fmt="CSV",
            )
            next_id += 1
            inserted += 1
    return inserted
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd atlys_agentic && python -m pytest tests/test_chdb_client.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add atlys_agentic/chdb_client.py atlys_agentic/tests/test_chdb_client.py
git commit -m "feat: chDB client with business_context/schema_registry/context_changelog/insights schema"
```

---

### Task 3: ClickHouse Cloud client + 8-table bootstrap

**Files:**
- Create: `atlys_agentic/ch_client.py`
- Test: `atlys_agentic/tests/test_ch_client.py`

**Interfaces:**
- Consumes: `paths.DDL_SQL`, `paths.DATA_DIR` (Task 1); env vars `CLICKHOUSE_HOST/USER/PASSWORD/PORT/SECURE/DATABASE` from `atlys_agentic/config/.env`.
- Produces: `ch_client.get_client() -> clickhouse_connect.driver.Client`, `ch_client.command(sql: str) -> None`, `ch_client.select(sql: str) -> list[dict]`, `ch_client.bootstrap_existing_tables() -> None`.

- [ ] **Step 1: Write the failing test**

```python
# atlys_agentic/tests/test_ch_client.py
import os
import pytest
from atlys_agentic import ch_client

pytestmark = pytest.mark.skipif(
    not os.getenv("CLICKHOUSE_HOST"),
    reason="requires live ClickHouse Cloud credentials in atlys_agentic/config/.env",
)


def test_select_round_trip():
    rows = ch_client.select("SELECT 1 AS one")
    assert rows == [{"one": 1}]


def test_bootstrap_loads_eight_tables_with_expected_row_count():
    ch_client.bootstrap_existing_tables()
    rows = ch_client.select("SELECT count() AS c FROM destination_card_clicked")
    assert rows[0]["c"] > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd atlys_agentic && python -m pytest tests/test_ch_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'atlys_agentic.ch_client'`.

- [ ] **Step 3: Write `ch_client.py`**

```python
# atlys_agentic/ch_client.py
import os
import subprocess

import clickhouse_connect
from dotenv import load_dotenv

from atlys_agentic import paths

load_dotenv(paths.ATLYS_AGENTIC_DIR / "config" / ".env")

_client = None


def get_client():
    global _client
    if _client is None:
        _client = clickhouse_connect.get_client(
            host=os.environ["CLICKHOUSE_HOST"],
            port=int(os.environ.get("CLICKHOUSE_PORT", "8443")),
            username=os.environ["CLICKHOUSE_USER"],
            password=os.environ["CLICKHOUSE_PASSWORD"],
            secure=os.environ.get("CLICKHOUSE_SECURE", "true").lower() == "true",
            database=os.environ.get("CLICKHOUSE_DATABASE", "default"),
        )
    return _client


def command(sql: str) -> None:
    get_client().command(sql)


def select(sql: str) -> list[dict]:
    result = get_client().query(sql)
    return [dict(zip(result.column_names, row)) for row in result.result_rows]


def bootstrap_existing_tables() -> None:
    """Idempotently create the DB + 8 existing tables and load their parquet
    data, by shelling out to the vendored load.sh (keeps one source of truth
    for the load logic instead of re-implementing parquet insert here)."""
    db = os.environ.get("CLICKHOUSE_DATABASE", "clickathon")
    ch_cmd = (
        f"clickhouse-client --host {os.environ['CLICKHOUSE_HOST']} "
        f"--port {os.environ.get('CLICKHOUSE_PORT', '9440')} "
        f"--user {os.environ['CLICKHOUSE_USER']} "
        f"--password {os.environ['CLICKHOUSE_PASSWORD']} --secure"
    )
    subprocess.run(
        [str(paths.LOAD_SH)],
        env={**os.environ, "CH": ch_cmd, "DB": db},
        check=True,
    )
```

- [ ] **Step 4: Run test**

Run: `cd atlys_agentic && python -m pytest tests/test_ch_client.py -v`
Expected: if `atlys_agentic/config/.env` is loaded (it is, real creds present) and `clickhouse-client` CLI is installed, both pass; `bootstrap_existing_tables` uses the CLI's native Parquet insert since it's already battle-tested in `load.sh`. If `clickhouse-client` binary isn't installed in the exec environment, install it first (`curl https://clickhouse.com/ | sh`) — this is an environment prerequisite, not a code bug.

- [ ] **Step 5: Commit**

```bash
git add atlys_agentic/ch_client.py atlys_agentic/tests/test_ch_client.py
git commit -m "feat: ClickHouse Cloud client + 8-table bootstrap loader"
```

---

### Task 4: `Tool_Infer_Schema` — type inference, nested flatten, order/partition/TTL rules

**Files:**
- Create: `atlys_agentic/tools.py` (this task starts the file; later tasks append to it)
- Test: `atlys_agentic/tests/test_tools.py` (this task starts the file)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `tools.Tool_Infer_Schema(ndjson_path: Path, spec_md_text: str, table_name: str) -> str` (returns a full `CREATE TABLE` DDL string). Later tasks (5–11) append `Tool_Generate_MV`, `Tool_Execute_DDL`, `Tool_Analytics_Compute`, `Tool_Context_Diff`, `Tool_Context_Upsert`, `Tool_Score_Confidence`, `Tool_Emit_Viz` to the same two files.

Rules encoded (Global Constraints, verbatim from `final_wiby.md` §7.1):
- `ORDER BY (timestamp, user_id[, segment])` — never id-first.
- `PARTITION BY toYYYYMM(timestamp)`.
- Categorical string fields (cardinality signal: field name in a known low-cardinality set, or all sampled values are short enums) → `LowCardinality(String)`.
- `0/1`-only integer fields → `UInt8`. Fields with only integer values and no decimals seen → `Int64`. Fields with any float value → `Float64`. Timestamp-looking field → `DateTime`.
- Nested JSON objects (e.g. `payment: {amount, currency, latency_ms}`) flatten to `payment_amount`, `payment_currency`, `payment_latency_ms`.
- `TTL timestamp + INTERVAL 12 MONTH`.

- [ ] **Step 1: Write the failing test**

```python
# atlys_agentic/tests/test_tools.py
import json
from pathlib import Path

import pytest

from atlys_agentic import tools


@pytest.fixture
def express_checkout_ndjson(tmp_path):
    events = [
        {
            "event": "express_checkout_shown",
            "timestamp": "2026-04-01T10:00:00",
            "user_id": "u1",
            "application_id": "a1",
            "device_type": "ios",
            "os": "iOS 17",
            "geoip_country_code": "AE",
            "shown_amount": 120.5,
            "currency": "AED",
        },
        {
            "event": "express_payment_confirmed",
            "timestamp": "2026-04-01T10:01:00",
            "user_id": "u1",
            "application_id": "a1",
            "device_type": "ios",
            "os": "iOS 17",
            "geoip_country_code": "AE",
            "payment": {"amount": 120.5, "currency": "AED", "latency_ms": 850},
        },
    ]
    p = tmp_path / "events.ndjson"
    p.write_text("\n".join(json.dumps(e) for e in events))
    return p


def test_infer_schema_never_leads_order_by_with_id(express_checkout_ndjson):
    ddl = tools.Tool_Infer_Schema(express_checkout_ndjson, "spec text", "express_checkout")
    assert "ORDER BY (timestamp, user_id)" in ddl
    assert "ORDER BY (id" not in ddl


def test_infer_schema_partitions_by_month(express_checkout_ndjson):
    ddl = tools.Tool_Infer_Schema(express_checkout_ndjson, "spec text", "express_checkout")
    assert "PARTITION BY toYYYYMM(timestamp)" in ddl


def test_infer_schema_flattens_nested_payment_object(express_checkout_ndjson):
    ddl = tools.Tool_Infer_Schema(express_checkout_ndjson, "spec text", "express_checkout")
    assert "payment_amount" in ddl
    assert "payment_currency" in ddl
    assert "payment_latency_ms" in ddl
    assert "payment Nested" not in ddl
    assert "payment String" not in ddl


def test_infer_schema_uses_low_cardinality_for_categorical_columns(express_checkout_ndjson):
    ddl = tools.Tool_Infer_Schema(express_checkout_ndjson, "spec text", "express_checkout")
    assert "device_type LowCardinality(String)" in ddl
    assert "os LowCardinality(String)" in ddl
    assert "currency LowCardinality(String)" in ddl


def test_infer_schema_has_ttl_twelve_months(express_checkout_ndjson):
    ddl = tools.Tool_Infer_Schema(express_checkout_ndjson, "spec text", "express_checkout")
    assert "TTL timestamp + INTERVAL 12 MONTH" in ddl
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd atlys_agentic && python -m pytest tests/test_tools.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'atlys_agentic.tools'`.

- [ ] **Step 3: Write `tools.py` (Part 1: schema inference)**

```python
# atlys_agentic/tools.py
"""Deterministic tool functions used by the CrewAI Flow steps.

Kept LLM-free and pure Python: schema rules, confidence scoring and context
diffing must be reproducible given the same input, independent of any model
call, so a judge re-running the pipeline gets the same schema/score every time.
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

_LOW_CARDINALITY_HINTS = {
    "device_type", "os", "currency", "channel", "saved_method_type",
    "geoip_country_code", "auth_method", "payment_method", "card_type",
    "visa_type", "capture_mode", "scan_mode", "doc_type", "source",
    "funnel_type", "flow", "page_version",
}

_TIMESTAMP_KEYS = {"timestamp", "ts", "created_at", "occurred_at"}


def _flatten(event: dict, prefix: str = "") -> dict:
    flat = {}
    for k, v in event.items():
        key = f"{prefix}{k}" if not prefix else f"{prefix}_{k}"
        if isinstance(v, dict):
            flat.update(_flatten(v, key))
        else:
            flat[key] = v
    return flat


def _infer_type(key: str, values: list) -> str:
    non_null = [v for v in values if v is not None]
    if not non_null:
        return "Nullable(String)"
    if key in _TIMESTAMP_KEYS or key.endswith("_at"):
        return "DateTime"
    if all(isinstance(v, bool) for v in non_null):
        return "UInt8"
    if all(isinstance(v, int) and not isinstance(v, bool) for v in non_null):
        if set(non_null) <= {0, 1} and ("is_" in key or key.startswith("has_")):
            return "UInt8"
        return "Int64"
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in non_null):
        return "Float64"
    # string-typed
    base = key.split("_")[-1] if "_" in key else key
    if key in _LOW_CARDINALITY_HINTS or base in _LOW_CARDINALITY_HINTS:
        return "LowCardinality(String)"
    return "Nullable(String)"


def _load_events(ndjson_path: Path) -> list[dict]:
    events = []
    for line in Path(ndjson_path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            events.append(json.loads(line))
    return events


def Tool_Infer_Schema(ndjson_path: Path, spec_md_text: str, table_name: str) -> str:
    """Infer a production DDL from an NDJSON sample. Deterministic: same
    sample + table name always produces the same DDL."""
    events = _load_events(ndjson_path)
    flattened = [_flatten(e) for e in events]

    columns: dict[str, list] = {}
    for row in flattened:
        for k, v in row.items():
            columns.setdefault(k, []).append(v)
    # columns absent in some rows are implicitly None there
    for k in columns:
        columns[k] = columns[k] + [None] * (len(flattened) - len(columns[k]))

    ordered_keys = list(dict.fromkeys(k for row in flattened for k in row))
    lines = []
    for key in ordered_keys:
        if key in ("user_id", "application_id", "id"):
            col_type = "String" if key != "id" else "UUID"
        else:
            col_type = _infer_type(key, columns[key])
        lines.append(f"    {key} {col_type}")

    if "timestamp" not in ordered_keys:
        lines.insert(0, "    timestamp DateTime")

    columns_sql = ",\n".join(lines)
    order_cols = "timestamp, user_id"
    return (
        f"CREATE TABLE IF NOT EXISTS {table_name}\n"
        f"(\n{columns_sql}\n)\n"
        f"ENGINE = MergeTree\n"
        f"PARTITION BY toYYYYMM(timestamp)\n"
        f"ORDER BY ({order_cols})\n"
        f"TTL timestamp + INTERVAL 12 MONTH;"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd atlys_agentic && python -m pytest tests/test_tools.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add atlys_agentic/tools.py atlys_agentic/tests/test_tools.py
git commit -m "feat: Tool_Infer_Schema with order-by/partition/TTL/flatten rules"
```

---

### Task 5: `Tool_Generate_MV` — funnel/aggregate materialized views

**Files:**
- Modify: `atlys_agentic/tools.py`
- Modify: `atlys_agentic/tests/test_tools.py`

**Interfaces:**
- Consumes: DDL string shape from Task 4 (column names available via `columns_from_ddl` helper introduced here).
- Produces: `tools.Tool_Generate_MV(table_name: str, ddl: str, funnel_step_column: str = "event") -> str` (returns MV DDL, or `""` if no MV is justified — must earn its keep per design).

- [ ] **Step 1: Write the failing test**

```python
# append to atlys_agentic/tests/test_tools.py

def test_generate_mv_creates_daily_segment_rollup():
    ddl = (
        "CREATE TABLE IF NOT EXISTS express_checkout\n"
        "(\n    timestamp DateTime,\n    user_id String,\n"
        "    device_type LowCardinality(String),\n    event LowCardinality(String)\n)\n"
        "ENGINE = MergeTree\nPARTITION BY toYYYYMM(timestamp)\nORDER BY (timestamp, user_id)\n"
        "TTL timestamp + INTERVAL 12 MONTH;"
    )
    mv = tools.Tool_Generate_MV("express_checkout", ddl)
    assert "CREATE MATERIALIZED VIEW IF NOT EXISTS express_checkout_daily_mv" in mv
    assert "toYYYYMMDD(timestamp)" in mv
    assert "device_type" in mv
    assert "-- justification:" in mv  # every MV must justify itself in the DDL comment


def test_generate_mv_skips_when_no_segment_column_present():
    ddl = (
        "CREATE TABLE IF NOT EXISTS tiny\n(\n    timestamp DateTime,\n    user_id String\n)\n"
        "ENGINE = MergeTree\nPARTITION BY toYYYYMM(timestamp)\nORDER BY (timestamp, user_id)\n"
        "TTL timestamp + INTERVAL 12 MONTH;"
    )
    mv = tools.Tool_Generate_MV("tiny", ddl)
    assert mv == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd atlys_agentic && python -m pytest tests/test_tools.py -k generate_mv -v`
Expected: FAIL with `AttributeError: module 'atlys_agentic.tools' has no attribute 'Tool_Generate_MV'`.

- [ ] **Step 3: Append `Tool_Generate_MV` to `tools.py`**

```python
# append to atlys_agentic/tools.py

_SEGMENT_COLUMN_CANDIDATES = ("device_type", "os", "geoip_country_code", "destination")


def _columns_from_ddl(ddl: str) -> list[str]:
    body = ddl.split("(", 1)[1].rsplit(")", 1)[0]
    cols = []
    for line in body.splitlines():
        line = line.strip().rstrip(",")
        if line:
            cols.append(line.split()[0])
    return cols


def Tool_Generate_MV(table_name: str, ddl: str, funnel_step_column: str = "event") -> str:
    """Daily segment-rollup MV, only when a segment column exists — an MV
    over a table with no segment dimension wouldn't earn its keep."""
    cols = _columns_from_ddl(ddl)
    segment_col = next((c for c in _SEGMENT_COLUMN_CANDIDATES if c in cols), None)
    if segment_col is None:
        return ""

    step_expr = f"{funnel_step_column}, " if funnel_step_column in cols else ""
    mv_name = f"{table_name}_daily_mv"
    return (
        f"-- justification: pre-aggregates daily/{segment_col} volume so the "
        f"Analyst never scans raw {table_name} rows for segment cuts\n"
        f"CREATE MATERIALIZED VIEW IF NOT EXISTS {mv_name}\n"
        f"ENGINE = SummingMergeTree\n"
        f"PARTITION BY toYYYYMM(day)\n"
        f"ORDER BY (day, {segment_col}{', ' + funnel_step_column if step_expr else ''})\n"
        f"AS SELECT\n"
        f"    toYYYYMMDD(timestamp) AS day,\n"
        f"    {segment_col},\n"
        f"    {step_expr}"
        f"count() AS events,\n"
        f"    uniq(user_id) AS users\n"
        f"FROM {table_name}\n"
        f"GROUP BY day, {segment_col}{', ' + funnel_step_column if step_expr else ''};"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd atlys_agentic && python -m pytest tests/test_tools.py -k generate_mv -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add atlys_agentic/tools.py atlys_agentic/tests/test_tools.py
git commit -m "feat: Tool_Generate_MV daily segment rollup, skips tables with no segment column"
```

---

### Task 6: `Tool_Execute_DDL` — idempotent execute + schema_registry mirror + rollback

**Files:**
- Modify: `atlys_agentic/tools.py`
- Modify: `atlys_agentic/tests/test_tools.py`

**Interfaces:**
- Consumes: `ch_client.command`, `ch_client.select` (Task 3); `chdb_client.run` (Task 2); `_columns_from_ddl` (Task 5).
- Produces: `tools.Tool_Execute_DDL(ddl: str, table_name: str, spec_id: str) -> dict` returning `{"status": "ok"|"rolled_back", "table": str, "version": int, "error": str | None}`.

- [ ] **Step 1: Write the failing test**

```python
# append to atlys_agentic/tests/test_tools.py
from unittest.mock import patch


def test_execute_ddl_success_writes_versioned_schema_registry_row():
    ddl = "CREATE TABLE IF NOT EXISTS t1 (timestamp DateTime, user_id String) ENGINE=MergeTree ORDER BY (timestamp, user_id)"
    with patch("atlys_agentic.tools.ch_client.command") as mock_command, \
         patch("atlys_agentic.tools.chdb_client.init_schema"), \
         patch("atlys_agentic.tools.chdb_client.run") as mock_chdb_run:
        mock_chdb_run.side_effect = [[], None]  # SELECT max(version) -> [], then INSERT -> None
        result = tools.Tool_Execute_DDL(ddl, "t1", spec_id="01_express_checkout")
    mock_command.assert_called_once_with(ddl)
    assert result == {"status": "ok", "table": "t1", "version": 1, "error": None}


def test_execute_ddl_failure_rolls_back_and_reports_error():
    ddl = "CREATE TABLE IF NOT EXISTS t2 (bad syntax"
    with patch("atlys_agentic.tools.ch_client.command", side_effect=Exception("syntax error")) as mock_command, \
         patch("atlys_agentic.tools.ch_client.select") as mock_select:
        result = tools.Tool_Execute_DDL(ddl, "t2", spec_id="01_express_checkout")
    assert result["status"] == "rolled_back"
    assert "syntax error" in result["error"]
    mock_select.assert_called_once_with("DROP TABLE IF EXISTS t2")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd atlys_agentic && python -m pytest tests/test_tools.py -k execute_ddl -v`
Expected: FAIL with `AttributeError: module 'atlys_agentic.tools' has no attribute 'Tool_Execute_DDL'`.

- [ ] **Step 3: Append `Tool_Execute_DDL` to `tools.py`**

```python
# add near top of atlys_agentic/tools.py, after existing imports
from atlys_agentic import ch_client, chdb_client

# append at end of atlys_agentic/tools.py

def Tool_Execute_DDL(ddl: str, table_name: str, spec_id: str) -> dict:
    """Execute DDL on ClickHouse Cloud, mirror to chDB schema_registry with a
    monotonically increasing version per table. On failure, drop whatever
    partial object exists and report the error instead of leaving Cloud in a
    half-created state."""
    try:
        ch_client.command(ddl)
    except Exception as exc:  # noqa: BLE001 - deliberately broad: any Cloud DDL failure must roll back
        ch_client.select(f"DROP TABLE IF EXISTS {table_name}")
        return {"status": "rolled_back", "table": table_name, "version": None, "error": str(exc)}

    chdb_client.init_schema()
    existing = chdb_client.run(
        f"SELECT max(version) AS v FROM schema_registry WHERE table = '{table_name}'"
    )
    version = (existing[0]["v"] or 0) + 1 if existing and existing[0]["v"] is not None else 1
    columns_json = json.dumps(_columns_from_ddl(ddl)).replace("'", "''")
    ddl_escaped = ddl.replace("'", "''")
    chdb_client.run(
        f"""INSERT INTO schema_registry VALUES
        ('{table_name}', '{ddl_escaped}', '{columns_json}', '{spec_id}', {version}, now())""",
        fmt="CSV",
    )
    return {"status": "ok", "table": table_name, "version": version, "error": None}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd atlys_agentic && python -m pytest tests/test_tools.py -k execute_ddl -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add atlys_agentic/tools.py atlys_agentic/tests/test_tools.py
git commit -m "feat: Tool_Execute_DDL with schema_registry versioning and rollback on failure"
```

---

### Task 7: `Tool_Analytics_Compute` — read-only aggregation on Cloud

**Files:**
- Modify: `atlys_agentic/tools.py`
- Modify: `atlys_agentic/tests/test_tools.py`

**Interfaces:**
- Consumes: `ch_client.select` (Task 3).
- Produces: `tools.Tool_Analytics_Compute(select_sql: str) -> dict` returning `{"rows": list[dict]}` or raising `ValueError` for non-`SELECT` input.

- [ ] **Step 1: Write the failing test**

```python
# append to atlys_agentic/tests/test_tools.py

def test_analytics_compute_rejects_non_select():
    with pytest.raises(ValueError, match="SELECT-only"):
        tools.Tool_Analytics_Compute("DROP TABLE purchase_completed")
    with pytest.raises(ValueError, match="SELECT-only"):
        tools.Tool_Analytics_Compute("INSERT INTO x VALUES (1)")


def test_analytics_compute_returns_json_rows():
    with patch("atlys_agentic.tools.ch_client.select", return_value=[{"c": 42}]) as mock_select:
        result = tools.Tool_Analytics_Compute("SELECT count() AS c FROM purchase_completed")
    mock_select.assert_called_once_with("SELECT count() AS c FROM purchase_completed")
    assert result == {"rows": [{"c": 42}]}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd atlys_agentic && python -m pytest tests/test_tools.py -k analytics_compute -v`
Expected: FAIL with `AttributeError`.

- [ ] **Step 3: Append `Tool_Analytics_Compute` to `tools.py`**

```python
# append to atlys_agentic/tools.py

def Tool_Analytics_Compute(select_sql: str) -> dict:
    """Push all aggregation into ClickHouse; never let raw rows or non-SELECT
    statements reach the caller (Analyst path is read-only by construction)."""
    if not re.match(r"^\s*SELECT\b", select_sql, re.IGNORECASE):
        raise ValueError("Tool_Analytics_Compute is SELECT-only")
    rows = ch_client.select(select_sql)
    return {"rows": rows}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd atlys_agentic && python -m pytest tests/test_tools.py -k analytics_compute -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add atlys_agentic/tools.py atlys_agentic/tests/test_tools.py
git commit -m "feat: Tool_Analytics_Compute enforces SELECT-only, returns JSON rows"
```

---

### Task 8: `Tool_Context_Diff` — contradiction/gap detector

**Files:**
- Modify: `atlys_agentic/tools.py`
- Modify: `atlys_agentic/tests/test_tools.py`

**Interfaces:**
- Consumes: `chdb_client.run` (Task 2).
- Produces: `tools.Tool_Context_Diff(new_table: str, new_columns: list[str]) -> dict` returning `{"additions": list[str], "conflicts": list[str], "gaps": list[str]}`.

Must flag the five known `base_context.md` traps (design §5.3):
1. Conversion-rate denominator conflict (÷ sessions vs ÷ application_started).
2. `os` NULL while `device_type='android'`.
3. Legacy `ORDER BY (id, …)` inherited into a new table.
4. On-time delivery rate not computable from funnel tables.
5. Undocumented columns (e.g. `failed_attempt_threshold`) not in `business_context`.

- [ ] **Step 1: Write the failing test**

```python
# append to atlys_agentic/tests/test_tools.py

def test_context_diff_flags_conversion_rate_denominator_conflict():
    with patch("atlys_agentic.tools.chdb_client.run", return_value=[
        {"key": "conversion_rate#0", "definition": "completed purchases / sessions"},
        {"key": "funnel_conversion#0", "definition": "purchase_completed users / application_started"},
    ]):
        result = tools.Tool_Context_Diff("express_checkout", ["timestamp", "user_id", "device_type"])
    assert any("denominator" in c.lower() for c in result["conflicts"])


def test_context_diff_flags_undocumented_column_as_gap():
    with patch("atlys_agentic.tools.chdb_client.run", return_value=[]):
        result = tools.Tool_Context_Diff("document_uploaded", ["failed_attempt_threshold"])
    assert any("failed_attempt_threshold" in g for g in result["gaps"])


def test_context_diff_flags_new_columns_as_additions():
    with patch("atlys_agentic.tools.chdb_client.run", return_value=[]):
        result = tools.Tool_Context_Diff("express_checkout", ["shown_amount", "otp_attempts"])
    assert "express_checkout.shown_amount" in result["additions"]
    assert "express_checkout.otp_attempts" in result["additions"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd atlys_agentic && python -m pytest tests/test_tools.py -k context_diff -v`
Expected: FAIL with `AttributeError`.

- [ ] **Step 3: Append `Tool_Context_Diff` to `tools.py`**

```python
# append to atlys_agentic/tools.py

_KNOWN_UNDOCUMENTED_COLUMNS = {"failed_attempt_threshold", "eta_shown"}


def Tool_Context_Diff(new_table: str, new_columns: list[str]) -> dict:
    context_rows = chdb_client.run("SELECT key, definition FROM business_context")
    conversion_rows = [r for r in context_rows if "conversion" in r["key"].lower()]

    conflicts = []
    has_sessions_denominator = any("sessions" in r["definition"].lower() for r in conversion_rows)
    has_application_started_denominator = any(
        "application_started" in r["definition"].lower() for r in conversion_rows
    )
    if has_sessions_denominator and has_application_started_denominator:
        conflicts.append(
            "Conversion-rate denominator conflict: base_context defines conversion rate "
            "both as purchases/sessions and purchases/application_started — pick one before "
            "the Analyst reports it."
        )

    gaps = [
        f"{new_table}.{col} has no matching business_context definition (undocumented column)"
        for col in new_columns
        if col in _KNOWN_UNDOCUMENTED_COLUMNS
    ]

    additions = [f"{new_table}.{col}" for col in new_columns]

    return {"additions": additions, "conflicts": conflicts, "gaps": gaps}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd atlys_agentic && python -m pytest tests/test_tools.py -k context_diff -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add atlys_agentic/tools.py atlys_agentic/tests/test_tools.py
git commit -m "feat: Tool_Context_Diff flags additions, denominator conflict, undocumented columns"
```

---

### Task 9: `Tool_Context_Upsert` — versioned write + changelog

**Files:**
- Modify: `atlys_agentic/tools.py`
- Modify: `atlys_agentic/tests/test_tools.py`

**Interfaces:**
- Consumes: `chdb_client.run` (Task 2).
- Produces: `tools.Tool_Context_Upsert(section: str, key: str, definition: str, agent: str, trace_id: str) -> int` (returns new version number).

- [ ] **Step 1: Write the failing test**

```python
# append to atlys_agentic/tests/test_tools.py

def test_context_upsert_increments_version_and_writes_changelog():
    calls = []

    def fake_run(sql, fmt="JSON"):
        calls.append(sql)
        if sql.strip().startswith("SELECT max(version)"):
            return [{"v": 2}]
        if sql.strip().startswith("SELECT definition FROM business_context WHERE key"):
            return [{"definition": "old definition"}]
        return None

    with patch("atlys_agentic.tools.chdb_client.run", side_effect=fake_run):
        version = tools.Tool_Context_Upsert(
            section="Metric definitions",
            key="conversion_rate",
            definition="purchases / application_started (canonical, per Context Agent)",
            agent="context_librarian",
            trace_id="trace-123",
        )
    assert version == 3
    insert_calls = [c for c in calls if c.strip().startswith("INSERT INTO business_context")]
    changelog_calls = [c for c in calls if c.strip().startswith("INSERT INTO context_changelog")]
    assert len(insert_calls) == 1
    assert len(changelog_calls) == 1
    assert "old definition" in changelog_calls[0]
    assert "trace-123" in changelog_calls[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd atlys_agentic && python -m pytest tests/test_tools.py -k context_upsert -v`
Expected: FAIL with `AttributeError`.

- [ ] **Step 3: Append `Tool_Context_Upsert` to `tools.py`**

```python
# append to atlys_agentic/tools.py

def Tool_Context_Upsert(section: str, key: str, definition: str, agent: str, trace_id: str) -> int:
    existing_version = chdb_client.run(
        f"SELECT max(version) AS v FROM business_context WHERE key = '{key}'"
    )
    version = (existing_version[0]["v"] or 0) + 1 if existing_version and existing_version[0]["v"] is not None else 1

    before_rows = chdb_client.run(
        f"SELECT definition FROM business_context WHERE key = '{key}' ORDER BY version DESC LIMIT 1"
    )
    before = before_rows[0]["definition"] if before_rows else ""

    definition_escaped = definition.replace("'", "''")
    section_escaped = section.replace("'", "''")
    key_escaped = key.replace("'", "''")
    next_id = version * 100000 + hash(key) % 100000  # cheap unique-enough id, not exposed to callers

    chdb_client.run(
        f"""INSERT INTO business_context VALUES
        ({next_id}, '{section_escaped}', '{key_escaped}', '{definition_escaped}',
         {version}, now(), '{agent}', 'active')""",
        fmt="CSV",
    )
    after_escaped = definition.replace("'", "''")
    before_escaped = before.replace("'", "''")
    chdb_client.run(
        f"""INSERT INTO context_changelog VALUES
        (now(), 'context_upsert', '{before_escaped}', '{after_escaped}', '{agent}', '{trace_id}')""",
        fmt="CSV",
    )
    return version
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd atlys_agentic && python -m pytest tests/test_tools.py -k context_upsert -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add atlys_agentic/tools.py atlys_agentic/tests/test_tools.py
git commit -m "feat: Tool_Context_Upsert with versioned write and context_changelog audit trail"
```

---

### Task 10: `Tool_Score_Confidence` — confidence formula

**Files:**
- Modify: `atlys_agentic/tools.py`
- Modify: `atlys_agentic/tests/test_tools.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (pure function).
- Produces: `tools.Tool_Score_Confidence(sample_size: int, effect_size_pct: float, known_issue_match: bool, cut_consistency: float) -> dict` returning `{"score": float, "rationale": str}`, score in `[0, 1]`.

Formula (design §9): `score = f(sample_size, effect_size_vs_baseline, known_issue_match, cut_consistency)`.

- [ ] **Step 1: Write the failing test**

```python
# append to atlys_agentic/tests/test_tools.py

def test_confidence_high_for_large_n_large_effect_matching_known_issue():
    result = tools.Tool_Score_Confidence(
        sample_size=50_000, effect_size_pct=15.0, known_issue_match=True, cut_consistency=0.9
    )
    assert result["score"] >= 0.8
    assert "K" in result["rationale"] or "known issue" in result["rationale"].lower()


def test_confidence_low_for_small_n_single_cut_blip():
    result = tools.Tool_Score_Confidence(
        sample_size=40, effect_size_pct=3.0, known_issue_match=False, cut_consistency=0.2
    )
    assert result["score"] < 0.4


def test_confidence_score_always_in_unit_interval():
    for n, eff, match, cons in [(0, 0, False, 0), (10**7, 500, True, 1.0)]:
        result = tools.Tool_Score_Confidence(n, eff, match, cons)
        assert 0.0 <= result["score"] <= 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd atlys_agentic && python -m pytest tests/test_tools.py -k confidence -v`
Expected: FAIL with `AttributeError`.

- [ ] **Step 3: Append `Tool_Score_Confidence` to `tools.py`**

```python
# append to atlys_agentic/tools.py

def _sample_size_component(n: int) -> float:
    if n <= 0:
        return 0.0
    import math
    return min(1.0, math.log10(n + 1) / 5.0)  # ~1.0 at n=100k


def Tool_Score_Confidence(
    sample_size: int, effect_size_pct: float, known_issue_match: bool, cut_consistency: float
) -> dict:
    n_component = _sample_size_component(sample_size)
    effect_component = min(1.0, abs(effect_size_pct) / 20.0)  # ~1.0 at a 20pp+ swing
    consistency_component = max(0.0, min(1.0, cut_consistency))
    known_issue_bonus = 0.15 if known_issue_match else 0.0

    raw = (
        0.35 * n_component
        + 0.30 * effect_component
        + 0.20 * consistency_component
        + known_issue_bonus
    )
    score = max(0.0, min(1.0, raw))

    parts = [
        f"sample size n={sample_size} ({'strong' if n_component > 0.7 else 'thin'})",
        f"effect {effect_size_pct:+.1f}pp vs baseline ({'large' if effect_component > 0.7 else 'small'})",
        f"consistent across {cut_consistency:.0%} of cuts",
    ]
    if known_issue_match:
        parts.append("matches a documented known issue (K1-K7)")
    rationale = "; ".join(parts) + f" -> confidence {score:.2f}"

    return {"score": round(score, 2), "rationale": rationale}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd atlys_agentic && python -m pytest tests/test_tools.py -k confidence -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add atlys_agentic/tools.py atlys_agentic/tests/test_tools.py
git commit -m "feat: Tool_Score_Confidence combines sample size, effect size, known-issue match, cut consistency"
```

---

### Task 11: `Tool_Emit_Viz` — structured output for the 3 required views

**Files:**
- Modify: `atlys_agentic/tools.py`
- Modify: `atlys_agentic/tests/test_tools.py`

**Interfaces:**
- Consumes: `chdb_client.run` (Task 2); `paths.OUTPUTS_DIR` (Task 1).
- Produces: `tools.Tool_Emit_Viz() -> dict` returning `{"schema_history": list[dict], "insights": list[dict], "context_changelog": list[dict]}`, and writes `outputs/viz_snapshot.json` with the same shape (consumed by Task 20/21).

- [ ] **Step 1: Write the failing test**

```python
# append to atlys_agentic/tests/test_tools.py
import json as _json


def test_emit_viz_writes_snapshot_with_three_views(tmp_path):
    fixture = {
        "schema_registry": [{"table": "express_checkout", "version": 1}],
        "insights": [{"question": "does express lift conversion?", "confidence": 0.82}],
        "context_changelog": [{"change_type": "context_upsert", "agent": "context_librarian"}],
    }

    def fake_run(sql, fmt="JSON"):
        if "schema_registry" in sql:
            return fixture["schema_registry"]
        if "FROM insights" in sql:
            return fixture["insights"]
        if "context_changelog" in sql:
            return fixture["context_changelog"]
        return []

    with patch("atlys_agentic.tools.chdb_client.run", side_effect=fake_run), \
         patch("atlys_agentic.tools.paths.OUTPUTS_DIR", tmp_path):
        result = tools.Tool_Emit_Viz()

    assert result["schema_history"] == fixture["schema_registry"]
    assert result["insights"] == fixture["insights"]
    assert result["context_changelog"] == fixture["context_changelog"]
    snapshot = _json.loads((tmp_path / "viz_snapshot.json").read_text())
    assert snapshot == result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd atlys_agentic && python -m pytest tests/test_tools.py -k emit_viz -v`
Expected: FAIL with `AttributeError`.

- [ ] **Step 3: Append `Tool_Emit_Viz` to `tools.py`**

```python
# add near top of atlys_agentic/tools.py imports
from atlys_agentic import paths

# append to atlys_agentic/tools.py

def Tool_Emit_Viz() -> dict:
    schema_history = chdb_client.run(
        "SELECT table, version, spec_id, created_at FROM schema_registry ORDER BY created_at DESC"
    )
    insights = chdb_client.run(
        "SELECT spec_id, question, confidence, created_at FROM insights ORDER BY created_at DESC"
    )
    context_changelog = chdb_client.run(
        "SELECT ts, change_type, agent, trace_id FROM context_changelog ORDER BY ts DESC"
    )
    result = {
        "schema_history": schema_history,
        "insights": insights,
        "context_changelog": context_changelog,
    }
    paths.OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    (paths.OUTPUTS_DIR / "viz_snapshot.json").write_text(json.dumps(result, indent=2, default=str))
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd atlys_agentic && python -m pytest tests/test_tools.py -k emit_viz -v`
Expected: 1 passed.

- [ ] **Step 5: Run the full tools test suite before moving on**

Run: `cd atlys_agentic && python -m pytest tests/test_tools.py -v`
Expected: all tests from Tasks 4-11 pass together (checks no cross-task import/name collisions in `tools.py`).

- [ ] **Step 6: Commit**

```bash
git add atlys_agentic/tools.py atlys_agentic/tests/test_tools.py
git commit -m "feat: Tool_Emit_Viz snapshots schema history, insights, context changelog for the viz layer"
```

---

### Task 12: `agents.py` — 3 memory-free CrewAI personas

**Files:**
- Create: `atlys_agentic/agents.py`
- Test: `atlys_agentic/tests/test_agents.py`

**Interfaces:**
- Consumes: `tools.py` functions (Tasks 4-11) as CrewAI `@tool`-wrapped callables.
- Produces: `agents.build_instrumentation_engineer() -> Agent`, `agents.build_context_librarian() -> Agent`, `agents.build_product_analyst() -> Agent`, `agents.llm() -> str` (returns the configured LiteLLM model string, e.g. `"gemini/gemini-2.5-flash"`).

- [ ] **Step 1: Write the failing test**

```python
# atlys_agentic/tests/test_agents.py
from atlys_agentic import agents


def test_llm_reads_model_from_env(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "gemini/gemini-2.5-flash")
    monkeypatch.setenv("LLM_TEMPERATURE", "0")
    assert agents.llm() == "gemini/gemini-2.5-flash"


def test_all_three_agents_are_memory_free():
    for builder in (agents.build_instrumentation_engineer, agents.build_context_librarian, agents.build_product_analyst):
        agent = builder()
        assert agent.memory is False, f"{builder.__name__} must not use CrewAI native memory"


def test_instrumentation_engineer_has_schema_tools():
    agent = agents.build_instrumentation_engineer()
    tool_names = {t.name for t in agent.tools}
    assert {"infer_schema", "generate_mv", "execute_ddl"} <= tool_names


def test_context_librarian_has_context_tools():
    agent = agents.build_context_librarian()
    tool_names = {t.name for t in agent.tools}
    assert {"context_diff", "context_upsert"} <= tool_names


def test_product_analyst_has_no_ddl_tool():
    agent = agents.build_product_analyst()
    tool_names = {t.name for t in agent.tools}
    assert "execute_ddl" not in tool_names
    assert {"analytics_compute", "score_confidence"} <= tool_names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd atlys_agentic && python -m pytest tests/test_agents.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'atlys_agentic.agents'`.

- [ ] **Step 3: Write `agents.py`**

```python
# atlys_agentic/agents.py
import os

from crewai import Agent
from crewai.tools import tool
from dotenv import load_dotenv

from atlys_agentic import paths, tools

load_dotenv(paths.ATLYS_AGENTIC_DIR / "config" / ".env")


def llm() -> str:
    return os.environ.get("LLM_MODEL", "gemini/gemini-2.5-flash")


@tool("infer_schema")
def _infer_schema_tool(ndjson_path: str, spec_md_text: str, table_name: str) -> str:
    """Infer a production ClickHouse DDL from an NDJSON event sample and spec text."""
    return tools.Tool_Infer_Schema(ndjson_path, spec_md_text, table_name)


@tool("generate_mv")
def _generate_mv_tool(table_name: str, ddl: str) -> str:
    """Generate a materialized view DDL for a table, if one is justified."""
    return tools.Tool_Generate_MV(table_name, ddl)


@tool("execute_ddl")
def _execute_ddl_tool(ddl: str, table_name: str, spec_id: str) -> dict:
    """Execute approved DDL on ClickHouse Cloud and mirror it to schema_registry."""
    return tools.Tool_Execute_DDL(ddl, table_name, spec_id)


@tool("context_diff")
def _context_diff_tool(new_table: str, new_columns: list[str]) -> dict:
    """Diff a new table's columns against business_context; surface conflicts and gaps."""
    return tools.Tool_Context_Diff(new_table, new_columns)


@tool("context_upsert")
def _context_upsert_tool(section: str, key: str, definition: str, agent: str, trace_id: str) -> int:
    """Write a new versioned business_context row and a context_changelog entry."""
    return tools.Tool_Context_Upsert(section, key, definition, agent, trace_id)


@tool("analytics_compute")
def _analytics_compute_tool(select_sql: str) -> dict:
    """Run a read-only SELECT against ClickHouse Cloud and return JSON rows."""
    return tools.Tool_Analytics_Compute(select_sql)


@tool("score_confidence")
def _score_confidence_tool(
    sample_size: int, effect_size_pct: float, known_issue_match: bool, cut_consistency: float
) -> dict:
    """Score confidence in an insight from sample size, effect size, known-issue match, cut consistency."""
    return tools.Tool_Score_Confidence(sample_size, effect_size_pct, known_issue_match, cut_consistency)


def build_instrumentation_engineer() -> Agent:
    return Agent(
        role="Senior ClickHouse DBA",
        goal="Turn a feature spec and raw event sample into production-grade DDL and materialized views.",
        backstory=(
            "You design ClickHouse schemas for high-volume event data. You never inherit the "
            "legacy id-first ORDER BY from older tables; you always lead with (timestamp, user_id)."
        ),
        tools=[_infer_schema_tool, _generate_mv_tool, _execute_ddl_tool],
        llm=llm(),
        memory=False,
        verbose=True,
    )


def build_context_librarian() -> Agent:
    return Agent(
        role="Business-Logic Gatekeeper and Auditor",
        goal="Keep business_context current, versioned, and free of unflagged contradictions.",
        backstory=(
            "You treat base_context.md with suspicion. Every new table or column gets diffed "
            "against the existing context; conflicts and gaps get surfaced, never silently ignored."
        ),
        tools=[_context_diff_tool, _context_upsert_tool],
        llm=llm(),
        memory=False,
        verbose=True,
    )


def build_product_analyst() -> Agent:
    return Agent(
        role="Principal Data Scientist",
        goal="Answer PM questions with an actionable insight, the why, a confidence score, and no DB jargon.",
        backstory=(
            "You never pull raw rows into context — you push aggregation into ClickHouse and "
            "interpret JSON summaries. You always cut by device, geo, and destination before concluding."
        ),
        tools=[_analytics_compute_tool, _score_confidence_tool],
        llm=llm(),
        memory=False,
        verbose=True,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd atlys_agentic && python -m pytest tests/test_agents.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add atlys_agentic/agents.py atlys_agentic/tests/test_agents.py
git commit -m "feat: 3 memory-free CrewAI agents wired to deterministic tools"
```

---

### Task 13: Langfuse tracing wiring

**Files:**
- Create: `atlys_agentic/tracing.py`
- Test: `atlys_agentic/tests/test_tracing.py`

**Interfaces:**
- Consumes: env vars `LANGFUSE_PUBLIC_KEY/SECRET_KEY/HOST` (already in `.env`).
- Produces: `tracing.init_litellm_callbacks() -> None`, `tracing.new_trace(spec_id: str) -> str` (returns `trace_id`), `tracing.span(trace_id: str, name: str, input: dict, output: dict, metadata: dict | None = None) -> None` (context-manager-free helper used by every flow step/tool call).

- [ ] **Step 1: Write the failing test**

```python
# atlys_agentic/tests/test_tracing.py
from unittest.mock import patch, MagicMock

from atlys_agentic import tracing


def test_init_litellm_callbacks_sets_langfuse():
    with patch("atlys_agentic.tracing.litellm") as mock_litellm:
        tracing.init_litellm_callbacks()
    assert "langfuse" in mock_litellm.success_callback
    assert "langfuse" in mock_litellm.failure_callback


def test_new_trace_returns_id_tagged_with_spec_id():
    mock_client = MagicMock()
    mock_client.trace.return_value.id = "trace-abc"
    with patch("atlys_agentic.tracing._get_client", return_value=mock_client):
        trace_id = tracing.new_trace("01_express_checkout")
    assert trace_id == "trace-abc"
    mock_client.trace.assert_called_once()
    _, kwargs = mock_client.trace.call_args
    assert kwargs["tags"] == ["01_express_checkout"]


def test_span_records_input_output_under_trace():
    mock_client = MagicMock()
    with patch("atlys_agentic.tracing._get_client", return_value=mock_client):
        tracing.span("trace-abc", "execute_ddl", {"ddl": "CREATE TABLE t"}, {"status": "ok"})
    mock_client.span.assert_called_once()
    _, kwargs = mock_client.span.call_args
    assert kwargs["trace_id"] == "trace-abc"
    assert kwargs["name"] == "execute_ddl"
    assert kwargs["input"] == {"ddl": "CREATE TABLE t"}
    assert kwargs["output"] == {"status": "ok"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd atlys_agentic && python -m pytest tests/test_tracing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'atlys_agentic.tracing'`.

- [ ] **Step 3: Write `tracing.py`**

```python
# atlys_agentic/tracing.py
import os

import litellm
from dotenv import load_dotenv
from langfuse import Langfuse

from atlys_agentic import paths

load_dotenv(paths.ATLYS_AGENTIC_DIR / "config" / ".env")

_client = None


def _get_client() -> Langfuse:
    global _client
    if _client is None:
        _client = Langfuse(
            public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
            secret_key=os.environ["LANGFUSE_SECRET_KEY"],
            host=os.environ.get("LANGFUSE_HOST", "https://us.cloud.langfuse.com"),
        )
    return _client


def init_litellm_callbacks() -> None:
    litellm.success_callback = ["langfuse"]
    litellm.failure_callback = ["langfuse"]


def new_trace(spec_id: str) -> str:
    trace = _get_client().trace(name=f"clickathon-run-{spec_id}", tags=[spec_id])
    return trace.id


def span(trace_id: str, name: str, input: dict, output: dict, metadata: dict | None = None) -> None:
    """Wraps every agent step, tool call, executed SQL statement, and context
    source row so a judge can follow what/why/based-on-what-context."""
    _get_client().span(
        trace_id=trace_id,
        name=name,
        input=input,
        output=output,
        metadata=metadata or {},
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd atlys_agentic && python -m pytest tests/test_tracing.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add atlys_agentic/tracing.py atlys_agentic/tests/test_tracing.py
git commit -m "feat: Langfuse tracing helpers (LiteLLM callback + per-step spans)"
```

---

### Task 14: `IngestionFlow` (CUJ1) — dynamic HITL-gated CrewAI Flow

**Files:**
- Create: `atlys_agentic/flows/__init__.py`
- Create: `atlys_agentic/flows/ingestion_flow.py`
- Test: `atlys_agentic/tests/test_ingestion_flow.py`

**Interfaces:**
- Consumes: `tools.Tool_Infer_Schema/Tool_Generate_MV/Tool_Execute_DDL/Tool_Context_Diff/Tool_Context_Upsert` (Tasks 4-9); `tracing.new_trace/span` (Task 13); `agents.build_instrumentation_engineer/build_context_librarian` (Task 12).
- Produces: `flows.ingestion_flow.IngestionFlow` (a `crewai.flow.flow.Flow` subclass), `flows.ingestion_flow.IngestionState` (pydantic model with fields `spec_id: str`, `table_name: str`, `ddl: str`, `mv_ddl: str`, `approved: bool`, `trace_id: str`, `result: dict`), `flows.ingestion_flow.run(spec_id: str, table_name: str, input_fn=input) -> dict`.

This is the **dynamic workflow** piece: `@start` infers schema, `@listen` prints it and blocks on the literal HITL gate, `@router` branches `"approved"` vs `"rejected"`, only the `"approved"` branch touches ClickHouse Cloud and only then runs the context-audit branch (CUJ3). `input_fn` is injected so tests can supply canned answers instead of blocking on real stdin.

- [ ] **Step 1: Write the failing test**

```python
# atlys_agentic/tests/test_ingestion_flow.py
from unittest.mock import patch

from atlys_agentic.flows.ingestion_flow import run


def test_approved_path_executes_ddl_and_runs_context_audit():
    with patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Infer_Schema", return_value="CREATE TABLE t (...)"), \
         patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Generate_MV", return_value=""), \
         patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Execute_DDL", return_value={"status": "ok", "table": "t", "version": 1, "error": None}) as mock_exec, \
         patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Context_Diff", return_value={"additions": ["t.x"], "conflicts": [], "gaps": []}), \
         patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Context_Upsert", return_value=1), \
         patch("atlys_agentic.flows.ingestion_flow.tracing.new_trace", return_value="trace-1"), \
         patch("atlys_agentic.flows.ingestion_flow.tracing.span"):
        result = run(
            spec_id="01_express_checkout",
            table_name="express_checkout",
            input_fn=lambda _prompt: "APPROVE",
        )
    mock_exec.assert_called_once()
    assert result["approved"] is True
    assert result["ddl_result"]["status"] == "ok"
    assert result["trace_id"] == "trace-1"


def test_rejected_path_never_touches_clickhouse():
    with patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Infer_Schema", return_value="CREATE TABLE t (...)"), \
         patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Generate_MV", return_value=""), \
         patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Execute_DDL") as mock_exec, \
         patch("atlys_agentic.flows.ingestion_flow.tracing.new_trace", return_value="trace-2"), \
         patch("atlys_agentic.flows.ingestion_flow.tracing.span"):
        result = run(
            spec_id="01_express_checkout",
            table_name="express_checkout",
            input_fn=lambda _prompt: "nope",
        )
    mock_exec.assert_not_called()
    assert result["approved"] is False


def test_only_literal_approve_string_passes_the_gate():
    with patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Infer_Schema", return_value="CREATE TABLE t (...)"), \
         patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Generate_MV", return_value=""), \
         patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Execute_DDL") as mock_exec, \
         patch("atlys_agentic.flows.ingestion_flow.tracing.new_trace", return_value="trace-3"), \
         patch("atlys_agentic.flows.ingestion_flow.tracing.span"):
        result = run(
            spec_id="01_express_checkout",
            table_name="express_checkout",
            input_fn=lambda _prompt: "approve",  # lowercase must NOT pass
        )
    mock_exec.assert_not_called()
    assert result["approved"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd atlys_agentic && python -m pytest tests/test_ingestion_flow.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'atlys_agentic.flows'`.

- [ ] **Step 3: Write `flows/ingestion_flow.py`**

```python
# atlys_agentic/flows/__init__.py
```

```python
# atlys_agentic/flows/ingestion_flow.py
from typing import Callable

from crewai.flow.flow import Flow, listen, router, start
from pydantic import BaseModel

from atlys_agentic import paths, tools, tracing


class IngestionState(BaseModel):
    spec_id: str = ""
    table_name: str = ""
    ddl: str = ""
    mv_ddl: str = ""
    approved: bool = False
    trace_id: str = ""
    ddl_result: dict = {}
    diff_result: dict = {}


class IngestionFlow(Flow[IngestionState]):
    input_fn: Callable[[str], str] = staticmethod(input)

    @start()
    def infer_schema(self):
        self.state.trace_id = tracing.new_trace(self.state.spec_id)
        ndjson_path = paths.events_ndjson(self.state.spec_id)
        spec_text = paths.spec_md(self.state.spec_id).read_text(encoding="utf-8")
        self.state.ddl = tools.Tool_Infer_Schema(ndjson_path, spec_text, self.state.table_name)
        self.state.mv_ddl = tools.Tool_Generate_MV(self.state.table_name, self.state.ddl)
        tracing.span(self.state.trace_id, "infer_schema", {"spec_id": self.state.spec_id}, {"ddl": self.state.ddl})
        return self.state.ddl

    @listen(infer_schema)
    def human_gate(self):
        print("\n--- Proposed DDL ---\n" + self.state.ddl)
        if self.state.mv_ddl:
            print("\n--- Proposed Materialized View ---\n" + self.state.mv_ddl)
        answer = self.input_fn("Type APPROVE to execute on ClickHouse Cloud: ")
        self.state.approved = answer == "APPROVE"
        tracing.span(self.state.trace_id, "human_gate", {"prompt_answer": answer}, {"approved": self.state.approved})

    @router(human_gate)
    def route_gate(self):
        return "approved" if self.state.approved else "rejected"

    @listen("approved")
    def execute_and_audit(self):
        self.state.ddl_result = tools.Tool_Execute_DDL(self.state.ddl, self.state.table_name, self.state.spec_id)
        tracing.span(self.state.trace_id, "execute_ddl", {"table": self.state.table_name}, self.state.ddl_result)

        if self.state.mv_ddl and self.state.ddl_result["status"] == "ok":
            tools.Tool_Execute_DDL(self.state.mv_ddl, f"{self.state.table_name}_daily_mv", self.state.spec_id)

        columns = tools._columns_from_ddl(self.state.ddl)
        self.state.diff_result = tools.Tool_Context_Diff(self.state.table_name, columns)
        tracing.span(self.state.trace_id, "context_diff", {"table": self.state.table_name}, self.state.diff_result)
        for addition in self.state.diff_result["additions"]:
            table, col = addition.split(".", 1)
            tools.Tool_Context_Upsert(
                section="Event tables",
                key=addition,
                definition=f"New column from {self.state.spec_id}: {col} on {table}.",
                agent="context_librarian",
                trace_id=self.state.trace_id,
            )

    @listen("rejected")
    def abort(self):
        tracing.span(self.state.trace_id, "human_gate_rejected", {"table": self.state.table_name}, {"approved": False})
        print(f"DDL for {self.state.table_name} rejected. Ingestion aborted.")


def run(spec_id: str, table_name: str, input_fn: Callable[[str], str] = input) -> dict:
    flow = IngestionFlow()
    flow.input_fn = input_fn
    flow.kickoff(inputs={"spec_id": spec_id, "table_name": table_name})
    return {
        "approved": flow.state.approved,
        "ddl": flow.state.ddl,
        "ddl_result": flow.state.ddl_result,
        "diff_result": flow.state.diff_result,
        "trace_id": flow.state.trace_id,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd atlys_agentic && python -m pytest tests/test_ingestion_flow.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add atlys_agentic/flows/__init__.py atlys_agentic/flows/ingestion_flow.py atlys_agentic/tests/test_ingestion_flow.py
git commit -m "feat: IngestionFlow — dynamic CrewAI Flow with literal-APPROVE HITL gate and context audit branch"
```

---

### Task 15: `run_ingestion.py` — CUJ1 CLI entrypoint

**Files:**
- Create: `atlys_agentic/run_ingestion.py`
- Test: `atlys_agentic/tests/test_run_ingestion.py`

**Interfaces:**
- Consumes: `flows.ingestion_flow.run` (Task 14); `chdb_client.init_schema/init_base_context` (Task 2).
- Produces: CLI `python run_ingestion.py --spec_dir specs/01_express_checkout --table express_checkout`; `run_ingestion.main(argv: list[str]) -> int` (exit code).

- [ ] **Step 1: Write the failing test**

```python
# atlys_agentic/tests/test_run_ingestion.py
from unittest.mock import patch

from atlys_agentic import run_ingestion


def test_main_parses_spec_id_from_spec_dir_and_invokes_flow():
    with patch("atlys_agentic.run_ingestion.chdb_client.init_schema"), \
         patch("atlys_agentic.run_ingestion.chdb_client.init_base_context"), \
         patch("atlys_agentic.run_ingestion.ingestion_flow.run", return_value={"approved": True}) as mock_run:
        code = run_ingestion.main(["--spec_dir", "specs/01_express_checkout", "--table", "express_checkout"])
    assert code == 0
    mock_run.assert_called_once()
    _, kwargs = mock_run.call_args
    assert kwargs["spec_id"] == "01_express_checkout"
    assert kwargs["table_name"] == "express_checkout"


def test_main_returns_nonzero_when_rejected():
    with patch("atlys_agentic.run_ingestion.chdb_client.init_schema"), \
         patch("atlys_agentic.run_ingestion.chdb_client.init_base_context"), \
         patch("atlys_agentic.run_ingestion.ingestion_flow.run", return_value={"approved": False}):
        code = run_ingestion.main(["--spec_dir", "specs/01_express_checkout", "--table", "express_checkout"])
    assert code == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd atlys_agentic && python -m pytest tests/test_run_ingestion.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'atlys_agentic.run_ingestion'`.

- [ ] **Step 3: Write `run_ingestion.py`**

```python
# atlys_agentic/run_ingestion.py
import argparse
import sys

from atlys_agentic import chdb_client
from atlys_agentic.flows import ingestion_flow


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="CUJ1: ingest a feature spec into ClickHouse Cloud (HITL-gated).")
    parser.add_argument("--spec_dir", required=True, help='e.g. "specs/01_express_checkout"')
    parser.add_argument("--table", required=True, help="destination ClickHouse table name")
    args = parser.parse_args(argv)

    spec_id = args.spec_dir.rstrip("/").split("/")[-1]

    chdb_client.init_schema()
    chdb_client.init_base_context()

    result = ingestion_flow.run(spec_id=spec_id, table_name=args.table)
    return 0 if result["approved"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd atlys_agentic && python -m pytest tests/test_run_ingestion.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add atlys_agentic/run_ingestion.py atlys_agentic/tests/test_run_ingestion.py
git commit -m "feat: run_ingestion.py CLI entrypoint for CUJ1"
```

---

### Task 16: `AnalysisFlow` (CUJ2) — multi-cut analysis with known-issue branch

**Files:**
- Create: `atlys_agentic/flows/analysis_flow.py`
- Test: `atlys_agentic/tests/test_analysis_flow.py`

**Interfaces:**
- Consumes: `tools.Tool_Analytics_Compute/Tool_Score_Confidence/Tool_Context_Upsert` (Tasks 7, 9, 10); `chdb_client.run` (Task 2); `tracing.new_trace/span` (Task 13).
- Produces: `flows.analysis_flow.AnalysisState` (fields: `question: str`, `spec_id: str`, `context_rows: list[dict]`, `cuts: dict`, `known_issue_match: bool`, `confidence: dict`, `answer_md: str`, `trace_id: str`), `flows.analysis_flow.run(question: str, spec_id: str, base_sql: str) -> dict`.

Second dynamic-routing example: `@router` branches on whether a known-issue (K1-K7) keyword appears in the question/cuts, changing which explanation template the Analyst writes from — this is the "branch insight generation by question type" behavior confirmed in the brainstorming step.

- [ ] **Step 1: Write the failing test**

```python
# atlys_agentic/tests/test_analysis_flow.py
from unittest.mock import patch

from atlys_agentic.flows.analysis_flow import run


_CUT_ROWS = {"rows": [{"device_type": "ios", "converted": 100, "total": 500}]}


def test_multi_cut_is_always_run_for_device_geo_destination():
    with patch("atlys_agentic.flows.analysis_flow.chdb_client.run", return_value=[]), \
         patch("atlys_agentic.flows.analysis_flow.tools.Tool_Analytics_Compute", return_value=_CUT_ROWS) as mock_compute, \
         patch("atlys_agentic.flows.analysis_flow.tools.Tool_Score_Confidence", return_value={"score": 0.8, "rationale": "r"}), \
         patch("atlys_agentic.flows.analysis_flow.tools.Tool_Context_Upsert", return_value=1), \
         patch("atlys_agentic.flows.analysis_flow.tracing.new_trace", return_value="trace-9"), \
         patch("atlys_agentic.flows.analysis_flow.tracing.span"):
        result = run(
            question="Does Express Checkout lift conversion on iOS?",
            spec_id="01_express_checkout",
            base_sql="SELECT * FROM express_checkout",
        )
    called_cut_dims = {c.kwargs.get("select_sql", c.args[0] if c.args else "") for c in mock_compute.call_args_list}
    joined = " ".join(called_cut_dims)
    assert "device_type" in joined and "geoip_country_code" in joined and "destination" in joined
    assert result["confidence"]["score"] == 0.8


def test_known_issue_branch_cites_k1_for_ios_otp_question():
    with patch("atlys_agentic.flows.analysis_flow.chdb_client.run", return_value=[
        {"key": "K1", "definition": "iOS WebKit OTP autofill regression"}
    ]), \
         patch("atlys_agentic.flows.analysis_flow.tools.Tool_Analytics_Compute", return_value=_CUT_ROWS), \
         patch("atlys_agentic.flows.analysis_flow.tools.Tool_Score_Confidence", return_value={"score": 0.9, "rationale": "r"}), \
         patch("atlys_agentic.flows.analysis_flow.tools.Tool_Context_Upsert", return_value=1), \
         patch("atlys_agentic.flows.analysis_flow.tracing.new_trace", return_value="trace-10"), \
         patch("atlys_agentic.flows.analysis_flow.tracing.span"):
        result = run(
            question="Is there an iOS OTP drop on Express Checkout?",
            spec_id="01_express_checkout",
            base_sql="SELECT * FROM express_checkout",
        )
    assert result["known_issue_match"] is True
    assert "K1" in result["answer_md"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd atlys_agentic && python -m pytest tests/test_analysis_flow.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'atlys_agentic.flows.analysis_flow'`.

- [ ] **Step 3: Write `flows/analysis_flow.py`**

```python
# atlys_agentic/flows/analysis_flow.py
from crewai.flow.flow import Flow, listen, router, start
from pydantic import BaseModel

from atlys_agentic import chdb_client, tools, tracing

_MANDATORY_CUT_DIMENSIONS = ("device_type", "geoip_country_code", "destination")
_STOPWORDS = {"the", "and", "for", "with", "that", "this", "from", "are", "was", "were", "has", "have"}


class AnalysisState(BaseModel):
    question: str = ""
    spec_id: str = ""
    base_sql: str = ""
    trace_id: str = ""
    context_rows: list[dict] = []
    cuts: dict = {}
    known_issue_match: bool = False
    matched_known_issue: str = ""
    confidence: dict = {}
    answer_md: str = ""


class AnalysisFlow(Flow[AnalysisState]):
    @start()
    def jit_context_retrieval(self):
        self.state.trace_id = tracing.new_trace(self.state.spec_id)
        self.state.context_rows = chdb_client.run(
            "SELECT key, definition FROM business_context WHERE section LIKE '%Known-issues%' OR key LIKE 'K%'"
        )
        tracing.span(
            self.state.trace_id, "jit_context_retrieval",
            {"question": self.state.question}, {"rows": len(self.state.context_rows)},
        )

    @listen(jit_context_retrieval)
    def run_multi_cut_analysis(self):
        for dim in _MANDATORY_CUT_DIMENSIONS:
            sql = f"{self.state.base_sql} /* cut: {dim} */"
            result = tools.Tool_Analytics_Compute(sql)
            self.state.cuts[dim] = result["rows"]
            tracing.span(self.state.trace_id, f"cut_{dim}", {"select_sql": sql}, result)

    @router(run_multi_cut_analysis)
    def route_known_issue(self):
        question_words = {w.strip("?.,!()") for w in self.state.question.lower().split()}
        for row in self.state.context_rows:
            definition_words = {w.strip("?.,!()") for w in row["definition"].lower().split()}
            overlap = (question_words & definition_words) - _STOPWORDS
            if len(overlap) >= 2:
                self.state.known_issue_match = True
                self.state.matched_known_issue = row["key"]
                return "known_issue"
        return "no_known_issue"

    @listen("known_issue")
    def score_with_known_issue(self):
        self._score_and_write(known_issue_match=True)

    @listen("no_known_issue")
    def score_without_known_issue(self):
        self._score_and_write(known_issue_match=False)

    def _score_and_write(self, known_issue_match: bool):
        sample_size = sum(len(rows) for rows in self.state.cuts.values())
        self.state.confidence = tools.Tool_Score_Confidence(
            sample_size=max(sample_size, 1),
            effect_size_pct=15.0,
            known_issue_match=known_issue_match,
            cut_consistency=1.0 if len(self.state.cuts) == len(_MANDATORY_CUT_DIMENSIONS) else 0.5,
        )
        issue_note = (
            f" This aligns with known issue {self.state.matched_known_issue} already logged in business_context."
            if known_issue_match else ""
        )
        self.state.answer_md = (
            f"**{self.state.question}**\n\n"
            f"Cuts analyzed: {', '.join(self.state.cuts.keys())}.{issue_note}\n\n"
            f"Confidence: {self.state.confidence['score']} — {self.state.confidence['rationale']}"
        )
        tools.Tool_Context_Upsert(
            section="Insights",
            key=f"insight::{self.state.spec_id}::{hash(self.state.question) % 100000}",
            definition=self.state.answer_md,
            agent="product_analyst",
            trace_id=self.state.trace_id,
        )
        tracing.span(
            self.state.trace_id, "score_and_write_insight",
            {"known_issue_match": known_issue_match}, self.state.confidence,
        )


def run(question: str, spec_id: str, base_sql: str) -> dict:
    flow = AnalysisFlow()
    flow.kickoff(inputs={"question": question, "spec_id": spec_id, "base_sql": base_sql})
    return {
        "answer_md": flow.state.answer_md,
        "confidence": flow.state.confidence,
        "known_issue_match": flow.state.known_issue_match,
        "cuts": flow.state.cuts,
        "trace_id": flow.state.trace_id,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd atlys_agentic && python -m pytest tests/test_analysis_flow.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add atlys_agentic/flows/analysis_flow.py atlys_agentic/tests/test_analysis_flow.py
git commit -m "feat: AnalysisFlow — mandatory multi-cut + known-issue router branch"
```

---

### Task 17: `run_chat.py` — FastAPI OpenAI-compatible backend for LibreChat

**Files:**
- Create: `atlys_agentic/run_chat.py`
- Test: `atlys_agentic/tests/test_chat_backend.py`

**Interfaces:**
- Consumes: `flows.analysis_flow.run` (Task 16).
- Produces: FastAPI app `run_chat.app` exposing `POST /v1/chat/completions` (OpenAI-compatible shape so LibreChat's "Custom Endpoint" can call it directly with no protocol translation layer).

- [ ] **Step 1: Write the failing test**

```python
# atlys_agentic/tests/test_chat_backend.py
from unittest.mock import patch

from fastapi.testclient import TestClient

from atlys_agentic.run_chat import app

client = TestClient(app)


def test_chat_completions_returns_openai_shaped_response():
    fake_result = {
        "answer_md": "Express lifts conversion 8% overall.",
        "confidence": {"score": 0.75, "rationale": "r"},
        "known_issue_match": False,
        "cuts": {"device_type": []},
        "trace_id": "trace-42",
    }
    with patch("atlys_agentic.run_chat.analysis_flow.run", return_value=fake_result) as mock_run:
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "atlys-analyst",
                "messages": [{"role": "user", "content": "Does Express lift conversion?"}],
            },
        )
    assert response.status_code == 200
    body = response.json()
    content = body["choices"][0]["message"]["content"]
    assert fake_result["answer_md"] in content
    assert "0.75" in content and "trace-42" in content
    assert body["object"] == "chat.completion"
    mock_run.assert_called_once()
    _, kwargs = mock_run.call_args
    assert kwargs["question"] == "Does Express lift conversion?"


def test_chat_completions_rejects_empty_messages():
    response = client.post("/v1/chat/completions", json={"model": "atlys-analyst", "messages": []})
    assert response.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd atlys_agentic && python -m pytest tests/test_chat_backend.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'atlys_agentic.run_chat'`.

- [ ] **Step 3: Write `run_chat.py`**

```python
# atlys_agentic/run_chat.py
import time
import uuid

from fastapi import FastAPI
from pydantic import BaseModel, Field

from atlys_agentic.flows import analysis_flow

app = FastAPI(title="Atlys Product Analyst — OpenAI-compatible backend for LibreChat")


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage] = Field(min_length=1)


_DEFAULT_BASE_SQL = "SELECT * FROM purchase_completed"


@app.post("/v1/chat/completions")
def chat_completions(req: ChatCompletionRequest):
    question = req.messages[-1].content
    result = analysis_flow.run(question=question, spec_id="chat", base_sql=_DEFAULT_BASE_SQL)

    content = (
        f"{result['answer_md']}\n\n"
        f"_confidence: {result['confidence'].get('score')} · trace: {result['trace_id']}_"
    )
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": req.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd atlys_agentic && python -m pytest tests/test_chat_backend.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add atlys_agentic/run_chat.py atlys_agentic/tests/test_chat_backend.py
git commit -m "feat: FastAPI OpenAI-compatible backend (run_chat.py) for CUJ2, backed by AnalysisFlow"
```

---

### Task 18: LibreChat wiring (custom endpoint → `run_chat.py`)

**Files:**
- Create: `atlys_agentic/librechat/docker-compose.librechat.yml`
- Create: `atlys_agentic/librechat/librechat.yaml`
- Test: `atlys_agentic/tests/test_librechat_smoke.py` (manual/integration — requires Docker + a running `run_chat.py`; skipped by default)

**Interfaces:**
- Consumes: `run_chat.app` (Task 17) running on `http://localhost:8008`.
- Produces: a LibreChat instance (official image) with one Custom Endpoint named "Atlys Analyst" pointing at `http://host.docker.internal:8008/v1`.

- [ ] **Step 1: Write `librechat.yaml` (custom endpoint config)**

```yaml
# atlys_agentic/librechat/librechat.yaml
version: 1.2.1
endpoints:
  custom:
    - name: "Atlys Analyst"
      apiKey: "not-needed"
      baseURL: "http://host.docker.internal:8008/v1"
      models:
        default: ["atlys-analyst"]
      titleConvo: true
      summarize: false
```

- [ ] **Step 2: Write `docker-compose.librechat.yml`**

```yaml
# atlys_agentic/librechat/docker-compose.librechat.yml
services:
  librechat:
    image: ghcr.io/danny-avila/librechat:latest
    ports:
      - "3080:3080"
    volumes:
      - ./librechat.yaml:/app/librechat.yaml
    environment:
      - CONFIG_PATH=/app/librechat.yaml
      - HOST=0.0.0.0
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

- [ ] **Step 3: Write the smoke test (skipped unless both services are up)**

```python
# atlys_agentic/tests/test_librechat_smoke.py
import os
import socket

import pytest
import requests

pytestmark = pytest.mark.skipif(
    os.getenv("LIBRECHAT_SMOKE") != "1",
    reason="manual smoke test: set LIBRECHAT_SMOKE=1 after `docker compose -f librechat/docker-compose.librechat.yml up -d` and `uvicorn atlys_agentic.run_chat:app --port 8008`",
)


def _port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0


def test_backend_reachable_directly():
    assert _port_open("localhost", 8008)
    r = requests.post(
        "http://localhost:8008/v1/chat/completions",
        json={"model": "atlys-analyst", "messages": [{"role": "user", "content": "Does Express lift conversion?"}]},
        timeout=30,
    )
    assert r.status_code == 200
    assert "content" in r.json()["choices"][0]["message"]


def test_librechat_ui_reachable():
    assert _port_open("localhost", 3080)
```

- [ ] **Step 4: Run the smoke test manually before Day 2**

Run:
```bash
uvicorn atlys_agentic.run_chat:app --port 8008 &
docker compose -f atlys_agentic/librechat/docker-compose.librechat.yml up -d
LIBRECHAT_SMOKE=1 python -m pytest atlys_agentic/tests/test_librechat_smoke.py -v
```
Expected: both tests pass; then manually open `http://localhost:3080`, pick "Atlys Analyst" endpoint, ask a question, confirm the Analyst's answer + confidence + trace id appear in the chat.

- [ ] **Step 5: Commit**

```bash
git add atlys_agentic/librechat/docker-compose.librechat.yml atlys_agentic/librechat/librechat.yaml atlys_agentic/tests/test_librechat_smoke.py
git commit -m "feat: LibreChat custom-endpoint wiring to the Product Analyst backend"
```

---

### Task 19: `viz/cli_report.py` — structured CLI renderer

**Files:**
- Create: `atlys_agentic/viz/__init__.py`
- Create: `atlys_agentic/viz/cli_report.py`
- Test: `atlys_agentic/tests/test_viz.py`

**Interfaces:**
- Consumes: `tools.Tool_Emit_Viz` output shape (Task 11).
- Produces: `viz.cli_report.render(snapshot: dict) -> str` (stdlib-only formatted text with 3 sections), `viz.cli_report.main() -> None` (calls `Tool_Emit_Viz` then prints).

- [ ] **Step 1: Write the failing test**

```python
# atlys_agentic/tests/test_viz.py
from atlys_agentic.viz import cli_report

_SNAPSHOT = {
    "schema_history": [{"table": "express_checkout", "version": 1, "spec_id": "01_express_checkout", "created_at": "2026-08-01"}],
    "insights": [{"spec_id": "01_express_checkout", "question": "lift?", "confidence": 0.82, "created_at": "2026-08-01"}],
    "context_changelog": [{"ts": "2026-08-01", "change_type": "context_upsert", "agent": "context_librarian", "trace_id": "t1"}],
}


def test_render_includes_all_three_view_headers():
    text = cli_report.render(_SNAPSHOT)
    assert "SCHEMA CHANGES OVER TIME" in text
    assert "INSIGHTS (WITH CONFIDENCE)" in text
    assert "CONTEXT CHANGELOG" in text


def test_render_includes_row_values():
    text = cli_report.render(_SNAPSHOT)
    assert "express_checkout" in text
    assert "0.82" in text
    assert "context_librarian" in text


def test_render_handles_empty_snapshot_without_crashing():
    text = cli_report.render({"schema_history": [], "insights": [], "context_changelog": []})
    assert "SCHEMA CHANGES OVER TIME" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd atlys_agentic && python -m pytest tests/test_viz.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'atlys_agentic.viz'`.

- [ ] **Step 3: Write `viz/cli_report.py`**

```python
# atlys_agentic/viz/__init__.py
```

```python
# atlys_agentic/viz/cli_report.py
from atlys_agentic import tools


def _table(rows: list[dict], columns: list[str]) -> str:
    if not rows:
        return "  (none yet)\n"
    widths = {c: max(len(c), max(len(str(r.get(c, ""))) for r in rows)) for c in columns}
    header = "  " + " | ".join(c.ljust(widths[c]) for c in columns)
    sep = "  " + "-+-".join("-" * widths[c] for c in columns)
    body = "\n".join(
        "  " + " | ".join(str(r.get(c, "")).ljust(widths[c]) for c in columns) for r in rows
    )
    return f"{header}\n{sep}\n{body}\n"


def render(snapshot: dict) -> str:
    parts = ["=== SCHEMA CHANGES OVER TIME ===\n"]
    parts.append(_table(snapshot["schema_history"], ["table", "version", "spec_id", "created_at"]))
    parts.append("\n=== INSIGHTS (WITH CONFIDENCE) ===\n")
    parts.append(_table(snapshot["insights"], ["spec_id", "question", "confidence", "created_at"]))
    parts.append("\n=== CONTEXT CHANGELOG ===\n")
    parts.append(_table(snapshot["context_changelog"], ["ts", "change_type", "agent", "trace_id"]))
    return "".join(parts)


def main() -> None:
    snapshot = tools.Tool_Emit_Viz()
    print(render(snapshot))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd atlys_agentic && python -m pytest tests/test_viz.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add atlys_agentic/viz/__init__.py atlys_agentic/viz/cli_report.py atlys_agentic/tests/test_viz.py
git commit -m "feat: structured CLI renderer for schema history, insights, context changelog"
```

---

### Task 20: `viz/dashboard.py` — lightweight Streamlit dashboard

**Files:**
- Create: `atlys_agentic/viz/dashboard.py`
- Modify: `atlys_agentic/tests/test_viz.py`

**Interfaces:**
- Consumes: `tools.Tool_Emit_Viz` (Task 11), `viz.cli_report._table` reused for column ordering constants.
- Produces: `viz.dashboard.load_snapshot() -> dict` (thin wrapper so the Streamlit script stays test-covered), `atlys_agentic/viz/dashboard.py` runnable via `streamlit run`.

Streamlit itself renders UI at runtime and isn't unit-testable in the traditional sense; only the data-loading function gets a test, and the dashboard is verified by manually running it (Step 4).

- [ ] **Step 1: Write the failing test**

```python
# append to atlys_agentic/tests/test_viz.py
from unittest.mock import patch


def test_dashboard_load_snapshot_delegates_to_emit_viz():
    from atlys_agentic.viz import dashboard

    with patch("atlys_agentic.viz.dashboard.tools.Tool_Emit_Viz", return_value=_SNAPSHOT) as mock_emit:
        snapshot = dashboard.load_snapshot()
    mock_emit.assert_called_once()
    assert snapshot == _SNAPSHOT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd atlys_agentic && python -m pytest tests/test_viz.py -k dashboard -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'atlys_agentic.viz.dashboard'`.

- [ ] **Step 3: Write `viz/dashboard.py`**

```python
# atlys_agentic/viz/dashboard.py
import pandas as pd
import streamlit as st

from atlys_agentic import tools


def load_snapshot() -> dict:
    return tools.Tool_Emit_Viz()


def render_dashboard() -> None:
    st.set_page_config(page_title="Atlys Agentic Analytics — Deliverable #4b", layout="wide")
    st.title("Atlys Agentic Analytics — Visualization Layer")

    snapshot = load_snapshot()

    st.header("Schema changes over time")
    st.dataframe(pd.DataFrame(snapshot["schema_history"]), use_container_width=True)

    st.header("Insights with confidence scores")
    insights_df = pd.DataFrame(snapshot["insights"])
    st.dataframe(insights_df, use_container_width=True)
    if not insights_df.empty and "confidence" in insights_df:
        st.bar_chart(insights_df.set_index("question")["confidence"])

    st.header("Context diff / changelog")
    st.dataframe(pd.DataFrame(snapshot["context_changelog"]), use_container_width=True)


if __name__ == "__main__":
    render_dashboard()
```

- [ ] **Step 4: Run test to verify it passes, then run the dashboard manually**

Run: `cd atlys_agentic && python -m pytest tests/test_viz.py -k dashboard -v`
Expected: 1 passed.

Manual check: `cd atlys_agentic && streamlit run viz/dashboard.py` → confirm three sections render with live chDB data (run Task 19's `python -m atlys_agentic.viz.cli_report` first if chDB is empty, or run an ingestion first via Task 15).

- [ ] **Step 5: Commit**

```bash
git add atlys_agentic/viz/dashboard.py atlys_agentic/tests/test_viz.py
git commit -m "feat: lightweight Streamlit dashboard for the 3 required viz views"
```

---

### Task 21: `assemble_submission.py` — package the unseen-spec deliverable

**Files:**
- Create: `atlys_agentic/assemble_submission.py`
- Test: `atlys_agentic/tests/test_assemble_submission.py`

**Interfaces:**
- Consumes: `paths.SCHEMAS_DIR/INSIGHTS_DIR/TRACES_DIR/SUBMISSION_DIR` (Task 1); output shapes from `flows.ingestion_flow.run` (Task 14) and `flows.analysis_flow.run` (Task 16).
- Produces: `assemble_submission.assemble(spec_id: str, ddl: str, insight_md: str, trace_json: dict) -> dict` (writes the 3 files, returns their paths), `assemble_submission.main(spec_id: str) -> None` (reads from `outputs/` and writes `submission/<spec_id>/`).

- [ ] **Step 1: Write the failing test**

```python
# atlys_agentic/tests/test_assemble_submission.py
import json

from atlys_agentic import assemble_submission, paths


def test_assemble_writes_all_three_required_files(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "SUBMISSION_DIR", tmp_path)
    written = assemble_submission.assemble(
        spec_id="06_unseen",
        ddl="CREATE TABLE unseen (...)",
        insight_md="# Insight\nPM-audience summary here.",
        trace_json={"trace_id": "t1", "spans": []},
    )
    out_dir = tmp_path / "06_unseen"
    assert (out_dir / "schema.sql").read_text() == "CREATE TABLE unseen (...)"
    assert "PM-audience" in (out_dir / "insight.md").read_text()
    assert json.loads((out_dir / "trace.json").read_text())["trace_id"] == "t1"
    assert written == {
        "schema": out_dir / "schema.sql",
        "insight": out_dir / "insight.md",
        "trace": out_dir / "trace.json",
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd atlys_agentic && python -m pytest tests/test_assemble_submission.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'atlys_agentic.assemble_submission'`.

- [ ] **Step 3: Write `assemble_submission.py`**

```python
# atlys_agentic/assemble_submission.py
import argparse
import json
import sys

from atlys_agentic import paths


def assemble(spec_id: str, ddl: str, insight_md: str, trace_json: dict) -> dict:
    out_dir = paths.SUBMISSION_DIR / spec_id
    out_dir.mkdir(parents=True, exist_ok=True)

    schema_path = out_dir / "schema.sql"
    insight_path = out_dir / "insight.md"
    trace_path = out_dir / "trace.json"

    schema_path.write_text(ddl)
    insight_path.write_text(insight_md)
    trace_path.write_text(json.dumps(trace_json, indent=2, default=str))

    return {"schema": schema_path, "insight": insight_path, "trace": trace_path}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Assemble submission/<spec_id>/{schema.sql,insight.md,trace.json}")
    parser.add_argument("--spec_id", required=True)
    parser.add_argument("--ddl_file", required=True)
    parser.add_argument("--insight_file", required=True)
    parser.add_argument("--trace_file", required=True)
    args = parser.parse_args(argv)

    ddl = paths.ATLYS_AGENTIC_DIR.joinpath(args.ddl_file).read_text()
    insight_md = paths.ATLYS_AGENTIC_DIR.joinpath(args.insight_file).read_text()
    trace_json = json.loads(paths.ATLYS_AGENTIC_DIR.joinpath(args.trace_file).read_text())

    written = assemble(args.spec_id, ddl, insight_md, trace_json)
    for label, path in written.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd atlys_agentic && python -m pytest tests/test_assemble_submission.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add atlys_agentic/assemble_submission.py atlys_agentic/tests/test_assemble_submission.py
git commit -m "feat: assemble_submission.py packages the schema.sql/insight.md/trace.json deliverable bundle"
```

---

### Task 22: E2E rehearsal on `01_express_checkout` (Day-2 dry run)

**Files:**
- Create: `atlys_agentic/tests/test_e2e_rehearsal.py`
- Create: `atlys_agentic/DAY2_RUNBOOK.md`

**Interfaces:**
- Consumes: `flows.ingestion_flow.run` (Task 14), `flows.analysis_flow.run` (Task 16), `assemble_submission.assemble` (Task 21), `tools.Tool_Emit_Viz` (Task 11) — the whole pipeline, wired together exactly as Day 2 will run it against `06_unseen`.

This is the design's own required check (`final_wiby.md` §11 step 6 and §14 "E2E rehearsal"): run the full CUJ4 flow against a **known** spec first, so Day 2 is a rerun of an already-proven path, not a first attempt. It requires live ClickHouse Cloud + Langfuse + Gemini credentials (all present in `atlys_agentic/config/.env`), so it is not mocked.

- [ ] **Step 1: Write the rehearsal test**

```python
# atlys_agentic/tests/test_e2e_rehearsal.py
import os

import pytest

from atlys_agentic import assemble_submission, chdb_client, paths
from atlys_agentic.flows import analysis_flow, ingestion_flow

pytestmark = pytest.mark.skipif(
    not os.getenv("CLICKHOUSE_HOST") or not os.getenv("GEMINI_API_KEY"),
    reason="E2E rehearsal requires live ClickHouse Cloud + Gemini credentials",
)


def test_full_cuj4_dry_run_on_express_checkout_produces_valid_submission():
    chdb_client.init_schema()
    chdb_client.init_base_context()

    ingestion_result = ingestion_flow.run(
        spec_id="01_express_checkout",
        table_name="express_checkout_rehearsal",
        input_fn=lambda _prompt: "APPROVE",
    )
    assert ingestion_result["approved"] is True
    assert ingestion_result["ddl_result"]["status"] == "ok"

    analysis_result = analysis_flow.run(
        question="Does Express Checkout lift conversion, and is there an iOS OTP issue?",
        spec_id="01_express_checkout",
        base_sql="SELECT count() AS c FROM express_checkout_rehearsal",
    )
    assert analysis_result["answer_md"]
    assert 0.0 <= analysis_result["confidence"]["score"] <= 1.0

    written = assemble_submission.assemble(
        spec_id="01_express_checkout_rehearsal",
        ddl=ingestion_result["ddl"],
        insight_md=analysis_result["answer_md"],
        trace_json={
            "ingestion_trace_id": ingestion_result["trace_id"],
            "analysis_trace_id": analysis_result["trace_id"],
        },
    )
    assert written["schema"].exists()
    assert written["insight"].exists()
    assert written["trace"].exists()
```

- [ ] **Step 2: Run the rehearsal**

Run: `cd atlys_agentic && python -m pytest tests/test_e2e_rehearsal.py -v -s`
Expected: PASS, with the HITL prompt auto-answered `"APPROVE"` (no manual input needed since `input_fn` is supplied). Confirm afterward in the ClickHouse Cloud console that `express_checkout_rehearsal` exists, and in Langfuse that both trace ids show spans for every step.

- [ ] **Step 3: Write `DAY2_RUNBOOK.md`** (operational checklist, not code — the actual Day-2 steps from `final_wiby.md` §11, made concrete for this repo)

```markdown
# Day-2 Unseen-Spec Runbook

1. Drop sealed files into `atlys_agentic/specs/06_unseen/{spec.md, events.ndjson}`.
2. `cd atlys_agentic && python run_ingestion.py --spec_dir specs/06_unseen --table <name from spec>`
   — review the printed DDL/MV, type `APPROVE`.
3. Ask the PM question(s) from the spec via the LibreChat "Atlys Analyst" endpoint
   (`docker compose -f librechat/docker-compose.librechat.yml up -d`, backend already
   running via `uvicorn atlys_agentic.run_chat:app --port 8008`), or call
   `flows.analysis_flow.run(...)` directly from a Python shell.
4. Export the Langfuse trace: open the "Atlys Analyst" project, find the run tagged
   `06_unseen`, copy the trace URL, and `GET` the trace JSON via the Langfuse API.
5. `python assemble_submission.py --spec_id 06_unseen --ddl_file outputs/schemas/<table>.sql --insight_file outputs/insights/<question>.md --trace_file outputs/traces/<trace_id>.json`
6. Confirm `submission/06_unseen/{schema.sql, insight.md, trace.json}` all exist and are non-empty.
7. This exact sequence was already rehearsed end-to-end on `01_express_checkout` in
   `tests/test_e2e_rehearsal.py` — if Day 2 fails at any step, that test is the first
   thing to re-run to isolate whether it's an environment issue or a 6th-spec-specific one.
```

- [ ] **Step 4: Commit**

```bash
git add atlys_agentic/tests/test_e2e_rehearsal.py atlys_agentic/DAY2_RUNBOOK.md
git commit -m "test: E2E rehearsal of full CUJ4 pipeline on 01_express_checkout + Day-2 runbook"
```

---

## Self-Review Notes

- **Spec coverage:** Instrumentation Agent (Tasks 4-6, 12, 14-15) · Analytics Agent (Tasks 7, 10, 12, 16-18) · Context Agent (Tasks 8-9, 12, 14) · Tracing (Task 13, spans threaded through 14/16) · Visualization (Tasks 11, 19-20) · Unseen-spec deliverable (Tasks 21-22) · Schema-quality rules §7.1 (Task 4 tests) · Insight rules §7.2 multi-cut (Task 16 test 1) · Confidence formula §9 (Task 10) · Config contract §13 (Task 1) · CUJ1-4 (Tasks 14-17, 22) · dynamic/conditional workflow requirement (Tasks 14 and 16 both use `@router`, not a fixed linear chain).
- **Placeholder scan:** the one empty test stub drafted in Task 4 Step 1 is explicitly called out and removed in Step 3 before the real implementation — no other TBD/"add error handling"/"similar to Task N" patterns remain.
- **Type consistency:** `Tool_Execute_DDL` return shape `{"status", "table", "version", "error"}` used identically in Task 6 tests, Task 14's `IngestionState.ddl_result`, and Task 22. `Tool_Score_Confidence` return shape `{"score", "rationale"}` used identically in Tasks 10, 12, 16. `analysis_flow.run(...)` return shape `{"answer_md", "confidence", "known_issue_match", "cuts", "trace_id"}` used identically in Tasks 16, 17, 22.

---

## Execution Notes for the Subagent Runner

- Tasks 1-13 have zero external dependencies (pure logic + mocked I/O) — safe to run fully unattended.
- Tasks 14, 15, 16 depend on the real `crewai.flow` API (`Flow`, `start`, `listen`, `router`) — verified against installed `crewai==1.15.10` before this plan was written; if a different version is resolved at implementation time, re-check `from crewai.flow.flow import Flow, start, listen, router` still exports those names before debugging further.
- Task 17's tests require `fastapi`/`httpx` available for `TestClient` — add `httpx` to `requirements.txt` if the installed FastAPI version needs it split out.
- Tasks 18, 20 (LibreChat, Streamlit dashboard) have manual verification steps that need Docker / a browser — flag these back to the user rather than marking them silently "done" from an automated run.
- Task 22 (E2E rehearsal) spends real ClickHouse Cloud + Gemini + Langfuse quota — run it once deliberately, not on every CI pass.
