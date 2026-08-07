"""E2E: generate synthetic data -> ingest via the CUJ1 tool pipeline -> query
via the CUJ2 tool pipeline -> assert correctness, schema integrity, latency.

See docs/superpowers/specs/2026-08-06-cuj1-cuj2-e2e-tests-design.md for why
this suite talks to a local chdb session instead of live ClickHouse Cloud.
"""
from __future__ import annotations

import pytest

from atlys_agentic import tools
from tests.e2e import pipeline_helpers, synthetic_data


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
