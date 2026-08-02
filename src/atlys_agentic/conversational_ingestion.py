"""Conversational Ingestion and Human-in-the-Loop Handler for LibreChat.

Provides conversational schema proposal, 6-pillar architectural reasoning,
interactive follow-up explanation, schema refinement, and in-chat HITL deployment
for CUJ 1 within LibreChat and OpenAI-compatible chat interfaces.
"""
from __future__ import annotations

import os
import re
from typing import Any

from atlys_agentic import chdb_client, paths, prompts, tools, tracing
from atlys_agentic.flows import ingestion_flow

PROPOSAL_TOKEN_REGEX = re.compile(
    r"<!--\s*atlys:proposal\s+spec_id=(?P<spec_id>[\w_]+)\s+table=(?P<table>[\w_]+)(?:\s+trace=(?P<trace>[\w-]+))?\s*-->",
    re.IGNORECASE,
)

INSTRUMENTATION_GREETING_MD = """### 🛠️ Hello! I'm the Atlys Instrumentation Engineer

I specialize in **CUJ 1: Schema Ingestion & Evolution** for ClickHouse Cloud and the internal context layer.

**What I can do for you:**
- 📋 **Catalog Discovery**: List all feature specifications and telemetry event streams (*Try: "what specs are available?"*).
- 🏗️ **Optimal Schema Proposal**: Synthesize 6-pillar ClickHouse storage architecture (`ORDER BY`, `PARTITION BY`, `LowCardinality`, `SummingMergeTree`, `TTL`) (*Try: "ingest 01_express_checkout"*).
- 🔍 **Interactive Deep Dives**: Answer questions on ClickHouse storage mechanics, part management, or dictionary encodings (*Try: "why not order by application_id first?"*).
- ✏️ **Schema Modification**: Adjust columns or types upon request (*Try: "Add column promo_code Nullable(String)"*).
- 🚀 **Human-in-the-Loop Deployment**: Deploy authorized DDL directly to ClickHouse Cloud, load event samples, and sync context (*Reply "APPROVE"*).

*For funnel analytics, conversion drop investigations, or telemetry anomaly diagnosis (CUJ 2), please select the **Atlys Product Analyst** model.*"""

INSTRUMENTATION_SCOPE_NOTICE_MD = """### ℹ️ Instrumentation Engineer Scope Notice

I am the **Atlys Instrumentation Engineer**, dedicated to **CUJ 1: Schema Ingestion, ClickHouse Storage Architecture & DDL Deployment**.

Your query appears to be an analytical telemetry or funnel diagnostic question (CUJ 2).

👉 **How to proceed:**
Please select **Atlys Product Analyst** (`atlys-analyst`) from the model dropdown in LibreChat to investigate conversion drops, segment cuts, and telemetry anomalies."""

ANALYST_SCOPE_NOTICE_MD = """### ℹ️ Product Analyst Scope Notice

I am the **Atlys Product Analyst**, dedicated to **CUJ 2: Telemetry Diagnostics, Funnel Analysis & Root Cause Investigation**.

Your request appears to be a schema proposal or table ingestion request (CUJ 1).

👉 **How to proceed:**
Please select **Atlys Instrumentation Engineer** (`atlys-instrumentation`) from the model dropdown in LibreChat to generate ClickHouse DDL, review storage mechanics, and authorize schema deployments."""


def extract_proposal_token_from_history(messages: list[dict[str, str]]) -> dict[str, str] | None:
    """Extract machine-readable proposal token from LibreChat message history (docs/CUJ1.md Section 6)."""
    for msg in reversed(messages):
        content = msg.get("content", "")
        match = PROPOSAL_TOKEN_REGEX.search(content)
        if match:
            return {
                "spec_id": match.group("spec_id"),
                "table_name": match.group("table"),
                "trace_id": match.group("trace") or "",
            }
    return None


