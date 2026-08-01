"""Memory-free CrewAI agent personas.

No agent below sets CrewAI's native Short/Long/Entity memory — every context
an agent needs is passed in explicitly via task input or fetched at call time
through a tool, never recalled from opaque agent memory (see final_wiby.md
§2, the "no hidden LLM memory" principle).
"""
import os
from pathlib import Path

from dotenv import load_dotenv

from atlys_agentic import paths, tools

load_dotenv(paths.ATLYS_AGENTIC_DIR / "config" / ".env")
load_dotenv(paths.REPO_ROOT / ".env")

try:
    from crewai import Agent, LLM
    from crewai.tools import tool
except ImportError:  # pragma: no cover
    class LLM:  # type: ignore
        def __init__(self, model: str = "", is_litellm: bool = True, temperature: float = 0.0):
            self.model = model
            self.is_litellm = is_litellm
            self.temperature = temperature

    def tool(name: str):  # type: ignore
        def decorator(fn):
            fn.name = name
            return fn
        return decorator

    class Agent:  # type: ignore
        def __init__(
            self,
            role: str = "",
            goal: str = "",
            backstory: str = "",
            tools: list = None,
            llm=None,
            memory: bool = False,
            verbose: bool = True,
            allow_delegation: bool = False,
            max_iter: int = 5,
            **kwargs,
        ):
            self.role = role
            self.goal = goal
            self.backstory = backstory
            self.tools = tools or []
            self.llm = llm
            self.memory = memory
            self.verbose = verbose
            self.allow_delegation = allow_delegation
            self.max_iter = max_iter


def llm() -> LLM:
    """Routes through LiteLLM explicitly (is_litellm=True) rather than
    CrewAI's native per-provider SDKs, so LiteLLM's Langfuse callback
    (see tracing.init_litellm_callbacks) actually sees every call."""
    model = os.environ.get("LLM_MODEL", "gemini/gemini-flash-latest")
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
    """Execute approved DDL on ClickHouse Cloud only — does not touch chDB; see register_schema_version."""
    return tools.Tool_Execute_DDL(ddl, table_name, spec_id)


@tool("register_schema_version")
def _register_schema_version_tool(ddl: str, table_name: str, spec_id: str) -> dict:
    """Mirror an already-executed DDL into chDB.schema_registry with an incremented version."""
    return tools.Tool_Register_Schema_Version(ddl, table_name, spec_id)


@tool("context_diff")
def _context_diff_tool(new_table: str, new_columns: list[str]) -> dict:
    """Diff a new table's columns against business_context; surface conflicts and gaps."""
    return tools.Tool_Context_Diff(new_table, new_columns)


@tool("context_upsert")
def _context_upsert_tool(section: str, key: str, definition: str, agent: str, trace_id: str) -> int:
    """Write a new versioned business_context row only — does not touch context_changelog; see append_context_changelog."""
    return tools.Tool_Context_Upsert(section, key, definition, agent, trace_id)


@tool("append_context_changelog")
def _append_context_changelog_tool(key: str, before: str, after: str, agent: str, trace_id: str) -> None:
    """Append one immutable audit-trail row to context_changelog."""
    return tools.Tool_Append_Context_Changelog(key, before, after, agent, trace_id)


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


@tool("text_to_sql")
def _text_to_sql_tool(question: str, table_name: str, columns: list[str], mandatory_dims: list[str]) -> dict:
    """Translate a PM question into the SELECT queries needed to answer it: one per mandatory cut dimension, plus an optional question-targeted extra."""
    from atlys_agentic import query_architect
    role_cfg = get_role_config("query_architect")
    queries = query_architect.generate_sql(role_cfg, question, table_name, columns, tuple(mandatory_dims))
    return {"queries": queries}


