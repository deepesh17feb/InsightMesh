# Analyst Repo Knowledge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the `atlys-analyst` chat surface answer questions about this repository's own docs, architecture, CUJs, setup, specs, and source code, and enrich genuine telemetry answers with the relevant feature spec.

**Architecture:** A stdlib-only keyword index over `git ls-files` markdown and `src/**/*.py` prefilters candidate chunks. A new CrewAI agent with two read-only tools (`search_repo`, `read_repo_file`) reads further only when the prefilter is insufficient. Routing is a fifth intent, `repo_knowledge`, added to the LLM intent classifier that `analysis_flow.run` already calls — no new regex ladder, and the CUJ 1 path is untouched.

**Tech Stack:** Python 3.11, CrewAI 1.15.10, litellm, pydantic, pytest 8, chDB, Langfuse.

**Spec:** `docs/superpowers/specs/2026-08-03-analyst-repo-knowledge-design.md`

## Global Constraints

- **Python 3.11.** The project venv is `.venv/bin/python3` (3.11). Backslashes inside f-string expression parts are a `SyntaxError` — hoist to a local variable first. This is what Task 0 fixes.
- **Run everything through the venv:** `.venv/bin/python3 -m pytest`. A bare `python` is not on PATH; a bare `python3` is `/usr/bin/python3` and has no dependencies installed.
- **`repo_index` is stdlib-only.** No new dependencies in `pyproject.toml`. No embeddings, no vector store, no persisted index.
- **Repository tools are read-only.** No write, delete, move, or shell execution tool is added.
- **`read_repo_file` must be jailed to `paths.REPO_ROOT`.** Its path argument comes from LLM output on a network-exposed endpoint, so it is untrusted input at a trust boundary. This check is not optional and must not be simplified away.
- **Offline degradation is mandatory.** Every LLM call site must check `os.environ.get("PYTEST_CURRENT_TEST")` and the API key, exactly as the surrounding code in `analysis_flow.py` already does, so the test suite stays hermetic and makes no network calls.
- **The response dict shape returned by `analysis_flow.run` is a contract.** `run_chat.py` and `POST /api/analyze/query` both consume it. Every new return path must produce all the same keys.
- **Do not modify** `run_chat.py`, `conversational_ingestion.py`, `flows/ingestion_flow.py`, or any CUJ 1 code path.
- **Corpus exclusions:** `.worktrees/`, `outputs/`, `.pytest_cache/`, `docs/superpowers/`, `*.ndjson`, `*.lock`. Python files are included only under `src/`.

## Amendments to the Spec

Two items were discovered while gathering exact signatures for this plan. Both are folded into tasks below, and the spec document is updated in Task 7.

1. **`docs/superpowers/` joins the corpus exclusion list.** Verified against a prototype over the real repository: our own plan and spec documents outranked the actual source documents in 3 of 5 sample queries. Excluding them restores correct ranking.
2. **`prompts.build_product_analyst_synthesis_prompt` is called with the wrong signature.** `analysis_flow.py:546` passes `spec_id`, `table_name`, `known_issue`, `cuts`; the function it aliases (`prompts.py:277` → `build_analytics_agent_synthesis_prompt`, `prompts.py:152`) accepts `interpretation`, `headline`, `cuts_summary`, `correlation`, `timing_k_match`, `context_applied`, `trend_info`. The resulting `TypeError` is swallowed by the bare `except Exception: pass` at `analysis_flow.py:580`, so the Product Analyst synthesis LLM call has never executed on this path, `executive_summary` is always the template string, and the `product_analyst::gemini_synthesis` generation never reaches Langfuse. The spec's blend threads repo context into that exact prompt, so it cannot work until this is fixed. Task 6 fixes it.

## File Structure

**Create:**

| File | Responsibility |
| :--- | :--- |
| `src/atlys_agentic/repo_index.py` | Corpus selection, chunking, keyword scoring. Pure functions, stdlib only, no LLM. |
| `src/atlys_agentic/tools_repo.py` | Plain-Python repo read functions plus the path jail. No CrewAI import. |
| `src/atlys_agentic/repo_qa.py` | Assembles prefilter + agent + Crew, returns the standard analysis response dict. |
| `tests/test_repo_qa.py` | Covers all of the above, hermetic. |

**Modify:**

| File | Change |
| :--- | :--- |
| `src/atlys_agentic/tools_cuj1.py:307` | Python 3.11 f-string fix (Task 0). |
| `src/atlys_agentic/prompts.py` | Fifth classifier intent; `build_repo_qa_task_description`; `build_repo_answer_synthesis_prompt`. |
| `src/atlys_agentic/agents.py` | `_search_repo_tool`, `_read_repo_file_tool`, `build_repo_agent()`. |
| `src/atlys_agentic/flows/analysis_flow.py` | `repo_knowledge` branches (LLM + heuristic); two `AnalysisState` fields; blend in `jit_context_retrieval`; synthesis-prompt call fix. |
| `docs/CUJ2.md` | New agent and span names. |
| `docs/superpowers/specs/2026-08-03-analyst-repo-knowledge-design.md` | Record the two amendments above. |

The split follows the existing codebase convention: `tools_*.py` holds plain functions, `agents.py` holds the thin `@tool` wrappers that import them lazily, and `prompts.py` holds every prompt string.

---

### Task 0: Unblock the test suite

The suite does not currently collect. All 8 test files error with `SyntaxError: f-string expression part cannot include a backslash` from `tools_cuj1.py:307`, because `.venv` is Python 3.11 and backslashes in f-string expressions are legal only on 3.12+. There is no green baseline to work against until this is fixed.