def detect_chat_intent(
    messages: list[dict[str, str]],
    model: str = "atlys-analyst",
) -> tuple[str, dict[str, Any]]:
    """Classify the user's intent across conversation turns per docs/CUJ1.md Section 6."""
    if not messages:
        return "GREETING", {}

    latest_msg = messages[-1].get("content", "").strip()
    latest_lower = latest_msg.lower()

    # 1. Check for Catalog Discovery / List Specs
    list_spec_keywords = [
        "what specs", "list specs", "show specs", "available specs",
        "which specs", "catalog", "which features", "specs available",
        "what specs are available",
    ]
    if any(kw in latest_lower for kw in list_spec_keywords):
        return "LIST_SPECS", {}

    # Check for proposal token in message history
    proposal_token_data = extract_proposal_token_from_history(messages[:-1])

    # 2. Check for HITL Deployment Authorization (strict keywords per locked spec)
    approve_patterns = [
        r"^(?:approve|approved|deploy|authorize|lgtm|ship it)(?:\s+([\w_]+))?$",
        r"^type\s+approve(?:\s+([\w_]+))?$",
    ]
    for pat in approve_patterns:
        match = re.search(pat, latest_lower)
        if match:
            table_hint = match.group(1) if match.lastindex else None
            data = {"table_hint": table_hint}
            if proposal_token_data:
                data.update(proposal_token_data)
            return "HITL_APPROVE", data

    # 3. Check for HITL Rejection
    reject_patterns = [r"^(?:reject|rejected|abort|cancel|deny|n|no)$"]
    for pat in reject_patterns:
        if re.search(pat, latest_lower):
            data = {}
            if proposal_token_data:
                data.update(proposal_token_data)
            return "HITL_REJECT", data

    # 4. Check for Ingestion Follow-up / Schema Refinement
    if proposal_token_data:
        followup_keywords = [
            "why", "how", "what if", "can we", "could we", "add column", "remove column",
            "change", "modify", "summingmergetree", "mergetree", "order by", "partition by",
            "lowcardinality", "nullable", "uint8", "ttl", "sorting key", "compression",
            "materialized view", "explain", "tradeoff", "trade-off", "storage", "application_id",
            "user_id", "timestamp",
        ]
        if any(kw in latest_lower for kw in followup_keywords):
            return "INGESTION_FOLLOWUP", {
                "spec_id": proposal_token_data["spec_id"],
                "table_name": proposal_token_data["table_name"],
                "trace_id": proposal_token_data["trace_id"],
                "question": latest_msg,
            }

    # 5. Check for Analytical Queries (CUJ 2)
    analytics_keywords = ["conversion", "lift", "drop", "drop-off", "otp", "rate", "funnel", "bottleneck", "regression", "trend", "delta"]
    proposal_keywords = ["ingest", "propose schema", "design schema", "create table", "propose table", "ddl for", "table ddl", "schema for"]
    is_explicit_proposal = any(kw in latest_lower for kw in proposal_keywords)

    if any(kw in latest_lower for kw in analytics_keywords) and not is_explicit_proposal:
        return "ANALYTICS", {"question": latest_msg}

    # 6. Check for Feature Spec Ingestion Proposal
    available = paths.available_spec_ids()
    for spec in available:
        spec_num = spec.split("_")[0]
        spec_slug = "_".join(spec.split("_")[1:])
        if (
            spec in latest_lower
            or f"spec {spec_num}" in latest_lower
            or f"spec_{spec_num}" in latest_lower
            or spec_slug in latest_lower
        ):
            if is_explicit_proposal or any(kw in latest_lower for kw in ["ingest", "schema", "table", "ddl", "propose"]) or model == "atlys-instrumentation":
                return "INGESTION_PROPOSAL", {"spec_id": spec, "table_name": spec_slug}

    # Generic ingestion proposal keywords with spec references
    if is_explicit_proposal or any(kw in latest_lower for kw in ["ingest spec", "propose schema", "design schema", "create table for"]):
        inferred_table = tools.infer_table_name_from_spec_or_id(latest_msg)
        return "INGESTION_PROPOSAL", {"spec_id": inferred_table, "table_name": inferred_table}

    # 7. Check for Greetings / General info
    if latest_lower in ["hi", "hello", "hey", "help", "who are you", "what can you do"]:
        return "GREETING", {}

    # 8. Default to Analytics (CUJ 2)
    return "ANALYTICS", {"question": latest_msg}


def format_available_specs_card() -> str:
    """Format cataloged feature specs into the exact table format per docs/CUJ1.md Section 9."""
    available = paths.available_spec_ids()
    lines = [
        "### Cataloged Feature Specs",
        "",
        "| Spec | Table | Status |",
        "| :--- | :--- | :--- |",
    ]

    for spec in available:
        table_slug = "_".join(spec.split("_")[1:]) if "_" in spec else spec
        # Check if table already registered in schema_registry
        is_registered = False
        try:
            reg = chdb_client.run(f'SELECT "table" FROM schema_registry WHERE "table" = \'{table_slug}\'')
            is_registered = bool(reg)
        except Exception:
            pass
        status_str = "instrumented" if is_registered else "not yet instrumented"
        lines.append(f"| `{spec}` | `{table_slug}` | {status_str} |")

    lines.extend([
        "",
        'Say *"ingest 01_express_checkout"* to design a schema.',
    ])
    return "\n".join(lines)


