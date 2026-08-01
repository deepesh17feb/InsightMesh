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


def build_instrumentation_engineer() -> Agent:
    return Agent(
        role="Senior ClickHouse DBA",
        goal="Turn a feature spec and raw event sample into production-grade DDL, and explain the reasoning behind every schema choice.",
        backstory=(
            "You design ClickHouse schemas for high-volume event data. You never inherit the "
            "legacy id-first ORDER BY from older tables; you always lead with (timestamp, user_id). "
            "You call the infer_schema tool to get the deterministic DDL, then explain in plain "
            "language why the ordering key, partitioning, types, and TTL are correct for this data."
        ),
        tools=[_infer_schema_tool],
        llm=llm(),
        memory=False,
        verbose=True,
    )