**Files:**
- Modify: `src/atlys_agentic/tools_cuj1.py:299-309`

**Interfaces:**
- Consumes: nothing
- Produces: a collectable test suite. Every later task depends on this.

- [ ] **Step 1: Confirm the failure**

Run: `.venv/bin/python3 -m pytest -q 2>&1 | tail -5`

Expected: `Interrupted: 8 errors during collection`, with `SyntaxError: f-string expression part cannot include a backslash`.

- [ ] **Step 2: Hoist the escaped value out of the f-string**

In `src/atlys_agentic/tools_cuj1.py`, the current code reads:

```python
    new_ver = (existing[0].get("v", 0) + 1) if (existing and existing[0].get("v") is not None) else 1

    try:
        chdb_client.run(
            f"INSERT INTO schema_registry VALUES ('{table_name}', '{ddl.replace('\'', '\'\'')}', '{json.dumps(cols)}', '{spec_id}', {new_ver}, now())",
            fmt="CSV",
        )
```

Replace it with:

```python
    new_ver = (existing[0].get("v", 0) + 1) if (existing and existing[0].get("v") is not None) else 1

    ddl_escaped = ddl.replace("'", "''")
    cols_json = json.dumps(cols)

    try:
        chdb_client.run(
            f"INSERT INTO schema_registry VALUES ('{table_name}', '{ddl_escaped}', '{cols_json}', '{spec_id}', {new_ver}, now())",
            fmt="CSV",
        )
```

The SQL string produced is byte-for-byte identical. Only the escaping moves out of the f-string expression.

- [ ] **Step 3: Verify collection and record the baseline**

Run: `.venv/bin/python3 -m pytest -q 2>&1 | tail -5`

Expected: the suite collects. Write down the pass/fail counts — this is the baseline every later task must not regress. Pre-existing failures unrelated to this work are acceptable; note them and move on. Do not fix them in this plan.

- [ ] **Step 4: Check for the same pattern elsewhere**

Run: `grep -rn "f\"[^\"]*\\\\" src/atlys_agentic/*.py src/atlys_agentic/flows/*.py`

If any other f-string contains a backslash inside `{...}`, apply the same hoist. If there are none, continue.

- [ ] **Step 5: Commit**

```bash
git add src/atlys_agentic/tools_cuj1.py
git commit -m "fix(tools_cuj1): hoist SQL escaping out of f-string for Python 3.11

Backslashes inside f-string expression parts are a SyntaxError before
Python 3.12. The project venv is 3.11, so this broke collection for the
entire test suite."
```

---

### Task 1: `repo_index` — corpus, chunking, keyword search

**Files:**
- Create: `src/atlys_agentic/repo_index.py`
- Test: `tests/test_repo_qa.py`

**Interfaces:**
- Consumes: `paths.REPO_ROOT` from `atlys_agentic.paths`
- Produces:
  - `tracked_files() -> list[str]` — repo-relative paths, sorted
  - `build_index(force: bool = False) -> list[dict]` — each chunk is `{"path": str, "heading": str, "text": str, "start_line": int}`
  - `search(question: str, k: int = 5, paths_prefix: tuple[str, ...] | None = None) -> list[dict]` — chunks plus an `int` `"score"` key, sorted by descending score

- [ ] **Step 1: Write the failing tests**

Create `tests/test_repo_qa.py`:

```python
"""Repository knowledge index, tools, and Q&A — hermetic, no network calls."""
from atlys_agentic import repo_index


def test_index_is_not_empty():
    assert len(repo_index.build_index()) > 50


def test_corpus_excludes_worktrees_data_and_our_own_planning_docs():
    for path in repo_index.tracked_files():
        assert not path.startswith(".worktrees/"), path
        assert not path.startswith("outputs/"), path
        assert not path.startswith("docs/superpowers/"), path
        assert not path.endswith(".ndjson"), path


def test_corpus_is_markdown_anywhere_plus_python_under_src_only():
    for path in repo_index.tracked_files():
        assert path.endswith((".md", ".py")), path
        if path.endswith(".py"):
            assert path.startswith("src/"), path


def test_chunks_carry_path_heading_and_start_line():
    chunk = repo_index.build_index()[0]
    assert set(chunk) == {"path", "heading", "text", "start_line"}
    assert chunk["start_line"] >= 1


def test_search_finds_the_run_guide():
    hits = repo_index.search("how do I run the backend", k=3)
    assert "RUN.md" in [h["path"] for h in hits]


def test_search_finds_the_cuj2_span_contract():
    hits = repo_index.search("langfuse tracing span contract", k=5)
    assert "docs/CUJ2.md" in [h["path"] for h in hits]


def test_search_respects_k():
    assert len(repo_index.search("clickhouse schema", k=2)) <= 2


def test_search_orders_by_descending_score():
    scores = [h["score"] for h in repo_index.search("clickhouse schema ingestion", k=10)]
    assert scores == sorted(scores, reverse=True)


def test_search_on_empty_or_stopword_only_question_returns_nothing():
    assert repo_index.search("") == []
    assert repo_index.search("the and for") == []


def test_paths_prefix_restricts_the_subtree():
    hits = repo_index.search(
        "express checkout funnel",
        k=3,
        paths_prefix=("docs/", "problem statment/specs/"),
    )
    assert hits
    for hit in hits:
        assert hit["path"].startswith(("docs/", "problem statment/specs/"))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python3 -m pytest tests/test_repo_qa.py -q`

Expected: FAIL — `ImportError: cannot import name 'repo_index'`.

- [ ] **Step 3: Implement `repo_index`**

