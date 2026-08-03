"""Read-only repository access for the Repository Knowledge Analyst.

Both functions are plain Python. The CrewAI `@tool` wrappers live in `agents.py`,
matching the convention already used by `tools_orchestrator` and `tools_cuj1`.
"""
from __future__ import annotations

from pathlib import Path

from atlys_agentic import paths, repo_index

SNIPPET_CHARS = 600
MAX_LINES = 200


def search_repo(query: str, k: int = 5) -> list[dict]:
    """Find repository documentation and source relevant to a query."""
    return [
        {
            "path": hit["path"],
            "heading": hit["heading"],
            "start_line": hit["start_line"],
            "score": hit["score"],
            "snippet": hit["text"][:SNIPPET_CHARS],
        }
        for hit in repo_index.search(query, k=k)
    ]


def _resolve_inside_repo(path: str) -> Path | None:
    """Resolve a caller-supplied path, or return None if it escapes the repository.

    The path argument originates from LLM output on a network-exposed endpoint, so
    it is untrusted input at a trust boundary. `Path.resolve()` collapses `..` and
    follows symlinks before the containment check, which is what makes the check
    hold against traversal, absolute paths, and symlink escapes alike.
    """
    try:
        if not path or not path.strip():
            return None
    except (AttributeError, TypeError):
        # path is not a string (e.g., int, None, etc.)
        return None
    root = paths.REPO_ROOT.resolve()
    try:
        target = (root / path.strip()).resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    if not target.is_relative_to(root):
        return None
    return target


def read_repo_file(path: str, start: int = 0, end: int = 200) -> str:
    """Read a bounded line span from a file inside the repository.

    Returns an `Error: ...` string rather than raising, so the agent can recover
    from a bad path on its next iteration instead of aborting the crew run.
    """
    target = _resolve_inside_repo(path)
    if target is None:
        return "Error: path is outside the repository root."
    if not target.is_file():
        return f"Error: no such file: {path}"

    try:
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return f"Error: could not read {path}: {exc}"

    try:
        start = max(0, int(start))
    except (ValueError, TypeError):
        return f"Error: start must be an integer, got {type(start).__name__}"

    try:
        end = max(0, int(end))
    except (ValueError, TypeError):
        return f"Error: end must be an integer, got {type(end).__name__}"

    end = min(end, start + MAX_LINES, len(lines))
    return "\n".join(lines[start:end])
