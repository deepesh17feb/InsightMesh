"""Text-to-SQL translation for CUJ 2 — single-responsibility split from
Product Analyst: this module only turns a PM question into SQL. It never
executes anything and never scores confidence — that stays with the
Product Analyst, whose only job is running what it's handed and scoring
the result.

LLM-generated per question rather than template-selection, so the query
actually reflects what was asked instead of a fixed dimension list. Falls
back to the deterministic per-dimension template whenever the LLM path is
unavailable, unparseable, or doesn't cover every mandatory cut dimension —
the mandatory dimensions are guaranteed either way: by fallback code when
the LLM can't be trusted, by prompt instruction when it can.
"""
import json
import os

from atlys_agentic import tools, tracing


def _resolve_api_key() -> str:
    return (
        os.environ.get("GEMINI_API_KEY", "")
        or os.environ.get("GOOGLE_API_KEY", "")
        or os.environ.get("OPENAI_API_KEY", "")
    ).strip()


def _fallback_queries(table_name: str, mandatory_dims: tuple) -> list[dict]:
    """Deterministic per-dimension template — the SQL shape CUJ 2 used
    before the Query Architect existed. ponytail: fixed template ceiling;
    upgrade path is fixing whatever made the LLM path fail, not growing
    this fallback."""
    return [
        {
            "dimension": dim,
            "sql": (
                f"SELECT {dim}, count() AS events, uniq(user_id) AS users "
                f"FROM {table_name} GROUP BY {dim} ORDER BY events DESC LIMIT 5"
            ),
        }
        for dim in mandatory_dims
    ]


def _build_prompt(role_cfg: dict, question: str, table_name: str, columns: list, mandatory_dims: tuple) -> str:
    columns_line = ", ".join(columns) if columns else "unknown — use only the mandatory dimensions and count()/uniq() aggregates"
    return (
        f"You are the {role_cfg['role']}. {role_cfg['backstory']}\n\n"
        f"Question: '{question}'\n"
        f"Table: {table_name}\n"
        f"Available columns: {columns_line}\n"
        f"Mandatory cut dimensions (one SELECT each, always required): {', '.join(mandatory_dims)}\n\n"
        "Return strict JSON only, no prose, no markdown fences:\n"
        '{"queries": [{"dimension": "<one of the mandatory dimensions>", "sql": "<SELECT ...>"}, ...'
        ' , optionally one more object with "dimension": null and a SELECT that targets exactly what the question asked]}\n\n'
        "Rules: every sql value MUST start with SELECT and reference `FROM " + table_name + "`. "
        "Never write DROP/DELETE/INSERT/ALTER/TRUNCATE. One query object per mandatory dimension is required — "
        "do not skip any. Aggregate with count()/uniq(user_id), GROUP BY the dimension, ORDER BY events DESC, LIMIT 5-10."
    )


def generate_sql(
    role_cfg: dict,
    question: str,
    table_name: str,
    columns: list,
    mandatory_dims: tuple,
    *,
    trace_id: str = "",
) -> list[dict]:
    """Translate `question` into the SQL CUJ 2 needs to answer it: one
    SELECT per mandatory dimension, plus an optional question-targeted
    extra (`dimension: null`). Every returned query is SELECT-only,
    enforced here and again by Tool_Analytics_Compute before execution."""
    api_key = _resolve_api_key()
    if not api_key or os.environ.get("PYTEST_CURRENT_TEST"):
        return _fallback_queries(table_name, mandatory_dims)

    model_name = os.environ.get("LLM_MODEL", "gemini/gemini-flash-latest")
    prompt = _build_prompt(role_cfg, question, table_name, columns, mandatory_dims)
    try:
        import litellm
        resp = litellm.completion(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            api_key=api_key,
            temperature=0.0,
        )
        raw = resp.choices[0].message.content.strip()
        if "```json" in raw:
            raw = raw.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in raw:
            raw = raw.split("```", 1)[1].split("```", 1)[0].strip()
        data = json.loads(raw)
        candidates = data.get("queries", [])

        validated = []
        covered_dims = set()
        for q in candidates:
            sql = (q.get("sql") or "").strip()
            dim = q.get("dimension")
            try:
                tools._assert_select_only(sql)
            except ValueError:
                continue
            validated.append({"dimension": dim, "sql": sql})
            if dim in mandatory_dims:
                covered_dims.add(dim)

        if not set(mandatory_dims) <= covered_dims:
            # Don't ship a partial mix of LLM + missing dimensions —
            # fall back to the deterministic template entirely.
            tracing.span(
                trace_id,
                "query_architect::incomplete_coverage",
                {"question": question, "covered": list(covered_dims)},
                {"required": list(mandatory_dims)},
            )
            return _fallback_queries(table_name, mandatory_dims)

        usage = {
            "prompt_tokens": getattr(getattr(resp, "usage", None), "prompt_tokens", 0),
            "completion_tokens": getattr(getattr(resp, "usage", None), "completion_tokens", 0),
        }
        tracing.generation(
            name="query_architect::text_to_sql",
            model=model_name,
            input={"question": question, "table": table_name},
            output=json.dumps(validated),
            usage_details=usage,
            metadata={"role": role_cfg.get("role", "")},
        )
        return validated
    except Exception as exc:
        tracing.span(
            trace_id,
            "query_architect::text_to_sql_failed",
            {"question": question},
            {"error": str(exc)},
        )
        return _fallback_queries(table_name, mandatory_dims)
