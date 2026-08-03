# Analyst Repo Knowledge — Design

Date: 2026-08-03
Status: Approved for planning
Scope: `atlys-analyst` (CUJ 2) chat surface only. The `atlys-instrumentation` (CUJ 1) path is not modified.

## 1. Problem

The Product Analyst chat surface can answer telemetry questions and can list workspace paths and specs. It cannot answer questions about the system itself.

Current behaviour for a question like *"how does the ingestion flow work?"* or *"what is CUJ 2?"*:

1. `run_chat.py:252` falls through to `analysis_flow.run(question=...)`.
2. `analysis_flow.run` calls `classify_question_intent_with_llm` (`analysis_flow.py:91`), whose prompt (`prompts.build_intent_classifier_system_prompt`) offers exactly four intents: `analytical | greeting | abusive | out_of_scope`.
3. A question about this repository is not analytical, so it classifies as `out_of_scope`.
4. `analysis_flow.py:671` returns `prompts.OUT_OF_SCOPE_RESPONSE_MD` with `confidence 0.0`.

The user gets a polite refusal for a question the system has every document needed to answer. The repository ships `README.md`, `ARCHITECTURE.md`, `RUN.md`, `atlys_tech_design.md`, `base_context.md`, `docs/CUJ1.md`, `docs/CUJ2.md`, `docs/cuj_architecture.md`, `problem statment/PROBLEM_STATEMENT.md` and six `spec.md` files — roughly 450 KB of markdown — none of which is reachable from chat.

A second, smaller defect sits on the same seam. `jit_context_retrieval` (`analysis_flow.py:300`) computes `librarian_notes` from the Context Librarian LLM call, emits it to Langfuse, and then drops it. Nothing downstream consumes it. The blend work below touches this exact code path, so the fix belongs here.

## 2. Goals

- The Analyst answers questions about this system's docs, architecture, CUJ definitions, setup, feature specs, and source code.
- Genuine analytical answers are enriched with the relevant feature spec, so a funnel diagnosis can cite the intended funnel rather than SQL alone.
- The locked CUJ 1 demo path is untouched.
- No change to the response contract consumed by `run_chat.py` or `POST /api/analyze/query`.

## 3. Non-Goals

- No embedding index, no vector store, no persisted index. Keyword prefiltering plus agentic file reads is the chosen mechanism.
- No write access to the repository from the agent. Read-only tools only.
- No change to `conversational_ingestion.detect_chat_intent`. Its regex ladder stays as-is.
- No change to the `atlys-instrumentation` model branch in `run_chat.py`.

## 4. Retrieval Approach

Hybrid: a cheap deterministic keyword prefilter selects candidate chunks, then a CrewAI agent reads further with tools if the prefilter was not sufficient.

Rejected alternatives and why:

- **Pure agentic tools.** No index and no staleness, but every question costs two to four LLM turns even when one document obviously answers it.
- **Pure keyword chunk injection.** One LLM call and fully deterministic, but weak on paraphrase — *"how do I start it"* does not lexically overlap `RUN.md`.
- **Embedding index.** Best recall, but needs an index build, a rebuild trigger on file change, and an embedding call per query. Not justified for 128 tracked files.

The hybrid gets single-call latency on the common case and keeps a recall escape hatch for the rest.

## 5. Components

### 5.1 `src/atlys_agentic/repo_index.py`

Corpus and keyword prefilter. No dependencies beyond stdlib and `git`.

Corpus selection:

- Source of truth is `git ls-files`, so untracked scratch files and build output never enter the corpus.
- Include `*.md` and `src/**/*.py`.
- Exclude `.worktrees/**` (stale duplicates of `src/`), `*.ndjson` (telemetry data, 21 MB, belongs in ClickHouse not in a prompt), `outputs/**`, and `uv.lock`.

Chunking:

- Markdown splits at `##` and `###` headings. Each chunk keeps its file path and heading trail.
- Python splits at top-level `def` and `class`. Each chunk keeps its path and symbol name.
- A chunk records `path`, `heading`, `text`, and `start_line`.

Scoring:

- Tokenize the question, lowercase, drop a small stopword set.
- Score each chunk by term overlap against its text.
- Boost matches that occur in the chunk's path or heading, which are far more discriminative than body text.

Public surface:

```python
def search(question: str, k: int = 5, paths_prefix: tuple[str, ...] | None = None) -> list[dict]
```

`paths_prefix` restricts the search to a subtree, used by the analytics blend to look only at `docs/` and `spec.md` files.

The index builds lazily on first call and is held at module level for the process lifetime.

`ponytail:` term-overlap scoring, no embeddings and no persistence. Swap in vector search when keyword recall measurably fails on real questions.

### 5.2 `src/atlys_agentic/tools_repo.py`

Two CrewAI tools, both read-only.

- `search_repo(query: str) -> list` — wraps `repo_index.search`, returns path, heading, and a snippet per hit.
- `read_repo_file(path: str, start: int = 0, end: int = 200) -> str` — bounded read of a repository file.

**Path jail.** `read_repo_file` resolves the requested path and rejects anything that is not inside the repository root:

```python
target = (paths.REPO_ROOT / path).resolve()
if not target.is_relative_to(paths.REPO_ROOT.resolve()):
    return "Error: path outside repository root."
```

This is not optional. The path argument originates from LLM output on a network-exposed endpoint, so it is an untrusted input at a trust boundary. The same check rejects absolute paths and `..` traversal. Reads are additionally capped in line count so a single call cannot flood the context window.

### 5.3 `agents.py: build_repo_agent()`

A CrewAI `Agent` following the existing builder pattern in `agents.py`.

- Role: `Atlys Repository Knowledge Analyst`
- Goal: answer questions about this system's own documentation, architecture, CUJ definitions, setup, feature specs, and source code, citing the files used.
- Tools: `search_repo`, `read_repo_file`
- `allow_delegation=False`, `memory=False`, `max_iter=5`, consistent with the other builders.

### 5.4 `src/atlys_agentic/repo_qa.py`

```python
def answer(question: str) -> dict
```

Flow:

1. `repo_index.search(question, k=5)` for the prefilter.
2. Build a CrewAI `Task` whose description carries the question plus the prefiltered chunks as starting context, and instructs the agent to call `search_repo` or `read_repo_file` only when the provided context is insufficient.
3. `Crew(agents=[repo_agent], tasks=[task]).kickoff()`.
4. Return the standard analysis response dict so no caller changes:

```python
{
  "answer_md": ...,
  "executive_summary": ...,
  "confidence": {"score": ..., "rationale": "Answered from repository documentation."},
  "known_issue_match": False,
  "matched_known_issue": "",
  "cuts": {},
  "views": {"conversion_trend": [], "segment_waterfall": [], "metric_deltas": []},
  "sql_queries": [],
  "spec_id": "repo_knowledge",
  "table_name": "none",
  "trace_id": ...,
}
```

Answers cite sources as `path:heading`.

If no API key is configured, or under `PYTEST_CURRENT_TEST`, `answer` skips the LLM and returns a markdown digest of the prefiltered chunks. This matches the existing offline-degradation convention used throughout `analysis_flow.py` and keeps the test suite hermetic.

### 5.5 Classifier change

`prompts.build_intent_classifier_system_prompt` gains a fifth intent:

```
5. 'repo_knowledge': Questions about THIS system itself — its architecture,
   CUJ definitions, setup or run instructions, feature spec documents, schema
   design rationale, or source code. These are questions about the software,
   not questions about product telemetry.
```

The JSON schema line in the same prompt is updated to
`"intent": "analytical" | "greeting" | "abusive" | "out_of_scope" | "repo_knowledge"`,
and `direct_response` stays `null` for `repo_knowledge` since the answer comes from the repo agent, not the classifier.

`_heuristic_classify_intent` (`analysis_flow.py:132`), the deterministic offline fallback, gains a matching branch. Without it the offline path and the test suite would route repository questions to `analytical` and attempt SQL against a table that does not exist.

The boundary between `repo_knowledge` and `analytical` is stated explicitly in the prompt: a question about what the system *is or does* is `repo_knowledge`; a question about what the telemetry *shows* is `analytical`. *"What does the express checkout spec define as the funnel?"* is `repo_knowledge`. *"Why did express checkout conversion drop?"* is `analytical`.

### 5.6 `analysis_flow.run` branch

A new branch alongside the existing guardrail branches at `analysis_flow.py:671`:

```python
elif intent == "repo_knowledge":
    return repo_qa.answer(question)
```

