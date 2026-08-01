from atlys_agentic import tools


def _table(rows: list[dict], columns: list[str]) -> str:
    if not rows:
        return "  (none yet)\n"
    widths = {c: max(len(c), max(len(str(r.get(c, ""))) for r in rows)) for c in columns}
    header = "  " + " | ".join(c.ljust(widths[c]) for c in columns)
    sep = "  " + "-+-".join("-" * widths[c] for c in columns)
    body = "\n".join(
        "  " + " | ".join(str(r.get(c, "")).ljust(widths[c]) for c in columns) for r in rows
    )
    return f"{header}\n{sep}\n{body}\n"


def render(snapshot: dict) -> str:
    parts = ["=== SCHEMA CHANGES OVER TIME ===\n"]
    parts.append(_table(snapshot["schema_history"], ["table", "version", "spec_id", "created_at"]))
    parts.append("\n=== INSIGHTS (WITH CONFIDENCE) ===\n")
    parts.append(_table(snapshot["insights"], ["spec_id", "question", "confidence", "created_at"]))
    parts.append("\n=== CONTEXT CHANGELOG ===\n")
    parts.append(_table(snapshot["context_changelog"], ["ts", "change_type", "agent", "trace_id"]))
    return "".join(parts)


def main() -> None:
    snapshot = tools.Tool_Emit_Viz()
    print(render(snapshot))


if __name__ == "__main__":
    main()
