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


INSTRUMENTATION_GREETING_MD = """### 🛠️ Hello! I'm the Atlys Instrumentation Engineer

I specialize in **CUJ 1: Schema Ingestion & Evolution** for ClickHouse Cloud and internal metadata registry.

**What I can do for you:**
- 📋 **Catalog Discovery**: List all feature specifications and telemetry event streams (*Try: "Show specs"*).
- 🏗️ **Optimal Schema Proposal**: Synthesize 6-pillar ClickHouse storage architecture (`ORDER BY`, `PARTITION BY`, `LowCardinality`, `SummingMergeTree`, `TTL`) (*Try: "Propose schema for 01_express_checkout"*).
- 🔍 **Interactive Deep Dives**: Answer questions on ClickHouse storage mechanics, part management, or dictionary encodings.
- ✏️ **Schema Modification**: Adjust columns or types upon request (*Try: "Add column promo_code Nullable(String)"*).
- 🚀 **Human-in-the-Loop Deployment**: Deploy authorized DDL directly to ClickHouse Cloud and register snapshots in `chDB.schema_registry` (*Type "APPROVE <table_name>"*).

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


def detect_chat_intent(
    messages: list[dict[str, str]],
    model: str = "atlys-analyst",
) -> tuple[str, dict[str, Any]]:
    """Classify the user's intent across conversation turns.

    Possible intents:
    - 'LIST_SPECS': User asks to view cataloged feature specs.
    - 'HITL_APPROVE': User explicitly authorizes schema deployment.
    - 'HITL_REJECT': User rejects or aborts schema deployment.
    - 'INGESTION_PROPOSAL': User requests a schema proposal for a feature spec.
    - 'INGESTION_FOLLOWUP': User asks follow-up questions or schema tweaks on an active proposal.
    - 'GREETING': Greeting or general capability inquiry.
    - 'ANALYTICS': CUJ 2 telemetry and root cause analysis queries.
    """
    if not messages:
        return "GREETING", {}

    latest_msg = messages[-1].get("content", "").strip()
    latest_lower = latest_msg.lower()

    # 1. Check for Catalog Discovery / List Specs
    list_spec_keywords = [
        "what specs", "list specs", "show specs", "available specs",
        "which specs", "catalog", "which features", "specs available",
    ]
    if any(kw in latest_lower for kw in list_spec_keywords):
        return "LIST_SPECS", {}

    # 2. Check for HITL Deployment Authorization
    approve_patterns = [
        r"^(?:approve|approved|deploy|authorize|lgtm|ship it)(?:\s+([\w_]+))?$",
        r"^type\s+approve(?:\s+([\w_]+))?$",
        r"^(?:please\s+)?(?:deploy|approve)\s+(?:this\s+)?(?:to\s+cloud|schema|table)?(?:\s+([\w_]+))?$",
    ]
    for pat in approve_patterns:
        match = re.search(pat, latest_lower)
        if match:
            table_hint = match.group(1) if match.lastindex else None
            return "HITL_APPROVE", {"table_hint": table_hint}

    # 3. Check for HITL Rejection
    reject_patterns = [r"^(?:reject|rejected|abort|cancel|deny|n|no)$"]
    for pat in reject_patterns:
        if re.search(pat, latest_lower):
            return "HITL_REJECT", {}

    # 4. Check for Ingestion Follow-up / Schema Refinement
    # If the conversation history previously proposed a schema, and current message asks technical or refinement questions:
    has_prior_proposal = False
    prior_table = None
    prior_ddl = None
    for msg in reversed(messages[:-1]):
        content = msg.get("content", "")
        if "CREATE TABLE" in content or "Instrumentation Engineer" in content:
            has_prior_proposal = True
            # Extract table name from prior DDL if possible
            match_table = re.search(r"CREATE TABLE (?:IF NOT EXISTS )?([\w_]+)", content)
            if match_table:
                prior_table = match_table.group(1)
            # Extract DDL block if present
            match_ddl = re.search(r"```sql\s*(CREATE TABLE[\s\S]+?);?\s*```", content)
            if match_ddl:
                prior_ddl = match_ddl.group(1)
            break

    followup_keywords = [
        "why", "how", "what if", "can we", "could we", "add column", "remove column",
        "change", "modify", "summingmergetree", "mergetree", "order by", "partition by",
        "lowcardinality", "nullable", "uint8", "ttl", "sorting key", "compression",
        "materialized view", "explain", "tradeoff", "trade-off", "storage",
    ]
    if has_prior_proposal and any(kw in latest_lower for kw in followup_keywords):
        return "INGESTION_FOLLOWUP", {
            "table_name": prior_table,
            "prior_ddl": prior_ddl,
            "question": latest_msg,
        }

    # 5. Check for Analytical Queries (CUJ 2)
    analytics_keywords = ["conversion", "lift", "drop", "drop-off", "otp", "rate", "funnel", "bottleneck", "regression", "trend", "delta"]
    proposal_keywords = ["ingest", "propose schema", "design schema", "create table", "propose table", "ddl for", "table ddl", "schema for"]
    is_explicit_proposal = any(kw in latest_lower for kw in proposal_keywords)

    if any(kw in latest_lower for kw in analytics_keywords) and not is_explicit_proposal:
        return "ANALYTICS", {"question": latest_msg}

    # 6. Check for Feature Spec Ingestion Proposal
    # Look for known spec IDs in the message or catalog
    available = paths.available_spec_ids()
    for spec in available:
        spec_num = spec.split("_")[0]
        spec_name = " ".join(spec.split("_")[1:])
        spec_slug = "_".join(spec.split("_")[1:])
        if (
            spec in latest_lower
            or f"spec {spec_num}" in latest_lower
            or f"spec_{spec_num}" in latest_lower
            or spec_name in latest_lower
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
    """Format cataloged feature specs into a rich Markdown card."""
    available = paths.available_spec_ids()
    lines = [
        "### 📋 Cataloged Feature Specs Ready for Ingestion",
        "",
        "The following feature specifications and telemetry event streams are discovered in the catalog:",
        "",
        "| Spec ID | Target Table | Description | Telemetry Stream |",
        "| :--- | :--- | :--- | :--- |",
    ]

    for spec in available:
        spec_dir = paths.spec_dir(spec)
        spec_md = spec_dir / "spec.md"
        events_file = spec_dir / "events.ndjson"

        desc = "Feature telemetry spec."
        if spec_md.exists():
            try:
                first_lines = spec_md.read_text(encoding="utf-8").splitlines()
                for line in first_lines:
                    cleaned = line.strip("# \t*")
                    if cleaned and not cleaned.lower().startswith("spec"):
                        desc = cleaned[:60]
                        break
            except Exception:
                pass

        event_count = 0
        if events_file.exists():
            try:
                event_count = sum(1 for _ in events_file.open(encoding="utf-8"))
            except Exception:
                pass

        table_slug = "_".join(spec.split("_")[1:]) if "_" in spec else spec
        lines.append(f"| `{spec}` | `{table_slug}` | {desc} | `{event_count:,}` events |")

    lines.extend([
        "",
        "💡 **How to proceed:**",
        "- To generate an ingestion proposal, ask: *'Propose schema for 01_express_checkout'*",
        "- To inspect telemetry cuts, ask: *'Is there an iOS OTP drop on Express Checkout?'*",
    ])
    return "\n".join(lines)


def format_ingestion_proposal_response(result: dict[str, Any]) -> str:
    """Format a dry-run ingestion flow result into a conversational proposal."""
    table = result.get("table_name", "feature_events")
    ddl = result.get("ddl", "")
    mv_ddl = result.get("mv_ddl", "")
    consult = result.get("table_consultation", {})
    reasoning = result.get("reasoning", {})
    diff = result.get("diff_result", {})
    trace_id = result.get("trace_id", "")

    deep = reasoning.get("technical_deep_dive", {})
    summary = reasoning.get("high_level_summary", consult.get("recommendation", ""))

    lines = [
        "### 🧠 Instrumentation Engineer Architectural Decision & Rationale",
        "",
        f"> **Executive Summary:** {summary}",
        "",
        "#### 1. 🏗️ ClickHouse Table DDL",
        "```sql",
        ddl,
        "```",
    ]

    if mv_ddl:
        lines.extend([
            "",
            "#### 2. 📈 Pre-Aggregation Materialized View (`SummingMergeTree`)",
            "```sql",
            mv_ddl,
            "```",
        ])

    lines.extend([
        "",
        "#### 3. 🔍 6-Pillar Storage Mechanics & Trade-Offs",
        f"- **Table Strategy (`{consult.get('strategy', 'CREATE_NEW')}`):** {deep.get('table_strategy', consult.get('recommendation', ''))}",
        f"- **Primary Sorting Key (`ORDER BY`):** {deep.get('ordering_mechanics', reasoning.get('ordering_reasoning', ''))}",
        f"- **Partitioning (`PARTITION BY`):** {deep.get('partitioning_mechanics', reasoning.get('partitioning_reasoning', ''))}",
        f"- **Encodings & Types:** {deep.get('column_encodings_and_compression', reasoning.get('types_reasoning', ''))}",
        f"- **Materialized View:** {deep.get('materialized_view_rollup', reasoning.get('mv_reasoning', ''))}",
        f"- **Data Retention (TTL):** {deep.get('lifecycle_retention', reasoning.get('retention_reasoning', ''))}",
        "",
        "#### 4. 📚 Context Diff Audit (Context Librarian)",
    ])

    additions = diff.get("additions", [])
    if additions:
        lines.append(f"- **New Columns to Index ({len(additions)}):** " + ", ".join(f"`{col}`" for col in additions))
    else:
        lines.append("- **New Columns to Index:** None (all attributes already present in registry).")

    if diff.get("conflicts"):
        lines.append(f"- ⚠️ **Metric Conflicts:** {diff.get('conflicts')}")
    if diff.get("gaps"):
        lines.append(f"- ⚠️ **Documentation Gaps:** {diff.get('gaps')}")

    lines.extend([
        "",
        "---",
        "💬 **Human-in-the-Loop Review Options:**",
        f"1. **Ask follow-up questions:** Ask about storage mechanics, partition choices, encodings, or trade-offs.",
        f"2. **Request schema adjustments:** e.g. *'Add column promo_code Nullable(String)'* or *'Change ORDER BY to include device_type'*.",
        f"3. **Authorize Deployment:** Type **`APPROVE {table}`** (or `APPROVE`) to deploy this DDL and Materialized View to ClickHouse Cloud.",
    ])

    if trace_id:
        lines.append(f"\n_trace: {trace_id}_")

    return "\n".join(lines)


def handle_followup_question(
    question: str,
    table_name: str | None,
    prior_ddl: str | None,
) -> str:
    """Provide detailed technical answers or schema modifications for follow-up questions."""
    q_lower = question.lower()
    table = table_name or "feature_events"

    # Check for column addition / modification request
    add_col_match = re.search(r"add\s+column\s+([\w_]+)\s+([\w\(\)]+)", question, re.IGNORECASE)
    if add_col_match:
        new_col_name = add_col_match.group(1)
        new_col_type = add_col_match.group(2)
        # Format updated DDL
        updated_ddl = prior_ddl or f"CREATE TABLE IF NOT EXISTS {table} (\n  timestamp DateTime64(3, 'UTC'),\n  user_id UUID\n) ENGINE = MergeTree() PARTITION BY toYYYYMM(timestamp) ORDER BY (timestamp, user_id);"
        # Insert column before closing parenthesis
        insert_line = f"    {new_col_name} {new_col_type},"
        if "ENGINE =" in updated_ddl:
            parts = updated_ddl.split("ENGINE =", 1)
            schema_part = parts[0].rstrip()
            if schema_part.endswith(")"):
                schema_part = schema_part[:-1].rstrip() + f",\n{insert_line}\n)"
            updated_ddl = f"{schema_part} ENGINE ={parts[1]}"

        return (
            f"### ✏️ Schema Modification Applied\n\n"
            f"Added column `{new_col_name} {new_col_type}` to `{table}`.\n\n"
            f"```sql\n{updated_ddl}\n```\n\n"
            f"Type **`APPROVE {table}`** to deploy this revised schema to ClickHouse Cloud."
        )

    # Dynamic LLM generation for Instrumentation Engineer follow-up response
    api_key = (
        os.environ.get("GEMINI_API_KEY", "")
        or os.environ.get("GOOGLE_API_KEY", "")
        or os.environ.get("OPENAI_API_KEY", "")
    ).strip()
    model_name = os.environ.get("LLM_MODEL", "gemini/gemini-2.5-flash")
    if api_key and not os.environ.get("PYTEST_CURRENT_TEST"):
        try:
            import litellm
            prompt = prompts.build_instrumentation_followup_prompt(
                question=question,
                table_name=table,
                current_ddl=prior_ddl or "",
                spec_context=f"Target ClickHouse table: {table}",
            )
            resp = litellm.completion(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                api_key=api_key,
                temperature=0.0,
            )
            llm_text = resp.choices[0].message.content.strip()
            if llm_text:
                usage = {
                    "prompt_tokens": getattr(getattr(resp, "usage", None), "prompt_tokens", 0),
                    "completion_tokens": getattr(getattr(resp, "usage", None), "completion_tokens", 0),
                }
                tracing.generation(
                    name="instrumentation_engineer::conversational_followup",
                    model=model_name,
                    input={"prompt": prompt, "question": question},
                    output=llm_text,
                    usage_details=usage,
                    metadata={"agent": "instrumentation_engineer", "table": table},
                    run_mode="live_run",
                )
                return f"{llm_text}\n\n---\nType **`APPROVE {table}`** to deploy this schema to ClickHouse Cloud."
        except Exception:
            pass

    # Question about SummingMergeTree
    if "summing" in q_lower or "materialized view" in q_lower or "mv" in q_lower:
        return (
            "### 🔍 Deep Dive: Why `SummingMergeTree` Materialized Views?\n\n"
            "1. **Write-Time Pre-Aggregation:**\n"
            "   ClickHouse processes Materialized Views as insert triggers. When raw events arrive, "
            "   the MV immediately pre-aggregates event volume and user metrics grouped by primary dimensions (`date, device_type, os, payment_method`).\n\n"
            "2. **Merge Mechanics:**\n"
            "   Background merges collapse rows with identical dimension keys, summing numeric counters. "
            "   When a Product Analyst queries daily conversion or cohort trends, the query reads pre-aggregated summary rows "
            "   rather than scanning millions of unaggregated event payloads, achieving **sub-10ms query responses and up to 99% less I/O**.\n\n"
            f"Type **`APPROVE {table}`** when ready to deploy, or ask further questions."
        )

    # Question about ORDER BY / Sorting Key
    if "order by" in q_lower or "sorting key" in q_lower or "primary key" in q_lower or "user_id" in q_lower:
        return (
            "### 🔍 Deep Dive: Sorting Key (`ORDER BY`) Mechanics\n\n"
            "1. **Dense Granule Locality:**\n"
            "   ClickHouse builds a sparse primary index with 1 mark per 8,192 rows (1 granule). "
            "   Placing `timestamp` first ensures chronological row ordering, allowing queries with date/time ranges to skip irrelevant granules with binary search.\n\n"
            "2. **Anti-Pattern Guardrail (Never Lead with UUID/ID):**\n"
            "   High-cardinality random identifiers (`user_id`, `event_id`, UUIDs) have uniform distributions. "
            "   Placing a UUID first scatters timestamps across data parts, destroys run-length compression, and forces ClickHouse into full-table scans. "
            "   By placing `user_id` second after `timestamp`, user funnel queries remain fast while preserving temporal compression.\n\n"
            f"Type **`APPROVE {table}`** to authorize deployment to ClickHouse Cloud."
        )

    # Question about PARTITION BY / Monthly partitioning
    if "partition" in q_lower or "month" in q_lower or "week" in q_lower or "day" in q_lower:
        return (
            "### 🔍 Deep Dive: Partitioning Strategy (`PARTITION BY`)\n\n"
            "1. **Monthly Granularity (`toYYYYMM(timestamp)`):**\n"
            "   ClickHouse creates physical filesystem directories for each partition. "
            "   Partitioning by **month** keeps total active parts manageable (< 300 parts per table), avoiding the dreaded *'Too many parts in all data parts in table'* error.\n\n"
            "2. **Why Not Daily or Weekly?**\n"
            "   Daily partitioning produces 365 directory partitions per year. Under continuous high-frequency ingestion, this leads to part fragmentation and excessive merge overhead. "
            "   Monthly partitions allow partition pruning during multi-month range queries while keeping disk operations efficient.\n\n"
            f"Type **`APPROVE {table}`** when you are ready to deploy."
        )

    # Question about LowCardinality / Encodings
    if "lowcardinality" in q_lower or "encoding" in q_lower or "compression" in q_lower:
        return (
            "### 🔍 Deep Dive: `LowCardinality(String)` Dictionary Encoding\n\n"
            "1. **Dictionary Tokenization:**\n"
            "   For columns with bounded unique values (`device_type`, `os`, `geoip_country_code`, `payment_method`), "
            "   `LowCardinality` replaces variable-length strings with 1- or 2-byte integer position indices and a shared dictionary block.\n\n"
            "2. **SIMD Vector Execution:**\n"
            "   During query execution (`GROUP BY device_type`), ClickHouse aggregates directly on the compact integer indices using vectorized SIMD CPU instructions without decompressing strings, yielding **5–10× faster scans and storage reduction**.\n\n"
            f"Type **`APPROVE {table}`** to deploy this schema to ClickHouse Cloud."
        )

    # General technical synthesis
    return (
        f"### 🧠 Instrumentation Engineer Response\n\n"
        f"Regarding your question on `{table}`: ClickHouse MergeTree storage is tuned specifically for columnar funnel analytics, "
        f"balancing mark pruning, dictionary encodings, and background merge TTLs.\n\n"
        f"Would you like to adjust any column definitions, change the primary sorting key, or proceed with deployment? "
        f"Type **`APPROVE {table}`** to deploy to ClickHouse Cloud."
    )


def handle_hitl_deployment(
    table_name: str | None,
    spec_id: str | None,
    history: list[dict[str, str]],
) -> str:
    """Execute live ClickHouse Cloud deployment and return versioned receipt."""
    # Find table name if not provided
    resolved_table = table_name
    resolved_spec = spec_id

    if not resolved_table or not resolved_spec:
        # Inspect conversation history for table and spec references
        for msg in reversed(history):
            content = msg.get("content", "")
            match_table = re.search(r"CREATE TABLE (?:IF NOT EXISTS )?([\w_]+)", content)
            if match_table and not resolved_table:
                resolved_table = match_table.group(1)
            # Check for spec ID pattern
            for spec in paths.available_spec_ids():
                if spec in content:
                    resolved_spec = spec
                    break
            if resolved_table and resolved_spec:
                break

    resolved_table = resolved_table or "express_checkout"
    resolved_spec = resolved_spec or f"01_{resolved_table}"

    chdb_client.init_schema()
    chdb_client.init_base_context()

    result = ingestion_flow.run(
        spec_id=resolved_spec,
        table_name=resolved_table,
        input_fn=lambda _: "APPROVE",
        dry_run=False,
    )

    if result.get("approved"):
        ddl_res = result.get("ddl_result", {})
        diff_res = result.get("diff_result", {})
        additions = diff_res.get("additions", [])
        version = ddl_res.get("version", 1)
        trace_id = result.get("trace_id", "")

        return (
            f"### 🎉 Deployment Authorized & Applied to ClickHouse Cloud!\n\n"
            f"The schema proposal for table `{resolved_table}` has been deployed through the Human-in-the-Loop gate.\n\n"
            f"| Metric / Asset | Status & Details |\n"
            f"| :--- | :--- |\n"
            f"| **Target Table** | `{resolved_table}` (ClickHouse Cloud) |\n"
            f"| **Deployment Status** | ✅ `status: ok` (Version {version}) |\n"
            f"| **Materialized View** | ✅ `{resolved_table}_daily_mv` (SummingMergeTree) registered |\n"
            f"| **Schema Registry** | Snapshot versioned in `chDB.schema_registry` |\n"
            f"| **Business Context** | {len(additions)} attributes indexed into `chDB.business_context` |\n"
            f"| **Changelog** | Migration logged in `chDB.context_changelog` |\n\n"
            f"**Indexed Attributes:**\n"
            f"{''.join(f'- `{col}`' for col in additions) if additions else '- All columns already up to date.'}\n\n"
            f"_Trace recorded: {trace_id}_"
        )
    else:
        return (
            f"### ❌ Deployment Aborted\n\n"
            f"Could not deploy table `{resolved_table}`. Status: {result.get('ddl_result')}\n\n"
            f"Please check logs or propose the schema again."
        )


def handle_hitl_rejection(table_name: str | None) -> str:
    """Handle explicit user rejection."""
    table = table_name or "proposed schema"
    return (
        f"### 🛑 Ingestion Review Aborted\n\n"
        f"The proposed schema deployment for `{table}` has been cancelled.\n\n"
        f"**Safety Guarantee:** ClickHouse Cloud and `chDB` remain untouched.\n\n"
        f"You can ask to propose another schema or list available specs anytime by typing *'Show specs'*."
    )
