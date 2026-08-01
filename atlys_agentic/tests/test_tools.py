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


def test_infer_schema_sparse_column_becomes_nullable(express_checkout_ndjson):
    # shown_amount/payment_latency_ms only appear on one of the two event
    # types in the fixture -> they must be Nullable(...), not plain types.
    ddl = tools.Tool_Infer_Schema(express_checkout_ndjson, "spec text", "express_checkout")
    assert "shown_amount Nullable(Float64)" in ddl
    assert "payment_latency_ms Nullable(Int64)" in ddl


@pytest.fixture
def bugfix_ndjson(tmp_path):
    events = [
        {
            "event": "express_checkout_shown",
            "timestamp": "2026-04-01T10:00:00",
            "user_id": "u1",
            "retry_count": 0,
            "plan_tier": "free",
        },
        {
            "event": "express_payment_confirmed",
            "timestamp": "2026-04-01T10:01:00",
            "user_id": "u1",
            "retry_count": 1,
            "plan_tier": "pro",
        },
        {
            "event": "express_payment_confirmed",
            "timestamp": "2026-04-01T10:02:00",
            "user_id": "u2",
            "retry_count": 1,
            "plan_tier": "pro",
        },
    ]
    p = tmp_path / "bugfix_events.ndjson"
    p.write_text("\n".join(json.dumps(e) for e in events))
    return p


def test_infer_schema_zero_one_int_gets_uint8_without_naming_qualifier(bugfix_ndjson):
    # "retry_count" has no is_/has_ prefix; brief's rule is unqualified.
    ddl = tools.Tool_Infer_Schema(bugfix_ndjson, "spec text", "express_checkout")
    assert "retry_count UInt8" in ddl


def test_infer_schema_short_enum_string_gets_low_cardinality_without_name_hint(bugfix_ndjson):
    # "plan_tier" isn't in _LOW_CARDINALITY_HINTS, but only has 2 distinct
    # sampled values -> should still be classified as LowCardinality(String).
    ddl = tools.Tool_Infer_Schema(bugfix_ndjson, "spec text", "express_checkout")
    assert "plan_tier LowCardinality(String)" in ddl
