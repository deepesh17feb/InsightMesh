"""Keyword-prefiltered index over this repository's own documentation and source.

Backs the Analyst's `repo_knowledge` intent. Deliberately stdlib-only: the corpus
is 45 files and roughly 560 chunks, which term-overlap scoring handles well
enough that an embedding index would be cost without benefit.

ponytail: term-overlap scoring, no embeddings and no persistence. Swap in vector
search when keyword recall measurably fails on real questions.
"""
from __future__ import annotations

import re
import subprocess

from atlys_agentic import paths

_INCLUDE_SUFFIXES = (".md", ".py")
_EXCLUDE_PREFIXES = (".worktrees/", "outputs/", ".pytest_cache/", "docs/superpowers/")
_EXCLUDE_SUFFIXES = (".ndjson", ".lock")

# Short and structural words carry no retrieval signal and would flatten every score.
_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were",
    "has", "have", "what", "is", "there", "an", "on", "how", "do", "does", "in",
    "of", "to", "a", "it", "its", "can", "you", "i", "we", "my", "be", "by",
    "or", "as", "at", "if", "not", "but", "all", "any", "our", "their",
}

_TOKEN_RE = re.compile(r"[a-z0-9_]+")
_MD_HEADING_RE = re.compile(r"^(#{1,3})\s+(.*)$")
_PY_SYMBOL_RE = re.compile(r"^(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)")

# A hit in a path or heading is far more discriminative than one in body prose.
_LABEL_WEIGHT = 3

_INDEX: list[dict] | None = None


def tracked_files() -> list[str]:
    """Repo-relative paths of every file eligible for the index.

    Sourced from `git ls-files`, so untracked scratch files and build output can
    never enter the corpus.
    """
    try:
        completed = subprocess.run(
            ["git", "ls-files"],
            cwd=paths.REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
    except Exception:
        return []

    selected = []
    for line in completed.stdout.splitlines():
        path = line.strip()
        if not path or not path.endswith(_INCLUDE_SUFFIXES):
            continue
        if path.startswith(_EXCLUDE_PREFIXES) or path.endswith(_EXCLUDE_SUFFIXES):
            continue
        if path.endswith(".py") and not path.startswith("src/"):
            continue
        selected.append(path)
    return sorted(selected)


def _chunk(path: str, text: str) -> list[dict]:
    """Split a file at its structural boundaries.

    Markdown splits at `#`, `##`, and `###`; Python splits at top-level `def` and
    `class`. Deeper markdown headings and nested defs stay with their parent, which
    keeps chunks large enough to answer a question on their own.
    """
    is_markdown = path.endswith(".md")
    boundary = _MD_HEADING_RE if is_markdown else _PY_SYMBOL_RE

    chunks: list[dict] = []
    heading = ""
    buffer: list[str] = []
    start_line = 1

    def flush() -> None:
        if buffer:
            chunks.append({
                "path": path,
                "heading": heading,
                "text": "\n".join(buffer),
                "start_line": start_line,
            })

    for line_no, line in enumerate(text.splitlines(), 1):
        match = boundary.match(line)
        if match:
            flush()
            heading = match.group(2).strip() if is_markdown else match.group(1)
            buffer = [line]
            start_line = line_no
        else:
            buffer.append(line)
    flush()
    return chunks


def build_index(force: bool = False) -> list[dict]:
    """Build (and memoize for the process lifetime) the chunk index."""
    global _INDEX
    if _INDEX is not None and not force:
        return _INDEX

    chunks: list[dict] = []
    for rel_path in tracked_files():
        try:
            text = (paths.REPO_ROOT / rel_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        chunks.extend(_chunk(rel_path, text))

    _INDEX = chunks
    return _INDEX


def _tokenize(text: str) -> set[str]:
    return {
        token
        for token in _TOKEN_RE.findall(text.lower())
        if len(token) > 2 and token not in _STOPWORDS
    }


def search(
    question: str,
    k: int = 5,
    paths_prefix: tuple[str, ...] | None = None,
) -> list[dict]:
    """Return the k chunks whose terms best overlap the question.

    `paths_prefix` restricts the search to a subtree, used by the analytics blend
    to consider only feature specs and CUJ documentation.
    """
    query_terms = _tokenize(question or "")
    if not query_terms:
        return []

    scored: list[dict] = []
    for chunk in build_index():
        if paths_prefix and not chunk["path"].startswith(tuple(paths_prefix)):
            continue
        body_hits = len(query_terms & _tokenize(chunk["text"]))
        label_hits = len(query_terms & _tokenize(f"{chunk['path']} {chunk['heading']}"))
        if not body_hits and not label_hits:
            continue
        scored.append({**chunk, "score": body_hits + _LABEL_WEIGHT * label_hits})

    # Path and start_line break ties so results are deterministic across runs.
    scored.sort(key=lambda c: (-c["score"], c["path"], c["start_line"]))
    return scored[:k]


def format_chunks_md(chunks: list[dict], max_chars: int = 1200) -> str:
    """Render chunks as cited markdown. Shared by the prompt builder and the
    offline fallback, so both cite sources identically."""
    if not chunks:
        return "_No matching repository content found._"
    blocks = []
    for chunk in chunks:
        label = f"{chunk['path']}:{chunk['heading']}" if chunk["heading"] else chunk["path"]
        blocks.append(f"**`{label}`**\n\n{chunk['text'][:max_chars]}")
    return "\n\n---\n\n".join(blocks)