_DEFAULT_AGENTS_CONFIG = {
    "instrumentation_engineer": {
        "role": "Staff ClickHouse Systems & Telemetry Architect",
        "goal": (
            "Transform product feature specifications and raw telemetry event streams into production-grade, "
            "high-performance ClickHouse DDL and high-leverage Materialized Views with zero schema anti-patterns."
        ),
        "backstory": (
            "You are a veteran ClickHouse database architect specializing in high-throughput event telemetry "
            "and real-time analytical engines. Always lead ordering keys with query filter predicates (timestamp, user_id). "
            "Always partition raw tables by toYYYYMM(timestamp), strictly enforce LowCardinality types, apply 12-month TTLs, "
            "and only generate Materialized Views that earn their keep with clear justification."
        ),
        "allow_delegation": False,
        "verbose": True,
        "max_iter": 5,
    },
    "context_librarian": {
        "role": "Lead Business-Logic Integrity Auditor & Context Gatekeeper",
        "goal": (
            "Maintain an authoritative, version-controlled business context layer in chDB, proactively detecting, "
            "versioning, and surfacing every schema contradiction, metric gap, or semantic drift."
        ),
        "backstory": (
            "You are the meticulous guardian of organizational business logic, metric definitions, and event schemas. "
            "You treat initial documentation and base context with rigorous, constructive skepticism. Diff every schema change, "
            "actively detect context traps (denominator ambiguity, data quality caveats, anti-patterns, boundary issues), "
            "and record versioned changelog entries with trace attribution."
        ),
        "allow_delegation": False,
        "verbose": True,
        "max_iter": 5,
    },
    "product_analyst": {
        "role": "Principal Product Analytics & Growth Data Scientist",
        "goal": (
            "Deliver high-impact, PM-actionable product insights that uncover the root cause ('the why') behind "
            "funnel conversion changes, supported by multi-dimensional cuts and calibrated confidence scores."
        ),
        "backstory": (
            "You are a seasoned Principal Product Data Scientist who bridges complex ClickHouse analytics and executive "
            "product strategy. Never pull raw rows into context; execute exactly the read-only SELECT queries the Query "
            "Architect hands you, match known platform issues (K1–K7), score confidence objectively from the actual result "
            "set, and eliminate all SQL/DB jargon for PM audiences. You do not write SQL yourself."
        ),
        "allow_delegation": False,
        "verbose": True,
        "max_iter": 5,
    },
    "query_architect": {
        "role": "Text-to-SQL Query Architect",
        "goal": (
            "Translate a PM's natural-language question into the exact ClickHouse SELECT statements needed to "
            "answer it — one per mandatory cut dimension, plus a question-targeted query when warranted — "
            "without ever writing, altering, or deleting data."
        ),
        "backstory": (
            "You are a SQL specialist who reads product questions and writes precise, read-only ClickHouse "
            "aggregations. You always cover the mandatory cut dimensions (device_type, geoip_country_code, "
            "destination) the Product Analyst requires, and you add one additional targeted query only when the "
            "question names a specific segment, platform, or condition the mandatory cuts wouldn't surface on "
            "their own. You never write DDL or mutating SQL, and you never execute anything yourself."
        ),
        "allow_delegation": False,
        "verbose": True,
        "max_iter": 5,
    },
}


def load_agents_config() -> dict:
    """Load agent persona configuration (role, goal, backstory, parameters) from YAML config file."""
    config_file = getattr(paths, "AGENTS_CONFIG_YAML", paths.ATLYS_AGENTIC_DIR / "config" / "agents.yaml")
    if config_file.exists():
        try:
            import yaml
            with open(config_file, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f)
                if isinstance(loaded, dict) and loaded:
                    return loaded
        except Exception:
            pass
    return _DEFAULT_AGENTS_CONFIG


def get_role_config(name: str) -> dict:
    """Return a persona's role/goal/backstory dict without building a full
    crewai.Agent — used by pipeline steps that only need prompt-seeding
    metadata for a narration call, not an agentic tool-calling loop."""
    return load_agents_config().get(name, _DEFAULT_AGENTS_CONFIG[name])


def build_instrumentation_engineer() -> Agent:
    cfg = load_agents_config().get("instrumentation_engineer", _DEFAULT_AGENTS_CONFIG["instrumentation_engineer"])
    return Agent(
        role=cfg["role"],
        goal=cfg["goal"],
        backstory=cfg["backstory"].strip(),
        tools=[
            _infer_schema_tool,
            _generate_mv_tool,
            _explain_schema_rationale_tool,
        ],
        llm=llm(),
        memory=False,
        verbose=cfg.get("verbose", True),
        allow_delegation=cfg.get("allow_delegation", False),
        max_iter=cfg.get("max_iter", 5),
    )


def build_context_librarian() -> Agent:
    cfg = load_agents_config().get("context_librarian", _DEFAULT_AGENTS_CONFIG["context_librarian"])
    return Agent(
        role=cfg["role"],
        goal=cfg["goal"],
        backstory=cfg["backstory"].strip(),
        tools=[
            _consult_internal_tables_tool,
            _context_diff_tool,
            _execute_ddl_tool,
            _register_schema_version_tool,
            _context_upsert_tool,
            _append_context_changelog_tool,
        ],
        llm=llm(),
        memory=False,
        verbose=cfg.get("verbose", True),
        allow_delegation=cfg.get("allow_delegation", False),
        max_iter=cfg.get("max_iter", 5),
    )


def build_query_architect() -> Agent:
    cfg = load_agents_config().get("query_architect", _DEFAULT_AGENTS_CONFIG["query_architect"])
    return Agent(
        role=cfg["role"],
        goal=cfg["goal"],
        backstory=cfg["backstory"].strip(),
        tools=[_text_to_sql_tool],
        llm=llm(),
        memory=False,
        verbose=cfg.get("verbose", True),
        allow_delegation=cfg.get("allow_delegation", False),
        max_iter=cfg.get("max_iter", 5),
    )


def build_product_analyst() -> Agent:
    cfg = load_agents_config().get("product_analyst", _DEFAULT_AGENTS_CONFIG["product_analyst"])
    return Agent(
        role=cfg["role"],
        goal=cfg["goal"],
        backstory=cfg["backstory"].strip(),
        tools=[_analytics_compute_tool, _score_confidence_tool],
        llm=llm(),
        memory=False,
        verbose=cfg.get("verbose", True),
        allow_delegation=cfg.get("allow_delegation", False),
        max_iter=cfg.get("max_iter", 5),
    )

