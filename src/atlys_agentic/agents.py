"""Memory-free CrewAI agent personas.

No agent below sets CrewAI's native Short/Long/Entity memory — every context
an agent needs is passed in explicitly via task input or fetched at call time
through a tool, never recalled from opaque agent memory (see final_wiby.md
§2, the "no hidden LLM memory" principle).
"""
import os
from pathlib import Path

from crewai import Agent, LLM
from crewai.tools import tool
from dotenv import load_dotenv

from atlys_agentic import paths, tools

load_dotenv(paths.ATLYS_AGENTIC_DIR / "config" / ".env")


def llm() -> LLM:
    """Routes through LiteLLM explicitly (is_litellm=True) rather than
    CrewAI's native per-provider SDKs, so LiteLLM's Langfuse callback
    (see tracing.init_litellm_callbacks) actually sees every call."""
    model = os.environ.get("LLM_MODEL", "gemini/gemini-flash-latest")
    temperature = float(os.environ.get("LLM_TEMPERATURE", "0"))
    return LLM(model=model, is_litellm=True, temperature=temperature)


@tool("infer_schema")
def _infer_schema_tool(ndjson_path: str, spec_md_text: str, table_name: str) -> str:
    """Infer a production ClickHouse DDL from an NDJSON event sample and spec text."""
    return tools.Tool_Infer_Schema(Path(ndjson_path), spec_md_text, table_name)


@tool("generate_mv")
def _generate_mv_tool(table_name: str, ddl: str) -> str:
    """Generate a materialized view DDL for a table, if one is justified."""
    return tools.Tool_Generate_MV(table_name, ddl)


@tool("execute_ddl")
def _execute_ddl_tool(ddl: str, table_name: str, spec_id: str) -> dict:
    """Execute approved DDL on ClickHouse Cloud and mirror it to schema_registry."""
    return tools.Tool_Execute_DDL(ddl, table_name, spec_id)


@tool("context_diff")
def _context_diff_tool(new_table: str, new_columns: list[str]) -> dict:
    """Diff a new table's columns against business_context; surface conflicts and gaps."""
    return tools.Tool_Context_Diff(new_table, new_columns)


@tool("context_upsert")
def _context_upsert_tool(section: str, key: str, definition: str, agent: str, trace_id: str) -> int:
    """Write a new versioned business_context row and a context_changelog entry."""
    return tools.Tool_Context_Upsert(section, key, definition, agent, trace_id)


@tool("analytics_compute")
def _analytics_compute_tool(select_sql: str) -> dict:
    """Run a read-only SELECT against ClickHouse Cloud and return JSON rows."""
    return tools.Tool_Analytics_Compute(select_sql)


@tool("score_confidence")
def _score_confidence_tool(
    sample_size: int, effect_size_pct: float, known_issue_match: bool, cut_consistency: float
) -> dict:
    """Score confidence in an insight from sample size, effect size, known-issue match, cut consistency."""
    return tools.Tool_Score_Confidence(sample_size, effect_size_pct, known_issue_match, cut_consistency)


def build_instrumentation_engineer() -> Agent:
    return Agent(
        role="Senior ClickHouse DBA",
        goal="Turn a feature spec and raw event sample into production-grade DDL and materialized views.",
        backstory=(
            "You design ClickHouse schemas for high-volume event data. You never inherit the "
            "legacy id-first ORDER BY from older tables; you always lead with (timestamp, user_id)."
        ),
        tools=[_infer_schema_tool, _generate_mv_tool, _execute_ddl_tool],
        llm=llm(),
        memory=False,
        verbose=True,
    )


def build_context_librarian() -> Agent:
    return Agent(
        role="Business-Logic Gatekeeper and Auditor",
        goal="Keep business_context current, versioned, and free of unflagged contradictions.",
        backstory=(
            "You treat base_context.md with suspicion. Every new table or column gets diffed "
            "against the existing context; conflicts and gaps get surfaced, never silently ignored."
        ),
        tools=[_context_diff_tool, _context_upsert_tool],
        llm=llm(),
        memory=False,
        verbose=True,
    )


def build_product_analyst() -> Agent:
    return Agent(
        role="Principal Data Scientist",
        goal="Answer PM questions with an actionable insight, the why, a confidence score, and no DB jargon.",
        backstory=(
            "You never pull raw rows into context — you push aggregation into ClickHouse and "
            "interpret JSON summaries. You always cut by device, geo, and destination before concluding."
        ),
        tools=[_analytics_compute_tool, _score_confidence_tool],
        llm=llm(),
        memory=False,
        verbose=True,
    )
