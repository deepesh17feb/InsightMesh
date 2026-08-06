# CUJ 1 → CUJ 2 E2E Integration Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a pytest suite that generates deterministic synthetic event data, ingests it through the real CUJ 1 tool-layer pipeline, queries it back through the real CUJ 2 tool-layer pipeline, and asserts row-level and aggregate correctness, schema integrity, and query latency — proving the two pipelines actually agree on what got stored.

**Architecture:** A `tests/e2e/` package. `conftest.py` monkeypatches `ch_client.command`/`select`/`insert_ndjson` so every "ClickHouse Cloud" call in `tools_cuj1.py`/`tools_cuj2.py` lands on the project's existing embedded `chdb.session` instead — verified locally to execute real `MergeTree` DDL, `PARTITION BY`, `TTL`, `LowCardinality`, `Nullable`, `GROUP BY`, `uniqExact`, `DESCRIBE TABLE`. `PYTEST_CURRENT_TEST` is unset only for the duration of tool calls that check it (`Tool_Load_Events`, `Tool_Analytics_Compute`), never around LLM-gated flow code (which this suite never calls). Langfuse tracing is mocked exactly like `tests/test_tracing.py` does today, so no real network calls happen anywhere in the suite. Synthetic spec directories live under `src/atlys_agentic/specs/e2e_synth_<name>/` — a root `paths.py` already recognizes — and are deleted, along with their chDB tables/catalog rows, in fixture teardown.

**Tech Stack:** Python 3.11, pytest 8, chdb 4.2.1 (already a project dependency), the existing `atlys_agentic.tools`/`tools_cuj1`/`tools_cuj2`/`chdb_client`/`ch_client` modules — no new dependencies.

## Global Constraints

- Python `>=3.11,<3.14` (`pyproject.toml`); use `.venv/bin/python` / `.venv/bin/pytest` for every command in this plan (already provisioned, has `chdb==4.2.1` and `clickhouse-connect` installed).
- `pyproject.toml` sets `pythonpath = ["src"]` and `testpaths = ["tests"]` — new files go under `tests/e2e/` and import `atlys_agentic.*` directly, no path hacks needed.
- **Never write to `problem statment/`** (the graded directory, typo preserved intentionally) — all synthetic spec dirs go under `src/atlys_agentic/specs/e2e_synth_<name>/`.
- **No real network or LLM calls** anywhere in this suite — Langfuse tracing is mocked in every test via an autouse fixture; this suite never calls `ingestion_flow.run()`/`analysis_flow.run()` (which contain LLM-gated branches), only the tool-layer functions in `tools_cuj1.py`/`tools_cuj2.py`.
- Every fixture that creates a chDB table or spec directory must clean it up in teardown (`shutil.rmtree` + `DROP TABLE IF EXISTS` + `ALTER TABLE schema_registry/table_semantics DELETE WHERE ...`) — the chDB store at `src/atlys_agentic/chdb_data/` is a persistent on-disk singleton shared with the real running app; leaking synthetic tables into it would pollute `_discover_cataloged_specs()` for real usage.
- Reference design doc: `docs/superpowers/specs/2026-08-06-cuj1-cuj2-e2e-tests-design.md`.

---

### Task 1: E2E harness — chdb-only `ch_client` patch, tracing mock, synthetic spec fixture

**Files:**
- Create: `tests/e2e/__init__.py`
- Create: `tests/e2e/conftest.py`
- Create: `tests/e2e/pipeline_helpers.py`
- Test: `tests/e2e/test_cuj1_to_cuj2_e2e.py` (harness smoke test only in this task)

**Interfaces:**
- Produces (`conftest.py` fixtures, consumed by every later task):
  - `chdb_only_ch_client(monkeypatch) -> ch_client module` — patches `ch_client.command`, `ch_client.select`, `ch_client.insert_ndjson`.
  - `no_pytest_guard(monkeypatch) -> None` — deletes `PYTEST_CURRENT_TEST` from `os.environ` for the test body.
  - `mock_tracing(monkeypatch) -> None` — **autouse**, applies to every test in `tests/e2e/` automatically.
  - `synthetic_spec() -> Callable[[str, str, list[dict]], tuple[str, str]]` — factory `_make(name, spec_md_text, events) -> (spec_id, table_name)`.
- Produces (`pipeline_helpers.py`, consumed by every later task):
  - `LATENCY_BUDGET_SECONDS: float = 2.0`
  - `ingest(spec_id: str, table_name: str, expected_row_count: int) -> dict` — returns `{"ddl": str, "ddl_result": dict, "load_result": dict, "semantics": dict}`, raises `AssertionError` on any pipeline-step failure.
  - `query(sql: str, spec_id: str = "") -> tuple[list[dict], float]` — returns `(rows, elapsed_seconds)`.

- [ ] **Step 1: Write the smoke test (will fail — nothing exists yet)**

Create `tests/e2e/__init__.py` (empty file, makes the directory a package so `from tests.e2e import ...` works):

```python
```

Create `tests/e2e/test_cuj1_to_cuj2_e2e.py` with just the harness smoke test for now:

