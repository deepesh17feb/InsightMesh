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
        trace_id="e2e",
    )

    return {"ddl": ddl, "ddl_result": ddl_result, "load_result": load_result, "semantics": semantics}


def query(sql: str, spec_id: str = "") -> tuple[list[dict], float]:
    """Run a CUJ2 analytics query through the real tool and return (rows, elapsed_seconds)."""
    start = time.perf_counter()
    result = tools.Tool_Analytics_Compute(sql, spec_id=spec_id)
    assert result["engine"] not in ("chdb_file", "fallback_empty"), (
        f"query bypassed persisted storage: engine={result['engine']!r}"
    )
    elapsed = time.perf_counter() - start
    return result["rows"], elapsed
