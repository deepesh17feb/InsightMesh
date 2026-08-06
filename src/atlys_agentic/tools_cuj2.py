"""CUJ 2 Tools: Telemetry Analytics, Multi-Cut Diagnosis & PM Insight Synthesis."""
from __future__ import annotations

import json
import os

from atlys_agentic import ch_client, chdb_client, mcp_server, paths
from atlys_agentic.tools_common import (
    PlannedQuery,
    _assert_select_only,
    _columns_from_ddl,
    _flatten,
    _load_events,
)
from atlys_agentic.tools_cuj1 import Tool_Infer_Table_Name, Tool_Write_Table_Semantics


def Tool_Analytics_Compute(query: PlannedQuery | str | dict, spec_id: str = "") -> dict:
    """Execute analytical SELECT query pushing aggregation to ClickHouse Cloud or chDB."""
    sql = query.sql if isinstance(query, PlannedQuery) else (query.get("sql") if isinstance(query, dict) else str(query))
    _assert_select_only(sql)

    # 1. Try ClickHouse Cloud (primary execution plane)
    try:
        if not os.environ.get("PYTEST_CURRENT_TEST"):
            rows = mcp_server.execute_query(sql)
            if rows is not None and isinstance(rows, list):
                return {"query": sql, "rows": rows, "count": len(rows), "engine": "clickhouse_cloud"}
    except Exception:
        pass

    try:
        if not os.environ.get("PYTEST_CURRENT_TEST"):
            rows = ch_client.select(sql)
            if rows is not None and isinstance(rows, list):
                return {"query": sql, "rows": rows, "count": len(rows), "engine": "clickhouse_client"}
    except Exception:
        pass

    # 2. Try chDB directly over events.ndjson file if available
    ndjson_path = paths.events_ndjson(spec_id) if spec_id else None
    if not (ndjson_path and ndjson_path.exists()):
        for sid in paths.available_spec_ids():
            possible_path = paths.events_ndjson(sid)
            if possible_path.exists():
                tbl_part = sid.split("_", 1)[-1] if "_" in sid else sid
                if tbl_part in sql or sid in sql:
                    ndjson_path = possible_path
                    break

    if ndjson_path and ndjson_path.exists():
        try:
            import chdb
            import re
            file_sql = re.sub(
                r"\bFROM\s+([a-zA-Z0-9_]+)\b",
                f"FROM file('{ndjson_path}', 'JSONEachRow')",
                sql,
                flags=re.IGNORECASE,
            )
            raw = str(chdb.query(file_sql, "JSON"))
            if raw.strip():
                data = json.loads(raw).get("data", [])
                return {"query": sql, "rows": data, "count": len(data), "engine": "chdb_file"}
        except Exception:
            pass

    return {"query": sql, "rows": [], "count": 0, "engine": "fallback_empty"}


BASE_TABLE_SEMANTICS: list[dict[str, str]] = [
    {
        "table_name": "destination_card_clicked",
        "spec_id": "base_funnel",
        "description": "Top-of-funnel destination browse and card click events where users view visa requirements. Contains is_guest_browse (1 for unauthenticated guest user, 0 for authenticated registered user), destination, device, co_travelers, card_type, flow, and traffic attribution.",
        "concepts": "destination browse, destination card click, card clicked, browse volume, guest browse, is_guest_browse, unauthenticated guest, pre-purchase funnel, visa discovery, top of funnel, guest ratio",
    },
    {
        "table_name": "application_started",
        "spec_id": "base_funnel",
        "description": "Stage 1 of the core visa funnel where a user initiates an application for a destination. Records application_id, destination, co-travelers, and visa_issuance_eta_days.",
        "concepts": "application start, funnel start, visa application started, co-travelers, issuance eta, visa_issuance_eta_days, funnel stage 1",
    },
    {
        "table_name": "document_uploaded",
        "spec_id": "base_funnel",
        "description": "Stage 2 of the core visa funnel. Captures KYC passport upload, camera vs gallery capture mode, retry_count, and failed-attempt threshold breaches (is_crossed_failed_attempt_threshold).",
        "concepts": "document upload, passport upload, kyc document, passport capture quality, retry count, failed attempt threshold, capture mode, funnel stage 2",
    },
    {
        "table_name": "pay_now_clicked",
        "spec_id": "base_funnel",
        "description": "Checkout initiation click where a user taps pay now. Tracks payment sheet trigger, payment method, currency, discount codes, and order amount before payment completion.",
        "concepts": "pay now clicked, checkout initiation, payment sheet, checkout drop-off, payment method, checkout intent",
    },
    {
        "table_name": "purchase_completed",
        "spec_id": "base_funnel",
        "description": "Stage 4 final stage of the pre-purchase funnel. Records successful payment conversion, total revenue, processing fee, coupon campaign realized value, aov, order_id, and currency.",
        "concepts": "purchase completed, conversion, payment successful, order revenue, aov, discount amount, coupon realized value, paid application, funnel stage 4",
    },
    {
        "table_name": "search_typed",
        "spec_id": "base_funnel",
        "description": "Search event where user types destination search terms. Records search query terms, zero-result states (is_zero_results), character length, and autocomplete interactions.",
        "concepts": "destination search, search typed, top search terms, destination search terms, zero results, query length, search volume, destination_searched",
    },
    {
        "table_name": "landing_page_scrolled",
        "spec_id": "base_funnel",
        "description": "Discovery feed and landing page scrolling behavior. Captures scroll depth percentage, impression count, and destination feed exploration before card click.",
        "concepts": "landing page scrolled, feed scrolled, scroll depth, feed impressions, discovery feed exploration",
    },
    {
        "table_name": "auth_completed",
        "spec_id": "base_funnel",
        "description": "Authentication and sign-in completion events. Tracks authentication method (phone otp, google oauth, email), is_new_user signup vs signin, and auth latency.",
        "concepts": "user authenticated, auth completed, authentication method breakdown, sign in, sign up, new user, otp, oauth, phone auth",
    },
]