```python
"""E2E: generate synthetic data -> ingest via the CUJ1 tool pipeline -> query
via the CUJ2 tool pipeline -> assert correctness, schema integrity, latency.

See docs/superpowers/specs/2026-08-06-cuj1-cuj2-e2e-tests-design.md for why
this suite talks to a local chdb session instead of live ClickHouse Cloud.
"""
from __future__ import annotations

import pytest

from tests.e2e import pipeline_helpers


def test_harness_persists_and_queries_via_chdb(chdb_only_ch_client, no_pytest_guard, synthetic_spec):
    """Minimal round trip proving the harness itself works: two events in,
    queryable back out through the real CUJ1/CUJ2 tool functions."""
    spec_md_text = "# Feature spec — Harness Smoke Test\n\n## What it does\nHarness check.\n"
    events = [
        {
            "event": "smoke_test_event",
            "id": "smoke-1",
            "timestamp": "2026-06-01T00:00:00.000",
            "user_id": "smoke-user-1",
            "device_type": "ios",
        },
        {
            "event": "smoke_test_event",
            "id": "smoke-2",
            "timestamp": "2026-06-01T00:01:00.000",
            "user_id": "smoke-user-2",
            "device_type": "android",
        },
    ]
    spec_id, table_name = synthetic_spec("harness_smoke", spec_md_text, events)

    pipeline_helpers.ingest(spec_id, table_name, expected_row_count=2)

    rows, elapsed = pipeline_helpers.query(f"SELECT count() AS c FROM {table_name}", spec_id=spec_id)
    assert elapsed < pipeline_helpers.LATENCY_BUDGET_SECONDS
    assert rows[0]["c"] == 2
```

- [ ] **Step 2: Run it to confirm it fails for the right reason**

Run: `.venv/bin/python -m pytest tests/e2e/test_cuj1_to_cuj2_e2e.py -v`
Expected: `ModuleNotFoundError: No module named 'tests.e2e.pipeline_helpers'` (or fixture-not-found errors) — `conftest.py` and `pipeline_helpers.py` don't exist yet.

- [ ] **Step 3: Verify the chdb DDL/DML behavior this harness relies on (already verified manually — record it as a comment, not a re-derivation)**

No code for this step — this was already confirmed interactively: `chdb.session.Session` executes real `CREATE TABLE ... ENGINE=MergeTree ... PARTITION BY ... TTL ...`, `INSERT ... FORMAT JSONEachRow`, `GROUP BY`/`uniqExact`, `DESCRIBE TABLE`, `ALTER TABLE ... DELETE WHERE ...`, and `DROP TABLE IF EXISTS` correctly, with no network. This is why the harness patches `ch_client` onto `chdb_client.run` rather than building a new local engine.

- [ ] **Step 4: Write `pipeline_helpers.py`**

```python
"""Shared CUJ1-ingest / CUJ2-query helpers for the E2E suite.

`ingest()` calls the real tool-layer CUJ1 pipeline (schema inference,
invariant validation, DDL execution, event load, table-semantics write) —
the same functions `flows/ingestion_flow.py` calls, minus the LLM-reasoning
and LibreChat chat-state layers that `tests/test_ingestion_flow.py` already
covers. `query()` calls the real CUJ2 execution primitive `Tool_Analytics_Compute`
that the Query Architect's planned SELECTs run through per docs/CUJ2.md §4.
"""
from __future__ import annotations

import time

from atlys_agentic import paths, tools

LATENCY_BUDGET_SECONDS = 2.0


def ingest(spec_id: str, table_name: str, expected_row_count: int) -> dict:
    """Run schema inference -> invariant validation -> DDL execution -> event
    load -> table-semantics write. Asserts each step succeeded; returns the
    raw tool outputs for callers that want to inspect the DDL or load result."""
    ndjson_path = paths.events_ndjson(spec_id)
    spec_text = paths.spec_md(spec_id).read_text(encoding="utf-8")

    ddl = tools.Tool_Infer_Schema(ndjson_path, spec_text, table_name)
    violations = tools.Tool_Validate_Invariants(ddl)
    assert violations == [], f"unexpected invariant violations: {violations}"

    ddl_result = tools.Tool_Execute_DDL(ddl, table_name, spec_id, dry_run=False)
    assert ddl_result["status"] == "ok", ddl_result

    load_result = tools.Tool_Load_Events(spec_id=spec_id, table_name=table_name, dry_run=False)
    assert load_result["status"] == "loaded", load_result
    assert load_result["rows_loaded"] == expected_row_count, load_result
    assert load_result["verified_count"] == expected_row_count, load_result

    semantics = tools.Tool_Write_Table_Semantics(
        spec_id=spec_id,
        table_name=table_name,
        spec_text=spec_text,
        column_names=tools._columns_from_ddl(ddl),
    )

    return {"ddl": ddl, "ddl_result": ddl_result, "load_result": load_result, "semantics": semantics}


def query(sql: str, spec_id: str = "") -> tuple[list[dict], float]:
    """Run a CUJ2 analytics query through the real tool and return (rows, elapsed_seconds)."""
    start = time.perf_counter()
    result = tools.Tool_Analytics_Compute(sql, spec_id=spec_id)
    elapsed = time.perf_counter() - start
    return result["rows"], elapsed
```

- [ ] **Step 5: Write `conftest.py`**