def handle_followup_question(
    question: str,
    table_name: str | None,
    spec_id: str | None = None,
    trace_id: str | None = None,
) -> str:
    """Provide detailed technical answers or schema modifications for follow-up questions."""
    q_lower = question.lower()
    table = table_name or "express_checkout"
    spec = spec_id or f"01_{table}"
    trace = trace_id or tracing.new_trace(spec, run_mode="live_run")

    token = f"<!-- atlys:proposal spec_id={spec} table={table} trace={trace} -->"

    # Specific follow-up: why not order by application_id first? (docs/CUJ1.md Section 9)
    if "application_id" in q_lower:
        return (
            f"`application_id` is `Nullable(String)` in this event stream — it is absent on "
            f"`{table}_shown`, present only once an application exists. A nullable leading key "
            f"forces ClickHouse to sort nulls into their own range, which fragments the primary index and "
            f"makes time-range pruning ineffective for the exact queries the analyst runs.\n\n"
            f"It is a good *secondary* key if you need per-application drill-down. Say "
            f'*"add application_id after user_id"* and I will regenerate the proposal.\n\n'
            f"🔍 Trace: https://us.cloud.langfuse.com/trace/{trace}\n\n"
            f"{token}"
        )

    # Dynamic LLM generation for Instrumentation Engineer follow-up response
    api_key = (
        os.environ.get("GEMINI_API_KEY", "")
        or os.environ.get("GOOGLE_API_KEY", "")
        or os.environ.get("OPENAI_API_KEY", "")
    ).strip()
    model_name = os.environ.get("LLM_MODEL", "gemini/gemini-3-flash-preview")
    if api_key and not os.environ.get("PYTEST_CURRENT_TEST"):
        try:
            import litellm
            prompt = prompts.build_instrumentation_followup_prompt(
                question=question,
                table_name=table,
                current_ddl="",
                spec_context=f"Target ClickHouse table: {table}, spec: {spec}",
            )
            resp = litellm.completion(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                api_key=api_key,
                temperature=0.0,
            )
            llm_text = resp.choices[0].message.content.strip()
            if llm_text:
                tracing.generation(
                    name="instrumentation_agent::followup_response",
                    model=model_name,
                    input={"question": question, "table": table, "spec": spec},
                    output=llm_text,
                    metadata={"agent": "instrumentation_agent", "why": "answered schema deep dive follow-up"},
                    run_mode="librechat_client",
                )
                return f"{llm_text}\n\n🔍 Trace: https://us.cloud.langfuse.com/trace/{trace}\n\n{token}"
        except Exception:
            pass

    # Question about SummingMergeTree
    if "summing" in q_lower or "materialized view" in q_lower or "mv" in q_lower:
        return (
            "### 🔍 Deep Dive: Why `SummingMergeTree` Materialized Views?\n\n"
            "1. **Write-Time Pre-Aggregation:**\n"
            "   ClickHouse processes Materialized Views as insert triggers. When raw events arrive, "
            "   the MV immediately pre-aggregates event volume and user metrics grouped by primary dimensions (`day, device_type, geoip_country_code`).\n\n"
            "2. **Merge Mechanics:**\n"
            "   Background merges collapse rows with identical dimension keys, summing numeric counters. "
            "   When a Product Analyst queries daily conversion or cohort trends, the query reads pre-aggregated summary rows "
            "   rather than scanning millions of unaggregated event payloads, achieving **sub-10ms query responses and up to 99% less I/O**.\n\n"
            f"🔍 Trace: https://us.cloud.langfuse.com/trace/{trace}\n\n"
            f"{token}"
        )

    # General technical synthesis
    return (
        f"### 🧠 Instrumentation Engineer Response\n\n"
        f"Regarding your question on `{table}`: ClickHouse MergeTree storage is tuned specifically for columnar funnel analytics, "
        f"balancing mark pruning, dictionary encodings, and background merge TTLs.\n\n"
        f"Would you like to adjust any column definitions, change the primary sorting key, or proceed with deployment? "
        f"Reply **`APPROVE`** to deploy to ClickHouse Cloud.\n\n"
        f"🔍 Trace: https://us.cloud.langfuse.com/trace/{trace}\n\n"
        f"{token}"
    )


def handle_hitl_deployment(
    table_name: str | None,
    spec_id: str | None,
    history: list[dict[str, str]],
) -> str:
    """Execute live ClickHouse Cloud deployment and return versioned receipt per docs/CUJ1.md Section 9."""
    token_data = extract_proposal_token_from_history(history)
    resolved_table = (token_data.get("table_name") if token_data else None) or table_name or "express_checkout"
    resolved_spec = (token_data.get("spec_id") if token_data else None) or spec_id or f"01_{resolved_table}"
    resolved_trace = (token_data.get("trace_id") if token_data else None) or ""

    chdb_client.init_schema()
    chdb_client.init_base_context()

    state = ingestion_flow.deploy_approved_proposal(
        spec_id=resolved_spec,
        table_name=resolved_table,
        trace_id=resolved_trace,
    )
    return state.receipt_md


def handle_hitl_rejection(
    table_name: str | None,
    history: list[dict[str, str]] | None = None,
) -> str:
    """Handle explicit user rejection per docs/CUJ1.md Section 10."""
    token_data = extract_proposal_token_from_history(history or [])
    resolved_table = (token_data.get("table_name") if token_data else None) or table_name or "express_checkout"
    resolved_spec = (token_data.get("spec_id") if token_data else None) or f"01_{resolved_table}"
    trace_id = (token_data.get("trace_id") if token_data else None) or "abc123def456"

    return (
        f"### 🛑 Ingestion aborted — `{resolved_table}`\n\n"
        "Nothing was written. ClickHouse Cloud and chDB are untouched, no rows loaded, no registry "
        "version created.\n\n"
        "The proposal is still in this conversation if you want to revise it — say what you would "
        f"change, or `ingest {resolved_spec}` to start again.\n\n"
        f"🔍 Trace: https://us.cloud.langfuse.com/trace/{trace_id}"
    )