Placed inside the existing `is_guardrails_enabled(...)` block, so disabling guardrails disables repo Q&A along with the other guardrail intents. That is the consistent behaviour.

### 5.7 Analytics blend

In `jit_context_retrieval` (`analysis_flow.py:259`), after the business-context rows are fetched:

- `self.state.repo_context = repo_index.search(self.state.question, k=3, paths_prefix=("docs/", "problem statment/specs/"))`
- `self.state.librarian_notes = librarian_notes` — the fix for the value currently computed and dropped at line 300.

Both fields are added to `AnalysisState` with empty defaults. Both are threaded into the answer-composition prompt so a funnel diagnosis can reference the spec's intended funnel and the librarian's known-issue reasoning.

The blend is additive. If `repo_index.search` returns nothing, or raises, the analytical path produces exactly what it produces today. The call is wrapped so a retrieval failure can never fail an analysis run.

## 6. Tracing

Consistent with the span contract in `docs/CUJ2.md`.

- Span `repo_knowledge_retrieval` — input the question, output the count of prefiltered chunks and their paths.
- Generation `repo_agent::answer` — `metadata.agent = "repo_agent"`, with model, usage, and a `why` field, matching the convention used by `context_librarian::jit_retrieval`.
- The existing `jit_context_retrieval` span output gains a `repo_chunks` count.

`docs/CUJ2.md` is updated with the new agent and the two new span names so the documented contract matches the emitted trace.

## 7. Error Handling

- Corpus build failure, for example `git ls-files` unavailable: `repo_index` returns an empty corpus, `repo_qa.answer` returns a plain "repository index unavailable" markdown response, and the analytics blend degrades to today's behaviour.
- Tool call on a non-existent path: `read_repo_file` returns an error string the agent can act on, rather than raising.
- Path outside the repository root: rejected with an error string, never read.
- LLM failure inside `repo_qa.answer`: falls back to the prefiltered-chunk digest, the same degradation used when no API key is present.
- The analytics blend is wrapped so that no repo-retrieval failure can break an analysis run.

## 8. Testing

One new file, `tests/test_repo_qa.py`, hermetic and offline:

- `search("how do I run the backend")` places `RUN.md` or `README.md` in the top three hits.
- `search("what is CUJ 2")` places `docs/CUJ2.md` in the top three hits.
- `read_repo_file("../../etc/passwd")` is rejected, and `read_repo_file("/etc/passwd")` is rejected.
- `read_repo_file("README.md")` succeeds and respects the line cap.
- `_heuristic_classify_intent("how does the ingestion flow work?")` returns `repo_knowledge`.
- `repo_qa.answer(...)` under `PYTEST_CURRENT_TEST` returns the standard response dict shape with `spec_id == "repo_knowledge"`.

Existing suites must stay green, in particular `tests/test_cuj2_analytics_flow.py` and `tests/test_chat_backend.py`, which cover the classifier and the chat contract.

## 9. Files Touched

New:

- `src/atlys_agentic/repo_index.py`
- `src/atlys_agentic/tools_repo.py`
- `src/atlys_agentic/repo_qa.py`
- `tests/test_repo_qa.py`

Modified:

- `src/atlys_agentic/prompts.py` — fifth classifier intent, updated JSON schema line
- `src/atlys_agentic/agents.py` — `build_repo_agent()` and its two tool wrappers
- `src/atlys_agentic/flows/analysis_flow.py` — `repo_knowledge` branch, heuristic fallback branch, two new `AnalysisState` fields, blend in `jit_context_retrieval`, `librarian_notes` fix
- `docs/CUJ2.md` — new agent and span names

Unchanged: `run_chat.py`, `conversational_ingestion.py`, `flows/ingestion_flow.py`, and every CUJ 1 code path.

## 10. Decisions Recorded

- Retrieval is a keyword prefilter feeding an agentic tool loop. Not embeddings.
- Routing is a fifth intent on the existing LLM classifier. Not a new regex ladder, and not a post-hoc fallback after a wasted analysis run.
- The blend into genuine analytical answers is in scope, and carries the `librarian_notes` fix with it.
- The corpus excludes `.worktrees/`, `*.ndjson`, and `outputs/`.
- Answers cite `path:heading`.
- Repository tools are read-only, and `read_repo_file` is jailed to the repository root.