```python
"""Shared fixtures for the CUJ1->CUJ2 E2E suite.

Routes ch_client at a local chdb session (no live ClickHouse Cloud, no
network), mutes real Langfuse tracing (same pattern as tests/test_tracing.py),
and provisions/cleans up synthetic spec directories + their chDB rows.
See docs/superpowers/specs/2026-08-06-cuj1-cuj2-e2e-tests-design.md.
"""
from __future__ import annotations

import json
import shutil
from unittest.mock import MagicMock

import pytest

from atlys_agentic import ch_client, chdb_client, paths, tracing


@pytest.fixture
def chdb_only_ch_client(monkeypatch):
    """Route ch_client.command/select/insert_ndjson at the local chdb session
    so CUJ1 writes and CUJ2 reads share one real embedded ClickHouse engine
    instead of touching live Cloud."""
    monkeypatch.setattr(ch_client, "command", lambda ddl: chdb_client.run(ddl, fmt="CSV"))
    monkeypatch.setattr(ch_client, "select", lambda sql: chdb_client.run(sql))
    monkeypatch.setattr(ch_client, "insert_ndjson", lambda table, content: None, raising=False)
    chdb_client.init_schema()
    return ch_client


@pytest.fixture
def no_pytest_guard(monkeypatch):
    """Tool_Load_Events / Tool_Analytics_Compute both no-op under
    PYTEST_CURRENT_TEST as a belt against tests hitting live ClickHouse Cloud.
    This suite calls only tool-layer functions -- never the LLM-gated flow
    orchestration -- so lifting the guard for the test body triggers no
    network or LLM calls, only the real storage code paths."""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)


@pytest.fixture(autouse=True)
def mock_tracing(monkeypatch):
    """Prevent real Langfuse network calls. Mirrors the mock shape used in
    tests/test_tracing.py's test_step_nests_under_active_trace_without_flushing."""
    mock_client = MagicMock()
    mock_client.start_as_current_observation.return_value.__enter__.return_value = MagicMock()
    mock_client.get_current_trace_id.return_value = "e2e-test-trace"
    mock_client.get_trace_url.return_value = None
    monkeypatch.setattr(tracing, "client", lambda: mock_client)


@pytest.fixture
def synthetic_spec():
    """Factory fixture: _make(name, spec_md_text, events) writes spec.md +
    events.ndjson under src/atlys_agentic/specs/e2e_synth_<name>/ (never the
    graded problem statement directory) and returns (spec_id, table_name).
    Teardown removes the directory and any chDB tables/catalog rows it caused."""
    created_dirs: list = []
    created_tables: list[str] = []

    def _make(name: str, spec_md_text: str, events: list[dict]) -> tuple[str, str]:
        spec_id = f"e2e_synth_{name}"
        table_name = f"e2e_{name}"
        spec_dir = paths.ATLYS_AGENTIC_DIR / "specs" / spec_id
        spec_dir.mkdir(parents=True, exist_ok=True)
        (spec_dir / "spec.md").write_text(spec_md_text, encoding="utf-8")
        with (spec_dir / "events.ndjson").open("w", encoding="utf-8") as f:
            for ev in events:
                f.write(json.dumps(ev) + "\n")
        created_dirs.append(spec_dir)
        created_tables.append(table_name)
        return spec_id, table_name

    yield _make

    for spec_dir in created_dirs:
        shutil.rmtree(spec_dir, ignore_errors=True)
    for table_name in created_tables:
        for cleanup_sql in (
            f"DROP TABLE IF EXISTS {table_name}",
            f"ALTER TABLE schema_registry DELETE WHERE \"table\" = '{table_name}'",
            f"ALTER TABLE table_semantics DELETE WHERE table_name = '{table_name}'",
        ):
            try:
                chdb_client.run(cleanup_sql, fmt="CSV")
            except Exception:
                pass
```

- [ ] **Step 6: Run the smoke test again — verify it passes**

Run: `.venv/bin/python -m pytest tests/e2e/test_cuj1_to_cuj2_e2e.py -v`
Expected: `1 passed`

- [ ] **Step 7: Run the full existing suite to confirm no regressions from the new package**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: all previously-passing tests still pass; the one new E2E test passes too.

- [ ] **Step 8: Commit**

```bash
git add tests/e2e/__init__.py tests/e2e/conftest.py tests/e2e/pipeline_helpers.py tests/e2e/test_cuj1_to_cuj2_e2e.py
git commit -m "$(cat <<'EOF'
test: add chdb-only E2E harness for CUJ1->CUJ2 integration tests

conftest.py routes ch_client at the local chdb session so CUJ1 writes
and CUJ2 reads share one real embedded ClickHouse engine, with no live
Cloud connection and no real Langfuse network calls. pipeline_helpers.py
wraps the tool-layer ingest/query round trip used by every scenario test.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Happy-path scenario — full funnel ingest, aggregate correctness, schema integrity, latency

**Files:**
- Create: `tests/e2e/synthetic_data.py`
- Modify: `tests/e2e/test_cuj1_to_cuj2_e2e.py` (add `test_happy_path_ingest_and_query`)

**Interfaces:**
- Consumes: `pipeline_helpers.ingest`, `pipeline_helpers.query`, `pipeline_helpers.LATENCY_BUDGET_SECONDS` (Task 1); fixtures `chdb_only_ch_client`, `no_pytest_guard`, `synthetic_spec` (Task 1, `mock_tracing` is autouse).
- Produces (`synthetic_data.py`, consumed by Tasks 2-5):
  - `SPEC_MD_TEMPLATE: str` — `.format(title=...)` template for generated `spec.md` files.
  - `happy_path(num_applications: int = 50) -> tuple[str, list[dict], dict]` — `(spec_md_text, events, expected)`.

- [ ] **Step 1: Write the failing test**

Append to `tests/e2e/test_cuj1_to_cuj2_e2e.py`:

```python
from tests.e2e import synthetic_data


