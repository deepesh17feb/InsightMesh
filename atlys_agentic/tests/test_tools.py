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
