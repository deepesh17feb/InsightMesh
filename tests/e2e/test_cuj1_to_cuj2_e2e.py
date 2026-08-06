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