Create `src/atlys_agentic/repo_index.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python3 -m pytest tests/test_repo_qa.py -q`

Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add src/atlys_agentic/repo_index.py tests/test_repo_qa.py
git commit -m "feat(repo_index): stdlib keyword index over repo docs and source

Corpus comes from git ls-files, chunked at markdown headings and top-level
Python symbols, scored by term overlap with a 3x weight on path and heading
hits. No embeddings, no persisted index."
```

---

### Task 2: `tools_repo` — read-only repo access with a path jail

**Files:**
- Create: `src/atlys_agentic/tools_repo.py`
- Test: `tests/test_repo_qa.py` (append)

**Interfaces:**
- Consumes: `repo_index.search`, `repo_index.format_chunks_md`, `paths.REPO_ROOT`
- Produces:
  - `search_repo(query: str, k: int = 5) -> list[dict]` — `{"path", "heading", "start_line", "score", "snippet"}` per hit
  - `read_repo_file(path: str, start: int = 0, end: int = 200) -> str`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_repo_qa.py`:

```python
from atlys_agentic import tools_repo


def test_search_repo_returns_snippets_not_whole_chunks():
    hits = tools_repo.search_repo("how do I run the backend", k=3)
    assert hits
    assert set(hits[0]) == {"path", "heading", "start_line", "score", "snippet"}
    assert len(hits[0]["snippet"]) <= tools_repo.SNIPPET_CHARS


def test_read_repo_file_reads_a_tracked_file():
    text = tools_repo.read_repo_file("README.md", start=0, end=5)
    assert "Error:" not in text
    assert len(text.splitlines()) <= 5


def test_read_repo_file_caps_the_line_span():
    text = tools_repo.read_repo_file("README.md", start=0, end=99999)
    assert len(text.splitlines()) <= tools_repo.MAX_LINES


def test_read_repo_file_rejects_parent_traversal():
    assert tools_repo.read_repo_file("../../etc/passwd").startswith("Error:")
    assert tools_repo.read_repo_file("docs/../../../etc/passwd").startswith("Error:")


def test_read_repo_file_rejects_absolute_paths_outside_the_repo():
    assert tools_repo.read_repo_file("/etc/passwd").startswith("Error:")


def test_read_repo_file_rejects_a_symlink_escaping_the_repo(tmp_path):
    from atlys_agentic import paths
    link = paths.REPO_ROOT / "_test_escape_link"
    link.symlink_to("/etc/passwd")
    try:
        assert tools_repo.read_repo_file("_test_escape_link").startswith("Error:")
    finally:
        link.unlink()


def test_read_repo_file_reports_a_missing_file_without_raising():
    assert tools_repo.read_repo_file("no/such/file.md").startswith("Error:")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python3 -m pytest tests/test_repo_qa.py -q`

Expected: FAIL — `ImportError: cannot import name 'tools_repo'`.

- [ ] **Step 3: Implement `tools_repo`**

Create `src/atlys_agentic/tools_repo.py`:

```python
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
    if not path or not path.strip():
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

    start = max(0, int(start))
    end = min(int(end), start + MAX_LINES, len(lines))
    return "\n".join(lines[start:end])
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python3 -m pytest tests/test_repo_qa.py -q`

Expected: 17 passed.

- [ ] **Step 5: Commit**

```bash
git add src/atlys_agentic/tools_repo.py tests/test_repo_qa.py
git commit -m "feat(tools_repo): read-only repo search and bounded file read

read_repo_file resolves before checking containment, so parent traversal,
absolute paths, and symlink escapes are all rejected. Its path argument is
untrusted LLM output on a network-exposed endpoint."
```

---

### Task 3: `build_repo_agent` and `repo_qa.answer`

**Files:**
- Modify: `src/atlys_agentic/prompts.py` (append two builders)
- Modify: `src/atlys_agentic/agents.py` (append two tool wrappers and one builder)
- Create: `src/atlys_agentic/repo_qa.py`
- Test: `tests/test_repo_qa.py` (append)

**Interfaces:**
- Consumes: `repo_index.search`, `repo_index.format_chunks_md`, `tools_repo.search_repo`, `tools_repo.read_repo_file`, `agents.llm()`
- Produces:
  - `prompts.build_repo_qa_task_description(question: str, context_md: str) -> str`
  - `agents.build_repo_agent() -> Agent`
  - `repo_qa.answer(question: str) -> dict` — the standard analysis response dict with `spec_id == "repo_knowledge"`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_repo_qa.py`:

```python
from atlys_agentic import repo_qa

_RESPONSE_KEYS = {
    "answer_md", "executive_summary", "confidence", "known_issue_match",
    "matched_known_issue", "cuts", "views", "sql_queries", "spec_id",
    "table_name", "trace_id",
}


def test_answer_returns_the_standard_response_contract():
    # Under PYTEST_CURRENT_TEST this takes the offline path and makes no network call.
    result = repo_qa.answer("how do I run the backend")
    assert set(result) == _RESPONSE_KEYS
    assert result["spec_id"] == "repo_knowledge"
    assert result["table_name"] == "none"
    assert result["known_issue_match"] is False
    assert result["sql_queries"] == []


def test_answer_cites_the_files_it_used():
    result = repo_qa.answer("how do I run the backend")
    assert "RUN.md" in result["answer_md"]


def test_answer_on_an_unmatchable_question_still_returns_the_contract():
    result = repo_qa.answer("zzzz nonexistent qqqq")
    assert set(result) == _RESPONSE_KEYS
    assert result["confidence"]["score"] == 0.0


