"""Memory-free CrewAI agent personas.

Every context an agent needs is passed in explicitly via task input or fetched
at call time through a tool, never recalled from opaque agent memory. That
guarantee is enforced by the deterministic flows in flows/ — no Crew is ever
kicked off, so there is no agent loop to accumulate memory. memory=False below
is belt-and-braces for the day one is.
"""
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

from atlys_agentic import paths, tools

load_dotenv(paths.ATLYS_AGENTIC_DIR / "config" / ".env", override=True)
load_dotenv(paths.REPO_ROOT / ".env", override=True)

from crewai import Agent, LLM
from crewai.tools import tool


def llm() -> LLM:
    """Routes through LiteLLM explicitly (is_litellm=True) rather than
    CrewAI's native per-provider SDKs, for consistent provider routing across
    every call site. Langfuse tracing is explicit at each call site via
    tracing.generation()/tracing.span(), not via a LiteLLM callback — see
    tracing.py's module docstring."""
    model = os.environ.get("LLM_MODEL", "gemini/gemini-3-flash-preview")
    temperature = float(os.environ.get("LLM_TEMPERATURE", "0"))
    return LLM(model=model, is_litellm=True, temperature=temperature)


@tool("consult_internal_tables")
def _consult_internal_tables_tool(spec_id: str, candidate_columns: list[str], table_name: str) -> dict:
    """Consult chDB schema_registry and business_context to inspect existing tables and determine strategy (CREATE_NEW, ALTER_EXISTING, REUSE_EXISTING)."""
    return tools.Tool_Consult_Internal_Tables(spec_id, candidate_columns, table_name)


@tool("infer_schema")
def _infer_schema_tool(ndjson_path: str, spec_md_text: str, table_name: str) -> str:
    """Infer a production ClickHouse DDL from an NDJSON event sample and spec text."""
    return tools.Tool_Infer_Schema(Path(ndjson_path), spec_md_text, table_name)


@tool("generate_mv")
def _generate_mv_tool(table_name: str, ddl: str) -> str:
    """Generate a materialized view DDL for a table, if one is justified."""
    return tools.Tool_Generate_MV(table_name, ddl)


@tool("explain_schema_rationale")
def _explain_schema_rationale_tool(table_name: str, ddl: str, mv_ddl: str, consultation: dict, spec_text: str) -> dict:
    """Explain the 6-pillar ClickHouse storage mechanics rationale (ORDER BY, PARTITION BY, LowCardinality, MV, TTL)."""
    return tools.Tool_Explain_Schema_Rationale(table_name, ddl, mv_ddl, consultation, spec_text)


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


def load_agents_config() -> dict:
    """Load agent personas (role, goal, backstory, params) from config/agents.yaml."""
    with open(paths.AGENTS_CONFIG_YAML, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _build(persona: str, agent_tools: list) -> Agent:
    cfg = load_agents_config()[persona]
    return Agent(
        role=cfg["role"],
        goal=cfg["goal"],
        backstory=cfg["backstory"].strip(),
        tools=agent_tools,
        llm=llm(),
        memory=False,
        verbose=cfg.get("verbose", True),
        allow_delegation=cfg.get("allow_delegation", False),
        max_iter=cfg.get("max_iter", 5),
    )


def build_instrumentation_engineer() -> Agent:
    return _build("instrumentation_engineer", [_infer_schema_tool, _generate_mv_tool, _explain_schema_rationale_tool])


def build_context_librarian() -> Agent:
    return _build("context_librarian", [_consult_internal_tables_tool, _context_diff_tool, _execute_ddl_tool, _context_upsert_tool])


def build_product_analyst() -> Agent:
    return _build("product_analyst", [_analytics_compute_tool, _score_confidence_tool])


def build_query_architect() -> Agent:
    return _build("query_architect", [])