def test_happy_path_ingest_and_query(chdb_only_ch_client, no_pytest_guard, synthetic_spec):
    """Full funnel: shown -> selected -> otp_entered -> (confirmed if OTP
    succeeded). Asserts exact aggregate correctness, a point lookup by
    application_id, schema integrity via DESCRIBE TABLE, the table_semantics
    handoff CUJ1 writes for CUJ2 (docs/CUJ1.md §6a), and query latency."""
    spec_md_text, events, expected = synthetic_data.happy_path(num_applications=50)
    spec_id, table_name = synthetic_spec("happy_path", spec_md_text, events)

    ingest_result = pipeline_helpers.ingest(spec_id, table_name, expected["total_events"])

    # -- aggregate correctness --
    rows, elapsed = pipeline_helpers.query(
        f"SELECT count() AS c FROM {table_name} WHERE event = 'express_payment_confirmed'",
        spec_id=spec_id,
    )
    assert elapsed < pipeline_helpers.LATENCY_BUDGET_SECONDS
    assert rows[0]["c"] == expected["confirmed_count"]

    rows, _ = pipeline_helpers.query(
        f"SELECT round(sum(payment_amount), 2) AS s FROM {table_name} "
        f"WHERE event = 'express_payment_confirmed'",
        spec_id=spec_id,
    )
    assert rows[0]["s"] == pytest.approx(expected["confirmed_sum_payment_amount"], abs=0.01)

    rows, _ = pipeline_helpers.query(
        f"SELECT countIf(otp_success = 1) AS c FROM {table_name} WHERE event = 'otp_entered'",
        spec_id=spec_id,
    )
    assert rows[0]["c"] == expected["confirmed_count"]

    # -- point lookup by a deterministic correlation id --
    sample = expected["sample_application"]
    rows, _ = pipeline_helpers.query(
        f"SELECT user_id, device_type, shown_amount FROM {table_name} "
        f"WHERE application_id = '{sample['application_id']}' AND event = 'express_checkout_shown'",
        spec_id=spec_id,
    )
    assert len(rows) == 1
    assert rows[0]["user_id"] == sample["user_id"]
    assert rows[0]["device_type"] == sample["device_type"]
    assert rows[0]["shown_amount"] == pytest.approx(sample["shown_amount"], abs=0.01)

    # -- schema integrity: declared columns actually exist with the inferred types --
    described, _ = pipeline_helpers.query(f"DESCRIBE TABLE {table_name}")
    described_cols = {row["name"] for row in described}
    for col in tools._columns_from_ddl(ingest_result["ddl"]):
        assert col in described_cols, f"column '{col}' missing from DESCRIBE TABLE output"

    # -- CUJ1 -> CUJ2 handoff: table_semantics row exists for this table --
    assert ingest_result["semantics"]["table_name"] == table_name
    assert ingest_result["semantics"]["version"] >= 1
```

Add the two new imports at the top of `tests/e2e/test_cuj1_to_cuj2_e2e.py` (alongside the existing `from tests.e2e import pipeline_helpers`):

```python
from atlys_agentic import tools
from tests.e2e import pipeline_helpers, synthetic_data
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `.venv/bin/python -m pytest tests/e2e/test_cuj1_to_cuj2_e2e.py::test_happy_path_ingest_and_query -v`
Expected: `ModuleNotFoundError: No module named 'tests.e2e.synthetic_data'`

- [ ] **Step 3: Write `synthetic_data.py`**

```python
"""Deterministic synthetic event generators for the CUJ1->CUJ2 E2E suite.

Every generator returns (spec_md_text, events, expected) where `expected` is
ground truth computed independently in Python -- never re-derived from the
SQL the tests assert against. Field shapes mirror
`problem statment/specs/01_express_checkout/events.ndjson` (event, id,
timestamp, device_type, os, geoip_country_code, user_id, application_id,
destination, plus stage-specific fields like shown_amount/otp_success/
nested payment.amount).
"""
from __future__ import annotations

DEVICES = ["ios", "android", "Desktop", "web-user-b2c"]
COUNTRIES = ["IN", "SG", "AE", "US"]

SPEC_MD_TEMPLATE = """# Feature spec — E2E Synthetic {title}

## What it does
Synthetic data generated for the CUJ1->CUJ2 end-to-end test suite. Not a real
feature spec -- do not treat as production instrumentation.

## User actions (raw events emitted)
- `express_checkout_shown`
- `express_checkout_selected`
- `otp_entered`
- `express_payment_confirmed`
"""


def happy_path(num_applications: int = 50) -> tuple[str, list[dict], dict]:
    """`num_applications` funnels; every 5th applicant fails OTP and never
    confirms. Returns the exact confirmed count and SUM(payment_amount)
    computed independently of any SQL, for parity assertions."""
    events: list[dict] = []
    confirmed_count = 0
    confirmed_sum = 0.0
    sample_application: dict | None = None

    for i in range(num_applications):
        device = DEVICES[i % len(DEVICES)]
        country = COUNTRIES[i % len(COUNTRIES)]
        user_id = f"e2e_user_{i:04d}"
        application_id = f"e2e_app_{i:04d}"
        shown_amount = round(1000.0 + i * 7.5, 2)
        currency = "INR"
        otp_success = i % 5 != 0
        minute = i

        shown = {
            "event": "express_checkout_shown",
            "id": f"e2e_{i:04d}_shown",
            "timestamp": f"2026-06-01T00:{minute:02d}:00.000",
            "device_type": device,
            "os": device,
            "geoip_country_code": country,
            "user_id": user_id,
            "application_id": application_id,
            "destination": country,
            "eligible": True,
            "shown_amount": shown_amount,
            "currency": currency,
        }
        selected = {
            "event": "express_checkout_selected",
            "id": f"e2e_{i:04d}_selected",
            "timestamp": f"2026-06-01T00:{minute:02d}:30.000",
            "device_type": device,
            "os": device,
            "geoip_country_code": country,
            "user_id": user_id,
            "application_id": application_id,
            "destination": country,
            "saved_method_type": "card" if i % 2 == 0 else "upi",
        }
        otp = {
            "event": "otp_entered",
            "id": f"e2e_{i:04d}_otp",
            "timestamp": f"2026-06-01T00:{minute:02d}:45.000",
            "device_type": device,
            "os": device,
            "geoip_country_code": country,
            "user_id": user_id,
            "application_id": application_id,
            "destination": country,
            "otp_attempts": 1,
            "otp_success": otp_success,
        }
        events.extend([shown, selected, otp])

        if otp_success:
            confirmed = {
                "event": "express_payment_confirmed",
                "id": f"e2e_{i:04d}_confirmed",
                "timestamp": f"2026-06-01T00:{minute:02d}:50.000",
                "device_type": device,
                "os": device,
                "geoip_country_code": country,
                "user_id": user_id,
                "application_id": application_id,
                "destination": country,
                "payment": {
                    "amount": shown_amount,
                    "currency": currency,
                    "latency_ms": 2000 + i * 3,
                },
            }
            events.append(confirmed)
            confirmed_count += 1
            confirmed_sum = round(confirmed_sum + shown_amount, 2)

        if i == 0:
            sample_application = {
                "application_id": application_id,
                "user_id": user_id,
                "device_type": device,
                "shown_amount": shown_amount,
            }

    expected = {
        "total_events": len(events),
        "confirmed_count": confirmed_count,
        "confirmed_sum_payment_amount": confirmed_sum,
        "sample_application": sample_application,
    }
    return SPEC_MD_TEMPLATE.format(title="Happy Path"), events, expected
```