def test_repo_agent_exposes_exactly_the_two_read_only_tools():
    from atlys_agentic import agents
    tool_names = {getattr(t, "name", "") for t in agents.build_repo_agent().tools}
    assert tool_names == {"search_repo", "read_repo_file"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python3 -m pytest tests/test_repo_qa.py -q`

Expected: FAIL — `ImportError: cannot import name 'repo_qa'`.

- [ ] **Step 3: Add the prompt builders**

Append to `src/atlys_agentic/prompts.py`:

```python
def build_repo_qa_task_description(question: str, context_md: str) -> str:
    """Construct the CrewAI task description for the Repository Knowledge Analyst."""
    return (
        "Answer the user's question about the InsightMesh system itself, using this "
        "repository's documentation and source code as the only source of truth.\n\n"
        f"User question: '{question}'\n\n"
        "Pre-retrieved repository content, selected by keyword relevance:\n\n"
        f"{context_md}\n\n"
        "Instructions:\n"
        "- If the content above answers the question, answer directly from it. Do not "
        "call any tool.\n"
        "- Only if it is insufficient, call `search_repo` with different terms, or "
        "`read_repo_file` to read more of a file already cited above.\n"
        "- Cite every source you use inline as `path:heading`.\n"
        "- Never invent file paths, function names, or behaviour that is not in the "
        "retrieved content. If the repository does not answer the question, say so "
        "plainly.\n"
        "- Answer in markdown, starting with a `### ` heading."
    )
```

- [ ] **Step 4: Add the tool wrappers and the agent builder**

Append to `src/atlys_agentic/agents.py`, following the lazy-import pattern already used by the orchestrator wrappers at lines 290-308:

```python
@tool("search_repo")
def _search_repo_tool(query: str) -> list:
    """Search this repository's documentation and source code for content relevant to a query."""
    from atlys_agentic import tools_repo
    return tools_repo.search_repo(query)


@tool("read_repo_file")
def _read_repo_file_tool(path: str, start: int = 0, end: int = 200) -> str:
    """Read a bounded span of lines from a file inside this repository."""
    from atlys_agentic import tools_repo
    return tools_repo.read_repo_file(path, start=start, end=end)


def build_repo_agent() -> Agent:
    """Build the Repository Knowledge Analyst, which answers questions about this
    system itself — its architecture, CUJs, setup, feature specs, and source."""
    return Agent(
        role="Atlys Repository Knowledge Analyst",
        goal=(
            "Answer questions about the InsightMesh system itself using its own "
            "documentation and source code, citing every file used."
        ),
        backstory="""You are the resident expert on this codebase. You know its CUJ documents,
its ClickHouse and chDB context layer, its CrewAI flows, and its Langfuse span contract. You
answer strictly from what the repository actually says — you never speculate about behaviour
you have not read, and you say so plainly when the repository does not cover something.""",
        tools=[_search_repo_tool, _read_repo_file_tool],
        llm=llm(),
        memory=False,
        verbose=True,
        allow_delegation=False,
        max_iter=5,
    )
```

- [ ] **Step 5: Implement `repo_qa`**

Create `src/atlys_agentic/repo_qa.py`:

```python
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
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/python3 -m pytest tests/test_repo_qa.py -q`

Expected: 21 passed.

- [ ] **Step 7: Confirm no network call happened**

Run: `.venv/bin/python3 -m pytest tests/test_repo_qa.py -q -p no:randomly 2>&1 | grep -ci "litellm\|connection\|timeout" || true`

Expected: `0`. If non-zero, the `PYTEST_CURRENT_TEST` guard in `repo_qa.answer` is missing or misplaced.

- [ ] **Step 8: Commit**

```bash
git add src/atlys_agentic/repo_qa.py src/atlys_agentic/agents.py src/atlys_agentic/prompts.py tests/test_repo_qa.py
git commit -m "feat(repo_qa): Repository Knowledge Analyst over prefiltered chunks

CrewAI agent with search_repo and read_repo_file, seeded with keyword-
prefiltered context so the common case costs one LLM turn. Returns the
standard analysis response dict, and degrades to a cited chunk digest
offline."
```

---

### Task 4: Fifth classifier intent — `repo_knowledge`

**Files:**
- Modify: `src/atlys_agentic/prompts.py:12-28` (`build_intent_classifier_system_prompt`)
- Modify: `src/atlys_agentic/flows/analysis_flow.py:132-194` (`_heuristic_classify_intent`)
- Test: `tests/test_repo_qa.py` (append)

**Interfaces:**
- Consumes: nothing from earlier tasks
- Produces: `"repo_knowledge"` as a fifth value of the `intent` field returned by `classify_question_intent_with_llm` and `_heuristic_classify_intent`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_repo_qa.py`:

```python
from atlys_agentic import prompts
from atlys_agentic.flows import analysis_flow


def test_classifier_prompt_documents_the_repo_knowledge_intent():
    text = prompts.build_intent_classifier_system_prompt()
    assert "repo_knowledge" in text
    assert '"analytical" | "greeting" | "abusive" | "out_of_scope" | "repo_knowledge"' in text


def test_heuristic_routes_system_questions_to_repo_knowledge():
    for question in [
        "how does the ingestion flow work?",
        "what is CUJ 2?",
        "where is the intent classifier implemented?",
        "explain this repo's architecture",
        "how do I run the backend?",
    ]:
        assert analysis_flow._heuristic_classify_intent(question)["intent"] == "repo_knowledge", question


def test_heuristic_keeps_telemetry_questions_analytical():
    for question in [
        "why did express checkout conversion drop on iOS?",
        "is there an OTP drop during verification?",
        "show me the funnel breakdown by device_type",
    ]:
        assert analysis_flow._heuristic_classify_intent(question)["intent"] == "analytical", question


def test_heuristic_still_classifies_greetings_and_abuse():
    assert analysis_flow._heuristic_classify_intent("hello")["intent"] == "greeting"
    assert analysis_flow._heuristic_classify_intent("you are stupid")["intent"] == "abusive"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python3 -m pytest tests/test_repo_qa.py -q -k "classifier or heuristic"`

Expected: FAIL — `assert 'repo_knowledge' in text`, and the heuristic returns `analytical` for system questions.

- [ ] **Step 3: Add the fifth intent to the LLM classifier prompt**

In `src/atlys_agentic/prompts.py`, inside `build_intent_classifier_system_prompt`, the current lines read:

```python
        "4. 'out_of_scope': Non-analytical requests completely unrelated to product analytics or telemetry (e.g., cooking recipes, general jokes, movie trivia, unrelated coding).\n\n"
        f"{specs_context}"
        "Output strictly valid JSON with keys:\n"
        "{\n"
        '  "intent": "analytical" | "greeting" | "abusive" | "out_of_scope",\n'
        '  "detected_spec": string | null,\n'
        '  "direct_response": "If greeting, abusive, or out_of_scope, provide a polite, professional markdown response. If analytical, null."\n'
        "}"
```

Replace with:

```python
        "4. 'out_of_scope': Non-analytical requests completely unrelated to product analytics or telemetry (e.g., cooking recipes, general jokes, movie trivia, unrelated coding).\n"
        "5. 'repo_knowledge': Questions about THIS system itself — its architecture, CUJ definitions, "
        "setup or run instructions, feature spec documents, schema design rationale, source code, "
        "modules, agents, flows, or tracing contract.\n\n"
        "Boundary between 'analytical' and 'repo_knowledge': a question about what the system IS or "
        "DOES is 'repo_knowledge'; a question about what the TELEMETRY SHOWS is 'analytical'. "
        "'What does the express checkout spec define as the funnel?' is 'repo_knowledge'. "
        "'Why did express checkout conversion drop?' is 'analytical'.\n\n"
        f"{specs_context}"
        "Output strictly valid JSON with keys:\n"
        "{\n"
        '  "intent": "analytical" | "greeting" | "abusive" | "out_of_scope" | "repo_knowledge",\n'
        '  "detected_spec": string | null,\n'
        '  "direct_response": "If greeting, abusive, or out_of_scope, provide a polite, professional markdown response. If analytical or repo_knowledge, null."\n'
        "}"
```

- [ ] **Step 4: Add the matching branch to the offline heuristic**

In `src/atlys_agentic/flows/analysis_flow.py`, inside `_heuristic_classify_intent`, insert this block **after** the `out_of_scope_patterns` block and **before** the final `infer_domain_from_question` line:

```python
    # Questions about this system itself, as opposed to what the telemetry shows.
    # Checked after greeting and abuse, before the analytical default.
    repo_patterns = [
        r"\b(cuj|cuj1|cuj2)\b",
        r"\b(readme|architecture|repo|repository|codebase|module|source code)\b",
        r"\b(spec|specification) (file|document|doc)\b",
        r"\bhow (does|do) (this|the|it) (system|repo|repository|code|project|flow|pipeline)\b",
        r"\bhow does the \w+ (flow|agent|tool|client|classifier|index)\b",
        r"\bwhere (is|are) .*(implement|defined|located|configured)",
        r"\bhow (do|can) i (run|start|deploy|install|setup|set up)\b",
        r"\bexplain (the|this) (architecture|design|flow|pipeline|schema design)\b",
        r"\b(langfuse|span contract|tracing contract)\b",
    ]
    if any(re.search(p, q_lower) for p in repo_patterns):
        return {"intent": "repo_knowledge", "detected_spec": None, "response": None}

```

The `has_analytical` guard is deliberately **not** applied here. "how do I run the backend" contains no analytical keyword, and "where is the funnel query implemented" contains `funnel` but is plainly a source-code question, so gating on `has_analytical` would misroute it.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python3 -m pytest tests/test_repo_qa.py -q`

Expected: 25 passed.

- [ ] **Step 6: Verify no regression in the existing classifier tests**

Run: `.venv/bin/python3 -m pytest tests/test_cuj2_analytics_flow.py tests/test_chat_backend.py -q`

Expected: same result as the Task 0 baseline. If a previously passing test now fails, a `repo_patterns` entry is too broad — narrow the offending pattern rather than deleting the test.

- [ ] **Step 7: Commit**

```bash
git add src/atlys_agentic/prompts.py src/atlys_agentic/flows/analysis_flow.py tests/test_repo_qa.py
git commit -m "feat(classifier): add repo_knowledge as a fifth guardrail intent

Questions about the system itself previously classified as out_of_scope and
dead-ended. Both the LLM prompt and the offline heuristic now recognise them,
with the analytical boundary stated explicitly."
```

---

### Task 5: Route `repo_knowledge` in `analysis_flow.run`

**Files:**
- Modify: `src/atlys_agentic/flows/analysis_flow.py:671-685` (guardrail branches) and `:6` (import)
- Test: `tests/test_repo_qa.py` (append)

**Interfaces:**
- Consumes: `repo_qa.answer` (Task 3), the `repo_knowledge` intent (Task 4)
- Produces: `analysis_flow.run(question=...)` returning the repo Q&A response for system questions

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_repo_qa.py`:

```python
def test_run_routes_a_system_question_to_repo_knowledge():
    result = analysis_flow.run(question="how do I run the backend?", spec_id="chat")
    assert result["spec_id"] == "repo_knowledge"
    assert "RUN.md" in result["answer_md"]


def test_run_still_answers_telemetry_questions_analytically():
    result = analysis_flow.run(question="why did express checkout conversion drop on iOS?", spec_id="chat")
    assert result["spec_id"] != "repo_knowledge"


def test_disabling_guardrails_disables_repo_knowledge_routing():
    result = analysis_flow.run(
        question="how do I run the backend?", spec_id="chat", enable_guardrails=False
    )
    assert result["spec_id"] != "repo_knowledge"


def test_repo_knowledge_response_satisfies_the_chat_contract():
    result = analysis_flow.run(question="what is CUJ 2?", spec_id="chat")
    for key in _RESPONSE_KEYS:
        assert key in result, key
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python3 -m pytest tests/test_repo_qa.py -q -k "run_routes or guardrails or chat_contract"`

Expected: FAIL — `assert result["spec_id"] == "repo_knowledge"` gets an analytical spec instead.

- [ ] **Step 3: Import `repo_qa`**

In `src/atlys_agentic/flows/analysis_flow.py`, change line 6 from:

```python
from atlys_agentic import agents, chdb_client, prompts, tools, tracing
```

to:

```python
from atlys_agentic import agents, chdb_client, prompts, repo_qa, tools, tracing
```

- [ ] **Step 4: Add the routing branch**

In `analysis_flow.run`, immediately after the closing of the `elif intent == "out_of_scope":` block (which ends with its `}` return at roughly line 685) and still inside the `if is_guardrails_enabled(...)` block, add:

```python
        elif intent == "repo_knowledge":
            return repo_qa.answer(question)
```

Placing it inside the guardrail block keeps behaviour consistent with the other guardrail intents: `enable_guardrails=False` disables all of them together.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python3 -m pytest tests/test_repo_qa.py -q`

Expected: 29 passed.

- [ ] **Step 6: Verify the full suite has not regressed**

Run: `.venv/bin/python3 -m pytest -q 2>&1 | tail -5`

Expected: same pass/fail counts as the Task 0 baseline, plus the 29 new tests passing.

- [ ] **Step 7: Commit**

```bash
git add src/atlys_agentic/flows/analysis_flow.py tests/test_repo_qa.py
git commit -m "feat(analysis_flow): route repo_knowledge to the Repository Knowledge Analyst

System questions on the analyst surface previously fell through to
out_of_scope. run_chat.py and /api/analyze/query need no change: the
response dict shape is unchanged."
```

---

### Task 6: Fix the synthesis prompt call, then blend repo context into analytics

The blend target is the Product Analyst synthesis prompt, which is currently dead code — see Amendment 2. Fix it first, then blend, so the blend is actually observable.

**Files:**
- Modify: `src/atlys_agentic/prompts.py` (append `build_repo_answer_synthesis_prompt`)
- Modify: `src/atlys_agentic/flows/analysis_flow.py:232-246` (`AnalysisState`), `:259-322` (`jit_context_retrieval`), `:543-581` (`_score_and_write`)
- Test: `tests/test_repo_qa.py` (append)

**Interfaces:**
- Consumes: `repo_index.search` (Task 1)
- Produces: `AnalysisState.repo_context: list[dict]`, `AnalysisState.librarian_notes: str`, and `prompts.build_repo_answer_synthesis_prompt(...)`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_repo_qa.py`:

```python
import inspect


def test_synthesis_prompt_accepts_the_arguments_the_flow_actually_passes():
    params = inspect.signature(prompts.build_repo_answer_synthesis_prompt).parameters
    for required in ("question", "spec_id", "table_name", "known_issue", "cuts", "confidence",
                     "repo_context_md", "librarian_notes"):
        assert required in params, required


def test_synthesis_prompt_builds_without_raising():
    text = prompts.build_repo_answer_synthesis_prompt(
        question="why did express checkout drop?",
        spec_id="01_express_checkout",
        table_name="express_checkout",
        known_issue="K1: OTP autofill regression",
        cuts={"device_type": []},
        confidence={"score": 0.8, "rationale": "n=100"},
        repo_context_md="**`problem statment/specs/01_express_checkout/spec.md:Feature spec`**",
        librarian_notes="K1 relates to this question.",
    )
    assert "express_checkout" in text
    assert "K1" in text


def test_analysis_state_carries_repo_context_and_librarian_notes():
    state = analysis_flow.AnalysisState()
    assert state.repo_context == []
    assert state.librarian_notes == ""


def test_jit_context_retrieval_populates_repo_context_from_specs_and_docs():
    from atlys_agentic import chdb_client
    chdb_client.init_schema()
    chdb_client.init_base_context()

    flow = analysis_flow.AnalysisFlow()
    flow.state.question = "why did express checkout conversion drop?"
    flow.state.spec_id = "chat"
    flow.jit_context_retrieval()
    assert flow.state.repo_context
    for chunk in flow.state.repo_context:
        assert chunk["path"].startswith(("docs/", "problem statment/specs/"))


def test_repo_context_failure_cannot_break_an_analysis_run(monkeypatch):
    from atlys_agentic import chdb_client
    chdb_client.init_schema()
    chdb_client.init_base_context()

    def boom(*args, **kwargs):
        raise RuntimeError("index unavailable")

    monkeypatch.setattr(analysis_flow.repo_index, "search", boom)
    flow = analysis_flow.AnalysisFlow()
    flow.state.question = "why did express checkout conversion drop?"
    flow.state.spec_id = "chat"
    flow.jit_context_retrieval()  # must not raise
    assert flow.state.repo_context == []
```

`jit_context_retrieval` queries `business_context` directly and does not guard that call, so the schema must exist before it runs. The same applies to the `analysis_flow.run` tests in Task 5 — if they error on a missing table, add the same two `chdb_client` init calls, matching what `run_chat.py:50-51` does at startup.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python3 -m pytest tests/test_repo_qa.py -q -k "synthesis or state_carries or jit_context or cannot_break"`

Expected: FAIL — `AttributeError: module 'atlys_agentic.prompts' has no attribute 'build_repo_answer_synthesis_prompt'`.

- [ ] **Step 3: Add the corrected synthesis prompt builder**

Append to `src/atlys_agentic/prompts.py`. This replaces the miswired alias call — it takes exactly the arguments `_score_and_write` has, plus the two new blend inputs:

```python
def build_repo_answer_synthesis_prompt(
    question: str,
    spec_id: str,
    table_name: str,
    known_issue: str,
    cuts: dict,
    confidence: dict,
    repo_context_md: str = "",
    librarian_notes: str = "",
) -> str:
    """Construct the Product Analyst synthesis prompt for the chat analytics path.

    Distinct from `build_analytics_agent_synthesis_prompt`, which serves the full
    12-phase submission pipeline and requires phase outputs the chat path never
    computes. This builder takes exactly what the chat flow has on hand.
    """
    known_issue_line = (
        f"Matched known issue: {known_issue}\n" if known_issue else "No known issue matched this cohort pattern.\n"
    )
    spec_block = (
        f"\nRelevant feature specification and design documentation:\n{repo_context_md}\n"
        if repo_context_md
        else ""
    )
    librarian_block = (
        f"\nContext Librarian notes on applicable known issues:\n{librarian_notes}\n"
        if librarian_notes
        else ""
    )
    return (
        "You are the Product Analyst at Atlys. Write a concise, PM-actionable diagnosis.\n\n"
        f"Question: '{question}'\n"
        f"Feature domain: {spec_id} (table: {table_name})\n"
        f"{known_issue_line}"
        f"Live segment cuts analysed: {list(cuts.keys())}\n"
        f"Cut data: {cuts}\n"
        f"Confidence: {confidence}\n"
        f"{spec_block}"
        f"{librarian_block}\n"
        "Write 3-5 sentences covering: the headline finding with its magnitude, where the "
        "effect concentrates across the cuts, the likely mechanism, and the recommended next "
        "step. Where the feature specification above defines the intended funnel or an "
        "expected behaviour, state whether the observed data matches it and cite the source "
        "as `path:heading`. Do not invent numbers that are not in the cut data."
    )
```

- [ ] **Step 4: Add the two state fields**

In `src/atlys_agentic/flows/analysis_flow.py`, extend `AnalysisState`:

```python
class AnalysisState(BaseModel):
    question: str = ""
    spec_id: str = "01_express_checkout"
    table_name: str = "express_checkout"
    base_sql: str = ""
    trace_id: str = ""
    context_rows: list[dict] = []
    cuts: dict = {}
    sql_queries: list[str] = []
    known_issue_match: bool = False
    matched_known_issue: str = ""
    confidence: dict = {}
    answer_md: str = ""
    executive_summary: str = ""
    views: dict = {}
    repo_context: list[dict] = []
    librarian_notes: str = ""
```

Add `repo_index` to the module import on line 6:

```python
from atlys_agentic import agents, chdb_client, prompts, repo_index, repo_qa, tools, tracing
```

- [ ] **Step 5: Blend in `jit_context_retrieval` and stop dropping the librarian notes**

In `jit_context_retrieval`, the LLM block currently ends by assigning `librarian_notes` to a local that nothing reads. Change the assignment at what is currently line 300 from:

```python
                librarian_notes = resp.choices[0].message.content.strip()
```

to:

```python
                librarian_notes = resp.choices[0].message.content.strip()
                self.state.librarian_notes = librarian_notes
```

Then, immediately **before** the closing `tracing.span(...)` call of the method, insert:

```python
        # Feature specs and CUJ docs state the intended funnel, which the cut data alone
        # cannot. Additive only: a retrieval failure must never fail an analysis run.
        try:
            self.state.repo_context = repo_index.search(
                self.state.question,
                k=3,
                paths_prefix=("docs/", "problem statment/specs/"),
            )
        except Exception:
            self.state.repo_context = []
```

And extend that `tracing.span` output dict from:

```python
            {"rows": len(self.state.context_rows), "agent": context_librarian.role},
```

to:

```python
            {
                "rows": len(self.state.context_rows),
                "agent": context_librarian.role,
                "repo_chunks": len(self.state.repo_context),
            },
```

- [ ] **Step 6: Fix the synthesis call and pass the blend through**

In `_score_and_write`, replace the miswired call:

```python
                prompt = prompts.build_product_analyst_synthesis_prompt(
                    question=self.state.question,
                    spec_id=self.state.spec_id,
                    table_name=self.state.table_name,
                    known_issue=self.state.matched_known_issue if known_issue_match else "",
                    cuts=self.state.cuts,
                    confidence=self.state.confidence,
                )
```

with:

```python
                prompt = prompts.build_repo_answer_synthesis_prompt(
                    question=self.state.question,
                    spec_id=self.state.spec_id,
                    table_name=self.state.table_name,
                    known_issue=self.state.matched_known_issue if known_issue_match else "",
                    cuts=self.state.cuts,
                    confidence=self.state.confidence,
                    repo_context_md=repo_index.format_chunks_md(self.state.repo_context, max_chars=800),
                    librarian_notes=self.state.librarian_notes,
                )
```

Leave `prompts.build_product_analyst_synthesis_prompt` and its alias in place — `scripts/run_all_submissions.py` and the 12-phase pipeline may still reference the original name. Do not delete it.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `.venv/bin/python3 -m pytest tests/test_repo_qa.py -q`

Expected: 34 passed.

- [ ] **Step 8: Verify the synthesis call no longer raises**

Run:

```bash
.venv/bin/python3 -c "
from src.atlys_agentic import prompts
prompts.build_repo_answer_synthesis_prompt(
    question='q', spec_id='s', table_name='t', known_issue='',
    cuts={}, confidence={}, repo_context_md='', librarian_notes='')
print('synthesis prompt builds cleanly')
"
```

Expected: `synthesis prompt builds cleanly`, with no `TypeError`.

- [ ] **Step 9: Verify the full suite has not regressed**

Run: `.venv/bin/python3 -m pytest -q 2>&1 | tail -5`

Expected: the Task 0 baseline plus 34 new tests passing.

- [ ] **Step 10: Commit**

```bash
git add src/atlys_agentic/prompts.py src/atlys_agentic/flows/analysis_flow.py tests/test_repo_qa.py
git commit -m "feat(analysis_flow): blend feature specs into analytical answers

Adds build_repo_answer_synthesis_prompt, taking exactly the arguments the
chat flow has. The previous call passed spec_id/table_name/known_issue/cuts
to an alias of build_analytics_agent_synthesis_prompt, which accepts none of
them; the resulting TypeError was swallowed, so Product Analyst synthesis had
never run on this path.

Also stops dropping librarian_notes, and threads both it and the retrieved
feature spec into the synthesis prompt."
```

---

### Task 7: Update the documented contracts

**Files:**
- Modify: `docs/CUJ2.md`
- Modify: `docs/superpowers/specs/2026-08-03-analyst-repo-knowledge-design.md`

**Interfaces:**
- Consumes: the span and agent names emitted by Tasks 3 and 6
- Produces: documentation matching the emitted trace

- [ ] **Step 1: Confirm the emitted span and agent names**

Run:

```bash
grep -rn "repo_knowledge_retrieval\|repo_agent::answer\|repo_chunks\|Repository Knowledge Analyst" src/atlys_agentic/
```

Expected: `repo_knowledge_retrieval` and `repo_agent::answer` in `repo_qa.py`, `repo_chunks` in `analysis_flow.py`, and the role string in `agents.py`. Use exactly these strings in the docs — do not paraphrase them.

- [ ] **Step 2: Add the agent to the CUJ2 roster**

In `docs/CUJ2.md`, locate the agent roster section and add a row for the Repository Knowledge Analyst, matching the surrounding table's existing columns:

- Agent: `repo_agent`
- Role: `Atlys Repository Knowledge Analyst`
- Tools: `search_repo`, `read_repo_file`
- Purpose: answers questions about the system itself from its own documentation and source

- [ ] **Step 3: Add the spans to the CUJ2 span contract**

In the same file's span contract section, add:

| Span / generation | Emitted by | Metadata |
| :--- | :--- | :--- |
| `repo_knowledge_retrieval` | `repo_qa.answer` | `agent=repo_agent`; output carries `chunks` and `paths` |
| `repo_agent::answer` | `repo_qa.answer` | `agent=repo_agent`; generation, carries `why` |

Also note that the existing `jit_context_retrieval` span output now carries a `repo_chunks` count.

- [ ] **Step 4: Record the amendments in the spec document**

In `docs/superpowers/specs/2026-08-03-analyst-repo-knowledge-design.md`:

- In §5.1, add `docs/superpowers/` to the documented exclusion list, noting that our own plan and spec documents otherwise outrank the source documents they describe.
- In §5.7, replace the reference to threading context into the existing synthesis prompt with a note that the prompt call was miswired (a `TypeError` swallowed by a bare `except`), that `build_repo_answer_synthesis_prompt` was added to fix it, and that Product Analyst synthesis had never run on the chat path before this change.

- [ ] **Step 5: Verify the full suite one final time**

Run: `.venv/bin/python3 -m pytest -q 2>&1 | tail -5`

Expected: the Task 0 baseline plus all 34 new tests passing.

- [ ] **Step 6: Commit**

```bash
git add docs/CUJ2.md docs/superpowers/specs/2026-08-03-analyst-repo-knowledge-design.md
git commit -m "docs(cuj2): document the repo_agent roster entry and its spans

Records the two amendments discovered during implementation: the
docs/superpowers/ corpus exclusion, and the miswired synthesis prompt call."
```

---

## Manual Verification

After Task 7, confirm the feature end to end against a live LibreChat session, as described in `RUN.md`:

1. Start the backend: `.venv/bin/python3 -m uvicorn atlys_agentic.run_chat:app --port 8008`
2. Select the **Atlys Product Analyst** (`atlys-analyst`) model.
3. Ask *"how does the ingestion flow work?"* — expect a cited answer, not the out-of-scope refusal.
4. Ask *"what does the express checkout spec define as the funnel?"* — expect a citation of `problem statment/specs/01_express_checkout/spec.md`.
5. Ask *"why did express checkout conversion drop on iOS?"* — expect the normal analytical diagnosis, now referencing the spec's intended funnel.
6. Confirm in Langfuse that `repo_knowledge_retrieval` and `repo_agent::answer` appear for steps 3-4, and that `product_analyst::gemini_synthesis` now appears for step 5 (it never did before Task 6).