def Tool_Bootstrap_Base_Semantics(force: bool = False) -> dict:
    """Bootstrap foundation base tables and spec tables into chDB table_semantics and schema_registry at runtime."""
    chdb_client.init_schema()
    ddl_tables = paths.parse_ddl_tables()

    existing_rows = chdb_client.run("SELECT DISTINCT table_name FROM table_semantics")
    existing_tables = {r.get("table_name") for r in existing_rows if r.get("table_name")}

    seeded_base = []
    for item in BASE_TABLE_SEMANTICS:
        tname = item["table_name"]
        if force or tname not in existing_tables:
            cols = ddl_tables.get(tname, {}).get("columns", [])
            if not cols:
                cols = ["id", "timestamp", "user_id", "application_id", "device_type", "destination", "is_guest_browse"]
            Tool_Write_Table_Semantics(
                spec_id=item["spec_id"],
                table_name=tname,
                spec_text=f"{item['description']}\nConcepts: {item['concepts']}",
                column_names=cols,
                agent="context_agent",
            )
            # Register base table in schema_registry as well
            try:
                cols_json = json.dumps(cols).replace("'", "''")
                chdb_client.run(
                    f"""INSERT INTO schema_registry VALUES
                    ('{tname}', '{item["spec_id"]}', 1, 'MergeTree', '{cols_json}', '', now())""",
                    fmt="CSV",
                )
            except Exception:
                pass
            seeded_base.append(tname)

    # Seed spec tables if missing
    available_specs = paths.available_spec_ids()
    seeded_specs = []
    for sid in available_specs:
        spec_path = paths.spec_md(sid)
        spec_text = spec_path.read_text(encoding="utf-8") if spec_path.exists() else ""
        tbl_name = Tool_Infer_Table_Name(sid, spec_text)
        if force or tbl_name not in existing_tables:
            cols = []

            events_file = paths.events_ndjson(sid)
            if events_file.exists():
                try:
                    events = _load_events(events_file)
                    if events:
                        cols = list(_flatten(events[0]).keys())
                except Exception:
                    pass
            Tool_Write_Table_Semantics(
                spec_id=sid,
                table_name=tbl_name,
                spec_text=spec_text,
                column_names=cols,
                agent="context_agent",
            )
            seeded_specs.append(tbl_name)

    return {
        "status": "ok",
        "seeded_base_tables": seeded_base,
        "seeded_spec_tables": seeded_specs,
    }


def Tool_Load_Table_Semantics(candidate_tables: list[str]) -> dict:
    """Phase 1b: Context Agent loads columns + version, metric formulas, caveats, K1-K7, changelog, prior insights."""
    candidates_meta = {}
    for tbl in candidate_tables:
        reg_rows = chdb_client.run(
            f'SELECT "table" as table_name, version, ddl, columns_json, spec_id FROM schema_registry WHERE "table" = \'{tbl}\' ORDER BY version DESC LIMIT 1'
        )
        cols = []
        ver = 1
        spec_id = f"01_{tbl}"
        if reg_rows:
            r = reg_rows[0]
            ver = r.get("version", 1)
            spec_id = r.get("spec_id") or spec_id
            if r.get("columns_json"):
                try:
                    cols = json.loads(r["columns_json"])
                except Exception:
                    cols = _columns_from_ddl(r.get("ddl", ""))
            elif r.get("ddl"):
                cols = _columns_from_ddl(r.get("ddl", ""))

        if not cols:
            ddl_tables = paths.parse_ddl_tables()
            if tbl in ddl_tables:
                cols = ddl_tables[tbl].get("columns", [])
                spec_id = "base_funnel"

        if not cols:
            events_path = paths.events_ndjson(spec_id)
            if not events_path.exists():
                for sid in paths.available_spec_ids():
                    if tbl in sid:
                        events_path = paths.events_ndjson(sid)
                        spec_id = sid
                        break
            if events_path.exists():
                try:
                    events = _load_events(events_path)
                    if events:
                        cols = list(_flatten(events[0]).keys())
                except Exception:
                    pass

        if not cols:
            cols = ["timestamp", "user_id", "device_type", "os", "geoip_country_code", "destination", "event", "is_guest"]

        # Read business_context
        bc_rows = chdb_client.run("SELECT section, key, definition, version FROM business_context ORDER BY version DESC")
        metrics = []
        caveats = []
        known_issues = []
        for r in bc_rows:
            sec = (r.get("section") or "").lower()
            key = (r.get("key") or "").strip()
            defn = (r.get("definition") or "").strip()
            if "caveat" in sec or "caveat" in defn.lower():
                caveats.append(f"{key}: {defn}")
            elif "known" in sec or key.startswith("K"):
                known_issues.append(f"{key}: {defn}")
            elif "metric" in sec or "conversion" in key.lower() or "formula" in defn.lower():
                metrics.append(f"{key}: {defn}")

        # Check prior insights for this table
        prior_insights = chdb_client.run(
            f"SELECT finding_key, spec_id, question, confidence, answer_md, created_at FROM insights WHERE finding_key LIKE '{tbl}::%' OR spec_id = '{spec_id}' ORDER BY created_at DESC LIMIT 3"
        )

        candidates_meta[tbl] = {
            "table_name": tbl,
            "spec_id": spec_id,
            "version": ver,
            "columns": cols,
            "metrics": metrics[:10],
            "caveats": caveats[:5],
            "known_issues": known_issues[:10],
            "prior_insights": prior_insights,
        }
    return candidates_meta
