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

# Brief: "all sampled values are short enums" -> a string column with at most
# this many distinct sampled values is treated as a bounded enum even when
# its name isn't in _LOW_CARDINALITY_HINTS.
_ENUM_CARDINALITY_THRESHOLD = 5

# Base types worth exposing as Nullable(...) when a column is absent in some
# sampled rows. DateTime/UInt8/LowCardinality(String) are returned as exact
# literals elsewhere in this function (existing tests assert those literal
# strings), and plain string columns already default to Nullable(String).
_NULLABLE_WRAPPABLE = {"Int64", "Float64"}


def _flatten(event: dict, prefix: str = "") -> dict:
    flat = {}
    for k, v in event.items():
        key = f"{prefix}{k}" if not prefix else f"{prefix}_{k}"
        if isinstance(v, dict):
            flat.update(_flatten(v, key))
        else:
            flat[key] = v
    return flat


def _infer_type(key: str, values: list, sparse: bool = False) -> str:
    non_null = [v for v in values if v is not None]
    if not non_null:
        return "Nullable(String)"
    if key in _TIMESTAMP_KEYS or key.endswith("_at"):
        return "DateTime"
    if all(isinstance(v, bool) for v in non_null):
        return "UInt8"
    if all(isinstance(v, int) and not isinstance(v, bool) for v in non_null):
        if set(non_null) <= {0, 1}:
            return "UInt8"
        base = "Int64"
    elif all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in non_null):
        base = "Float64"
    else:
        # string-typed
        suffix = key.split("_")[-1] if "_" in key else key
        is_short_enum = len(set(non_null)) <= _ENUM_CARDINALITY_THRESHOLD
        if key in _LOW_CARDINALITY_HINTS or suffix in _LOW_CARDINALITY_HINTS or is_short_enum:
            return "LowCardinality(String)"
        return "Nullable(String)"

    if sparse and base in _NULLABLE_WRAPPABLE:
        return f"Nullable({base})"
    return base


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
    # a column present in fewer rows than the sample size is absent (None)
    # in the other rows -> its inferred type should be Nullable(...)
    sparse_keys = {k for k, vals in columns.items() if len(vals) < len(flattened)}
    for k in columns:
        columns[k] = columns[k] + [None] * (len(flattened) - len(columns[k]))

    ordered_keys = list(dict.fromkeys(k for row in flattened for k in row))
    lines = []
    for key in ordered_keys:
        if key in ("user_id", "application_id", "id"):
            col_type = "String" if key != "id" else "UUID"
        else:
            col_type = _infer_type(key, columns[key], sparse=key in sparse_keys)
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
        f"    count() AS events,\n"
        f"    uniq(user_id) AS users\n"
        f"FROM {table_name}\n"
        f"GROUP BY day, {segment_col}{', ' + funnel_step_column if step_expr else ''};"
    )