- [ ] **Step 4: Run it to confirm it passes**

Run: `.venv/bin/python -m pytest tests/e2e/test_cuj1_to_cuj2_e2e.py -v`
Expected: `2 passed` (harness smoke test + happy path)

- [ ] **Step 5: Commit**

```bash
git add tests/e2e/synthetic_data.py tests/e2e/test_cuj1_to_cuj2_e2e.py
git commit -m "$(cat <<'EOF'
test: add CUJ1->CUJ2 happy-path E2E scenario

50 synthetic funnels through Tool_Infer_Schema/Tool_Execute_DDL/
Tool_Load_Events, queried back through Tool_Analytics_Compute. Asserts
exact aggregate correctness (COUNT/SUM), a point lookup by
application_id, DESCRIBE TABLE schema integrity, the table_semantics
CUJ1->CUJ2 handoff, and query latency.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Schema/type boundary scenario — nulls, unicode, long strings, float precision, partition edges

**Files:**
- Modify: `tests/e2e/synthetic_data.py` (add `boundary_cases`)
- Modify: `tests/e2e/test_cuj1_to_cuj2_e2e.py` (add `test_boundary_cases_survive_round_trip`)

**Interfaces:**
- Consumes: same as Task 2, plus `synthetic_data.SPEC_MD_TEMPLATE`.
- Produces: `synthetic_data.boundary_cases() -> tuple[str, list[dict], dict]` (consumed only by its own test; no later task depends on it).

- [ ] **Step 1: Write the failing test**

Append to `tests/e2e/test_cuj1_to_cuj2_e2e.py`:

```python
def test_boundary_cases_survive_round_trip(chdb_only_ch_client, no_pytest_guard, synthetic_spec):
    """NULL optional fields, unicode + SQL-lookalike strings, a max-length
    string, a float-precision edge value, and timestamps sitting exactly on
    a toYYYYMM() partition boundary -- none may be dropped or corrupted."""
    spec_md_text, events, expected = synthetic_data.boundary_cases()
    spec_id, table_name = synthetic_spec("boundary", spec_md_text, events)

    pipeline_helpers.ingest(spec_id, table_name, expected["total_events"])

    rows, _ = pipeline_helpers.query(
        f"SELECT shown_amount FROM {table_name} WHERE id = 'e2e_boundary_null_amount'",
        spec_id=spec_id,
    )
    assert len(rows) == 1
    assert rows[0]["shown_amount"] is None

    rows, _ = pipeline_helpers.query(
        f"SELECT city FROM {table_name} WHERE id = 'e2e_boundary_unicode'",
        spec_id=spec_id,
    )
    assert rows[0]["city"] == expected["unicode_city"]

    rows, _ = pipeline_helpers.query(
        f"SELECT length(city) AS n FROM {table_name} WHERE id = 'e2e_boundary_long_string'",
        spec_id=spec_id,
    )
    assert rows[0]["n"] == expected["long_city_length"]

    rows, _ = pipeline_helpers.query(
        f"SELECT payment_amount FROM {table_name} WHERE id = 'e2e_boundary_float_precision'",
        spec_id=spec_id,
    )
    assert rows[0]["payment_amount"] == pytest.approx(expected["precise_amount"], rel=1e-12)

    rows, _ = pipeline_helpers.query(
        f"SELECT toYYYYMM(timestamp) AS part, count() AS c FROM {table_name} "
        f"WHERE id IN ('e2e_boundary_jan_edge', 'e2e_boundary_feb_edge') "
        f"GROUP BY part ORDER BY part",
        spec_id=spec_id,
    )
    assert [str(r["part"]) for r in rows] == [expected["jan_partition"], expected["feb_partition"]]
    assert all(r["c"] == 1 for r in rows)
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `.venv/bin/python -m pytest tests/e2e/test_cuj1_to_cuj2_e2e.py::test_boundary_cases_survive_round_trip -v`
Expected: `AttributeError: module 'tests.e2e.synthetic_data' has no attribute 'boundary_cases'`

- [ ] **Step 3: Add `boundary_cases()` to `synthetic_data.py`**

Append to `tests/e2e/synthetic_data.py`:

```python
def boundary_cases() -> tuple[str, list[dict], dict]:
    """One event missing an optional numeric field entirely (exercises
    Nullable), one with a unicode + SQL-lookalike string (exercises the safe
    JSONEachRow insert path -- no manual SQL string interpolation), one with
    a long string, one with an unrounded float, and two sitting exactly on a
    January/February toYYYYMM() partition boundary."""
    long_city = "x" * 500
    unicode_city = "北京 — 'quoted'; DROP TABLE nope; --"
    precise_amount = 0.1 + 0.2  # 0.30000000000000004

    events = [
        {  # no shown_amount / currency at all -> exercises Nullable(Float64)
            "event": "express_checkout_shown",
            "id": "e2e_boundary_null_amount",
            "timestamp": "2026-06-01T00:00:00.000",
            "device_type": "ios",
            "os": "iOS",
            "geoip_country_code": "IN",
            "user_id": "e2e_boundary_user_1",
            "application_id": "e2e_boundary_app_1",
            "destination": "IN",
            "eligible": True,
        },
        {
            "event": "express_checkout_shown",
            "id": "e2e_boundary_unicode",
            "timestamp": "2026-06-01T00:01:00.000",
            "device_type": "ios",
            "os": "iOS",
            "geoip_country_code": "CN",
            "city": unicode_city,
            "user_id": "e2e_boundary_user_2",
            "application_id": "e2e_boundary_app_2",
            "destination": "CN",
            "eligible": True,
            "shown_amount": 100.0,
            "currency": "CNY",
        },
        {
            "event": "express_checkout_shown",
            "id": "e2e_boundary_long_string",
            "timestamp": "2026-06-01T00:02:00.000",
            "device_type": "ios",
            "os": "iOS",
            "geoip_country_code": "IN",
            "city": long_city,
            "user_id": "e2e_boundary_user_3",
            "application_id": "e2e_boundary_app_3",
            "destination": "IN",
            "eligible": True,
            "shown_amount": 100.0,
            "currency": "INR",
        },
        {
            "event": "express_payment_confirmed",
            "id": "e2e_boundary_float_precision",
            "timestamp": "2026-06-01T00:03:00.000",
            "device_type": "ios",
            "os": "iOS",
            "geoip_country_code": "IN",
            "user_id": "e2e_boundary_user_4",
            "application_id": "e2e_boundary_app_4",
            "destination": "IN",
            "payment": {"amount": precise_amount, "currency": "INR", "latency_ms": 1000},
        },
        {  # last moment of the January partition
            "event": "express_checkout_shown",
            "id": "e2e_boundary_jan_edge",
            "timestamp": "2026-01-31T23:59:59.000",
            "device_type": "ios",
            "os": "iOS",
            "geoip_country_code": "IN",
            "user_id": "e2e_boundary_user_5",
            "application_id": "e2e_boundary_app_5",
            "destination": "IN",
            "eligible": True,
            "shown_amount": 50.0,
            "currency": "INR",
        },
        {  # first moment of the February partition
            "event": "express_checkout_shown",
            "id": "e2e_boundary_feb_edge",
            "timestamp": "2026-02-01T00:00:00.000",
            "device_type": "ios",
            "os": "iOS",
            "geoip_country_code": "IN",
            "user_id": "e2e_boundary_user_6",
            "application_id": "e2e_boundary_app_6",
            "destination": "IN",
            "eligible": True,
            "shown_amount": 50.0,
            "currency": "INR",
        },
    ]

    expected = {
        "total_events": len(events),
        "unicode_city": unicode_city,
        "long_city_length": len(long_city),
        "precise_amount": precise_amount,
        "jan_partition": "202601",
        "feb_partition": "202602",
    }
    return SPEC_MD_TEMPLATE.format(title="Boundary Cases"), events, expected
```

- [ ] **Step 4: Run it to confirm it passes**

Run: `.venv/bin/python -m pytest tests/e2e/test_cuj1_to_cuj2_e2e.py -v`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add tests/e2e/synthetic_data.py tests/e2e/test_cuj1_to_cuj2_e2e.py
git commit -m "$(cat <<'EOF'
test: add schema/type boundary E2E scenario

Nulls, unicode + SQL-lookalike strings, a max-length string, a float
precision edge value, and timestamps exactly on a toYYYYMM() partition
boundary -- proves none get dropped, truncated, or misfiled by the
CUJ1 ingest -> CUJ2 query round trip.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Out-of-order / late-arriving events scenario

**Files:**
- Modify: `tests/e2e/synthetic_data.py` (add `out_of_order`)
- Modify: `tests/e2e/test_cuj1_to_cuj2_e2e.py` (add `test_out_of_order_events_query_correctly`)

**Interfaces:**
- Consumes: same as Task 2.
- Produces: `synthetic_data.out_of_order() -> tuple[str, list[dict], dict]`.

- [ ] **Step 1: Write the failing test**

Append to `tests/e2e/test_cuj1_to_cuj2_e2e.py`:

