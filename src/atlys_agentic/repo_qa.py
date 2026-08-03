"""Repository knowledge Q&A for the Analyst's `repo_knowledge` intent.

Hybrid retrieval: a deterministic keyword prefilter picks candidate chunks, then a
CrewAI agent reads further with tools only when the prefilter falls short. This keeps
the common case to a single LLM turn while leaving a recall escape hatch.
"""
from __future__ import annotations

import os

from atlys_agentic import agents, prompts, repo_index, tracing

_PREFILTER_K = 5

try:
    from crewai import Crew, Task
except ImportError:  # pragma: no cover
    Crew = None
    Task = None


def _response(answer_md: str, summary: str, score: float, trace_id: str) -> dict:
    """Build the standard analysis response dict.

    Shape is a contract: `run_chat.py` and `POST /api/analyze/query` both consume it.
    """
    return {
        "answer_md": answer_md,
        "executive_summary": summary,
        "confidence": {"score": score, "rationale": "Answered from repository documentation."},
        "known_issue_match": False,
        "matched_known_issue": "",
        "cuts": {},
        "views": {"conversion_trend": [], "segment_waterfall": [], "metric_deltas": []},
        "sql_queries": [],
        "spec_id": "repo_knowledge",
        "table_name": "none",
        "trace_id": trace_id,
    }


def answer(question: str) -> dict:
    """Answer a question about this repository."""
    trace_id = tracing.new_trace("repo_knowledge", run_mode="live_run")
    chunks = repo_index.search(question, k=_PREFILTER_K)
    context_md = repo_index.format_chunks_md(chunks)

    tracing.span(
        trace_id,
        "repo_knowledge_retrieval",
        {"question": question, "k": _PREFILTER_K},
        {"chunks": len(chunks), "paths": [c["path"] for c in chunks]},
        metadata={"agent": "repo_agent"},
        run_mode="live_run",
    )

    if not chunks:
        return _response(
            "### ℹ️ Nothing Found In This Repository\n\n"
            "I could not find documentation or source in this repository matching that "
            "question. Try naming a document, a CUJ, or a module.",
            "No matching repository content found.",
            0.0,
            trace_id,
        )

    api_key = (
        os.environ.get("GEMINI_API_KEY", "")
        or os.environ.get("GOOGLE_API_KEY", "")
        or os.environ.get("OPENAI_API_KEY", "")
    ).strip()

    if api_key and Crew is not None and not os.environ.get("PYTEST_CURRENT_TEST"):
        try:
            repo_agent = agents.build_repo_agent()
            task = Task(
                description=prompts.build_repo_qa_task_description(question, context_md),
                expected_output="A markdown answer citing every source file used as `path:heading`.",
                agent=repo_agent,
            )
            crew_output = Crew(agents=[repo_agent], tasks=[task], verbose=False).kickoff()
            answer_md = str(crew_output).strip()
            if answer_md:
                tracing.generation(
                    name="repo_agent::answer",
                    model=os.environ.get("LLM_MODEL", "gemini/gemini-2.5-flash"),
                    input={"question": question, "prefiltered_paths": [c["path"] for c in chunks]},
                    output=answer_md,
                    metadata={
                        "agent": "repo_agent",
                        "why": "answered a question about the system itself from its own docs and source",
                    },
                    run_mode="live_run",
                )
                tracing.flush()
                return _response(
                    answer_md,
                    f"Answered '{question}' from repository documentation.",
                    0.9,
                    trace_id,
                )
        except Exception:
            pass

    # Offline degradation: cite the prefiltered chunks directly, same as the rest of
    # the codebase does when no API key is configured or under pytest.
    tracing.flush()
    return _response(
        f"### 📚 Repository Knowledge\n\n**Question:** {question}\n\n{context_md}",
        f"Returned {len(chunks)} matching repository sections for '{question}'.",
        0.6,
        trace_id,
    )
