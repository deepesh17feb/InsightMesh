"""Single owner of every LLM narration call across the deterministic pipeline.

Flow steps call `narrate()` to turn tool output into PM-readable prose; the
pipeline's control flow never depends on the result. A failed or skipped
call returns None and the caller falls back to templated text — but the
failure is recorded as a trace span instead of silently swallowed, so a
degraded run is visible in Langfuse instead of indistinguishable from a
healthy one.
"""
import os

from atlys_agentic import tracing


def _resolve_api_key() -> str:
    return (
        os.environ.get("GEMINI_API_KEY", "")
        or os.environ.get("GOOGLE_API_KEY", "")
        or os.environ.get("OPENAI_API_KEY", "")
    ).strip()


def narrate(role_cfg: dict, prompt: str, *, run_mode: str, span_name: str, trace_id: str = "") -> str | None:
    """Run one narration LLM call scoped to a persona's role/backstory.

    `role_cfg` is a plain dict with `role`/`backstory` keys (see
    `agents.get_role_config`) — not a `crewai.Agent` instance; this call
    never runs an agentic tool-calling loop, it only produces prose.
    """
    api_key = _resolve_api_key()
    if not api_key or os.environ.get("PYTEST_CURRENT_TEST"):
        return None

    model_name = os.environ.get("LLM_MODEL", "gemini/gemini-flash-latest")
    try:
        import litellm
        resp = litellm.completion(
            model=model_name,
            messages=[
                {"role": "system", "content": f"You are the {role_cfg['role']}. {role_cfg['backstory']}"},
                {"role": "user", "content": prompt},
            ],
            api_key=api_key,
            temperature=0.0,
        )
        text = resp.choices[0].message.content.strip()
        usage = {
            "prompt_tokens": getattr(getattr(resp, "usage", None), "prompt_tokens", 0),
            "completion_tokens": getattr(getattr(resp, "usage", None), "completion_tokens", 0),
        }
        tracing.generation(
            name=span_name,
            model=model_name,
            input={"prompt": prompt},
            output=text,
            usage_details=usage,
            metadata={"role": role_cfg.get("role", "")},
            run_mode=run_mode,
        )
        return text
    except Exception as exc:
        tracing.span(
            trace_id,
            f"{span_name}::failed",
            {"prompt": prompt},
            {"error": str(exc)},
            run_mode=run_mode,
        )
        return None