```python
def test_out_of_order_events_query_correctly(chdb_only_ch_client, no_pytest_guard, synthetic_spec):
    """Events are inserted in a scrambled order relative to their timestamps
    (simulating late-arriving / backfilled data). A time-ordered CUJ2 query
    must return them in chronological order regardless of insertion order."""
    spec_md_text, events, expected = synthetic_data.out_of_order()
    spec_id, table_name = synthetic_spec("ooo", spec_md_text, events)

    pipeline_helpers.ingest(spec_id, table_name, len(events))

    rows, elapsed = pipeline_helpers.query(
        f"SELECT id FROM {table_name} ORDER BY timestamp ASC",
        spec_id=spec_id,
    )
    assert elapsed < pipeline_helpers.LATENCY_BUDGET_SECONDS
    assert [r["id"] for r in rows] == expected["chronological_ids"]
    assert [r["id"] for r in rows] != expected["insertion_order_ids"]
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `.venv/bin/python -m pytest tests/e2e/test_cuj1_to_cuj2_e2e.py::test_out_of_order_events_query_correctly -v`
Expected: `AttributeError: module 'tests.e2e.synthetic_data' has no attribute 'out_of_order'`

- [ ] **Step 3: Add `out_of_order()` to `synthetic_data.py`**

Append to `tests/e2e/synthetic_data.py`:

```python
def out_of_order() -> tuple[str, list[dict], dict]:
    """5 events with fixed, 10-minutes-apart timestamps, inserted in a
    deliberately scrambled order (index 2, 0, 4, 1, 3) to simulate
    late-arriving / backfilled data."""
    chronological_ids = ["e2e_ooo_t0", "e2e_ooo_t1", "e2e_ooo_t2", "e2e_ooo_t3", "e2e_ooo_t4"]
    timestamps = [
        "2026-06-01T00:00:00.000",
        "2026-06-01T00:10:00.000",
        "2026-06-01T00:20:00.000",
        "2026-06-01T00:30:00.000",
        "2026-06-01T00:40:00.000",
    ]
    insertion_order = [2, 0, 4, 1, 3]

    events = []
    for idx in insertion_order:
        events.append({
            "event": "express_checkout_shown",
            "id": chronological_ids[idx],
            "timestamp": timestamps[idx],
            "device_type": "ios",
            "os": "iOS",
            "geoip_country_code": "IN",
            "user_id": f"e2e_ooo_user_{idx}",
            "application_id": f"e2e_ooo_app_{idx}",
            "destination": "IN",
            "eligible": True,
            "shown_amount": 100.0 + idx,
            "currency": "INR",
        })

    expected = {
        "chronological_ids": chronological_ids,
        "insertion_order_ids": [chronological_ids[i] for i in insertion_order],
    }
    return SPEC_MD_TEMPLATE.format(title="Out Of Order"), events, expected
```

- [ ] **Step 4: Run it to confirm it passes**

Run: `.venv/bin/python -m pytest tests/e2e/test_cuj1_to_cuj2_e2e.py -v`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add tests/e2e/synthetic_data.py tests/e2e/test_cuj1_to_cuj2_e2e.py
git commit -m "$(cat <<'EOF'
test: add out-of-order / late-arriving events E2E scenario

Events inserted in scrambled order relative to their timestamps; a
time-ordered CUJ2 query must still return correct chronological order.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Duplicate / idempotency scenario

**Files:**
- Modify: `tests/e2e/synthetic_data.py` (add `duplicate_events`)
- Modify: `tests/e2e/test_cuj1_to_cuj2_e2e.py` (add `test_duplicate_events_are_not_silently_deduped`)

**Interfaces:**
- Consumes: same as Task 2.
- Produces: `synthetic_data.duplicate_events() -> tuple[str, list[dict], dict]`.

- [ ] **Step 1: Write the failing test**

Append to `tests/e2e/test_cuj1_to_cuj2_e2e.py`:

```python
def test_duplicate_events_are_not_silently_deduped(chdb_only_ch_client, no_pytest_guard, synthetic_spec):
    """MergeTree does not deduplicate on INSERT. Two of three events are
    loaded twice (exact same id). CUJ2 must show the raw duplication via
    count() and the true distinct count via uniqExact(id) -- confirming
    which query shape a correctness-sensitive caller actually needs."""
    spec_md_text, events, expected = synthetic_data.duplicate_events()
    spec_id, table_name = synthetic_spec("dup", spec_md_text, events)

    pipeline_helpers.ingest(spec_id, table_name, expected["raw_row_count"])

    rows, _ = pipeline_helpers.query(f"SELECT count() AS c FROM {table_name}", spec_id=spec_id)
    assert rows[0]["c"] == expected["raw_row_count"]

    rows, _ = pipeline_helpers.query(f"SELECT uniqExact(id) AS c FROM {table_name}", spec_id=spec_id)
    assert rows[0]["c"] == expected["distinct_id_count"]
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `.venv/bin/python -m pytest tests/e2e/test_cuj1_to_cuj2_e2e.py::test_duplicate_events_are_not_silently_deduped -v`
Expected: `AttributeError: module 'tests.e2e.synthetic_data' has no attribute 'duplicate_events'`

- [ ] **Step 3: Add `duplicate_events()` to `synthetic_data.py`**

Append to `tests/e2e/synthetic_data.py`:

```python
def duplicate_events() -> tuple[str, list[dict], dict]:
    """3 distinct events; the first two are appended a second time with the
    exact same id, simulating an at-least-once delivery retry."""
    base = [
        {
            "event": "express_checkout_shown",
            "id": "e2e_dup_1",
            "timestamp": "2026-06-01T00:00:00.000",
            "device_type": "ios",
            "os": "iOS",
            "geoip_country_code": "IN",
            "user_id": "e2e_dup_user_1",
            "application_id": "e2e_dup_app_1",
            "destination": "IN",
            "eligible": True,
            "shown_amount": 100.0,
            "currency": "INR",
        },
        {
            "event": "express_checkout_shown",
            "id": "e2e_dup_2",
            "timestamp": "2026-06-01T00:01:00.000",
            "device_type": "android",
            "os": "Android",
            "geoip_country_code": "SG",
            "user_id": "e2e_dup_user_2",
            "application_id": "e2e_dup_app_2",
            "destination": "SG",
            "eligible": True,
            "shown_amount": 200.0,
            "currency": "SGD",
        },
        {
            "event": "express_checkout_shown",
            "id": "e2e_dup_3",
            "timestamp": "2026-06-01T00:02:00.000",
            "device_type": "Desktop",
            "os": "Mac OS X",
            "geoip_country_code": "US",
            "user_id": "e2e_dup_user_3",
            "application_id": "e2e_dup_app_3",
            "destination": "US",
            "eligible": True,
            "shown_amount": 300.0,
            "currency": "USD",
        },
    ]
    events = base + [dict(base[0]), dict(base[1])]

    expected = {
        "raw_row_count": len(events),
        "distinct_id_count": len(base),
    }
    return SPEC_MD_TEMPLATE.format(title="Duplicate Events"), events, expected
```

