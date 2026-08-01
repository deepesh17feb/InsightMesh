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