- [ ] **Step 4: Run it to confirm it passes**

Run: `.venv/bin/python -m pytest tests/e2e/test_cuj1_to_cuj2_e2e.py -v`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add tests/e2e/synthetic_data.py tests/e2e/test_cuj1_to_cuj2_e2e.py
git commit -m "$(cat <<'EOF'
test: add duplicate/idempotency E2E scenario

Exact-duplicate event ids loaded twice. MergeTree does not dedupe on
insert -- this test documents and asserts that real behavior: count()
shows the duplication, uniqExact(id) shows the true distinct count.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Scenario matrix doc + full-suite verification

**Files:**
- Create: `docs/E2E_TEST_SCENARIOS.md`

**Interfaces:** none (documentation only).

- [ ] **Step 1: Write the scenario matrix doc**

```markdown
# CUJ 1 → CUJ 2 E2E Test Scenario Matrix

Suite: `tests/e2e/`. Run with `.venv/bin/python -m pytest tests/e2e/ -v`.

Every scenario generates deterministic synthetic events, ingests them through
the real CUJ 1 tool pipeline (`Tool_Infer_Schema` → `Tool_Validate_Invariants`
→ `Tool_Execute_DDL` → `Tool_Load_Events` → `Tool_Write_Table_Semantics`),
then queries the persisted table through the real CUJ 2 execution primitive
(`Tool_Analytics_Compute`) — backed by a local embedded `chdb` session instead
of live ClickHouse Cloud (see `docs/superpowers/specs/2026-08-06-cuj1-cuj2-e2e-tests-design.md`
for why).

| # | Scenario | Test | Generates | Proves |
| :-- | :--- | :--- | :--- | :--- |
| 1 | Happy path | `test_happy_path_ingest_and_query` | 50 funnels (shown → selected → otp_entered → confirmed, ~20% OTP failure) with unique `user_id`/`application_id` | Exact `COUNT`/`SUM` against precomputed ground truth; point lookup by `application_id`; `DESCRIBE TABLE` schema integrity; the `table_semantics` CUJ1→CUJ2 handoff; query latency under budget |
| 2 | Schema/type boundaries | `test_boundary_cases_survive_round_trip` | Missing optional field, unicode + SQL-lookalike string, max-length string, unrounded float, timestamps on a `toYYYYMM()` partition boundary | Nulls stay `NULL`, unicode/long strings round-trip exactly, float precision survives, partition-boundary rows land in the correct month |
| 3 | Out-of-order / late-arriving | `test_out_of_order_events_query_correctly` | 5 events inserted in scrambled order relative to their timestamps | A time-ordered query returns correct chronological order regardless of insertion order |
| 4 | Duplicate / idempotency | `test_duplicate_events_are_not_silently_deduped` | 3 distinct events, 2 loaded twice with identical `id` | `MergeTree` does not dedupe on insert — `count()` shows duplication, `uniqExact(id)` shows the true distinct count |

## Known gaps this suite intentionally does not cover

- **Real ClickHouse Cloud.** By design decision, this suite never opens a
  network connection — it validates the tool-layer pipeline logic against a
  real embedded ClickHouse engine (`chdb`), not production latency/infra
  characteristics of the actual Cloud service.
- **`analysis_flow.run()`'s CUJ2 orchestration.** That entry point currently
  re-reads `events.ndjson` directly on several fallback paths rather than
  querying the ingested table (see design doc §1). This suite exercises
  `Tool_Analytics_Compute` directly instead, since that is the primitive that
  actually proves data landed correctly in storage.
- **LLM-driven schema reasoning and semantic retrieval ranking.** Both are
  gated behind `PYTEST_CURRENT_TEST`, which this suite leaves set except
  around the two storage calls that need it lifted — no real Gemini calls
  happen anywhere in this suite.
```

- [ ] **Step 2: Run the full E2E suite standalone**

Run: `.venv/bin/python -m pytest tests/e2e/ -v`
Expected: `5 passed`

- [ ] **Step 3: Run the entire project test suite to confirm zero regressions**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: every test that passed before this plan still passes; 5 additional E2E tests pass.

- [ ] **Step 4: Confirm cleanup actually leaves no residue**

Run: `ls src/atlys_agentic/specs/ | grep e2e_synth || echo "no leftover e2e_synth dirs"`
Expected: `no leftover e2e_synth dirs` — fixture teardown removed every synthetic spec directory created across the whole run.

- [ ] **Step 5: Commit**

```bash
git add docs/E2E_TEST_SCENARIOS.md
git commit -m "$(cat <<'EOF'
docs: add CUJ1->CUJ2 E2E test scenario matrix

Human-readable index of the 4 scenarios in tests/e2e/, what each
generates, and what it proves. Documents the deliberate gaps (no live
ClickHouse Cloud, no LLM calls) so the suite's coverage claims are
explicit rather than assumed.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Self-review notes

- **Spec coverage:** design doc §2 (harness) → Task 1. §3 scenario matrix rows 1-4 → Tasks 2-5. §4 assertions (correctness/schema/latency/correlation IDs) → distributed across Tasks 2-5, schema integrity explicitly in Task 2. §5 deliverables → all four files created exactly as named. §6 out-of-scope items → called out explicitly in Task 6's doc so they read as decisions, not omissions.
- **Placeholder scan:** no TBD/TODO; every step has runnable code or an exact command.
- **Type/interface consistency:** `pipeline_helpers.ingest`/`query` signatures defined in Task 1 are called identically (same parameter names, same return-tuple unpacking) in Tasks 2-5. `synthetic_spec()`'s `(spec_id, table_name)` return tuple is unpacked the same way in every task. `synthetic_data.*()`'s `(spec_md_text, events, expected)` return shape is consistent across all four generators.
