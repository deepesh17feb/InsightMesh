# Analyst Simple Scope Layer — Design

Date: 2026-08-03
Status: Approved for planning
Scope: `atlys-analyst` (CUJ 2) chat surface only. The `atlys-instrumentation` (CUJ 1) path is not modified.

**Supersedes:** `docs/superpowers/specs/2026-08-03-analyst-repo-knowledge-design.md` and
`docs/superpowers/plans/2026-08-03-analyst-repo-knowledge.md`. That design built a keyword
index plus a CrewAI agent with read-only file-access tools. Mid-implementation, the goal was
reconsidered in favor of something simpler: one LLM call, grounded in embedded doc text, no
retrieval and no agentic tool loop. This document replaces that approach. The two documents
above stay in git history as a record of the earlier design; they are not deleted.

## 1. Problem

Unchanged from the superseded spec: on the Analyst chat surface, a question about the system
itself — "what is CUJ 2?", "how do you diagnose a drop?" — classifies as `out_of_scope` via
`classify_question_intent_with_llm` (`analysis_flow.py:91`) and dead-ends with
`prompts.OUT_OF_SCOPE_RESPONSE_MD`.

A second, related gap: a question about ingestion — "ingest a new spec", "what's the DDL for
X" — also falls into `out_of_scope`, a generic and slightly rude refusal, when the system
knows exactly what the user wants and which other model handles it.

## 2. Goals

- The Analyst answers questions about its own responsibilities, this system's architecture,
  and how to run it, from grounded document text.
- The Analyst recognizes ingestion questions specifically and responds with a friendly,
  accurate redirect to the `atlys-instrumentation` model, rather than a generic refusal.
- Analytics questions behave exactly as they do today.
- One LLM call. No retrieval, no keyword index, no agentic tool loop, no new attack surface.

## 3. Non-Goals

- No repository-wide search. The scope of "repo knowledge" is the four documents named below,
  not arbitrary source files. A question needing something outside them gets an honest "I
  don't have that" rather than a tool-driven file read.
- No change to the `atlys-instrumentation` model branch in `run_chat.py`, and no change to
  `conversational_ingestion.py`.
- The Analyst does not answer ingestion/schema/DDL questions itself — it redirects. Answering
  them would blur the CUJ1/CUJ2 model split that `ANALYST_SCOPE_NOTICE_MD` already encodes
  elsewhere in the codebase.

## 4. Approach

Extend the LLM call that already exists. `classify_question_intent_with_llm`
(`analysis_flow.py:91`) already returns a `direct_response` for `greeting`, `abusive`, and
`out_of_scope` — the classifier writes the canned answer itself, in the same call, no second
LLM turn. This design adds two more intents to that same mechanism instead of building a
separate answer-generation module:

| Intent | Trigger | Response |
| :--- | :--- | :--- |
| `repo_knowledge` | "what is CUJ 2?", "how do you diagnose a drop?", "what's this architecture?" | `direct_response`, written by the classifier LLM, grounded in doc text embedded in its own system prompt |
| `ingestion_redirect` | "ingest a new spec", "propose a schema for X", "what's the DDL for Y" | A fixed, friendly message pointing to `atlys-instrumentation` |

Six intents total: `analytical | greeting | abusive | out_of_scope | repo_knowledge |
ingestion_redirect`.

### 4.1 Grounding content for `repo_knowledge`

Embedded as plain text inside `prompts.build_intent_classifier_system_prompt`'s system prompt.
No index, no chunking, no scoring — the classifier reads the whole thing on every call.

| Source | Size | Included? |
| :--- | :--- | :--- |
| `docs/CUJ2-simple.md` (new) | ~4-6 KB | Yes — the Analyst's own role and process |
| `README.md` | 17 KB | Yes — project overview, setup |
| `ARCHITECTURE.md` | 24 KB | Yes — system design, agent roster, tracing |
| `RUN.md` | 4 KB | Yes — how to run the stack |
| `atlys_tech_design.md` | 9 KB | **No** — content overlaps `ARCHITECTURE.md`; including both burns tokens for no new ground truth |

Total embedded: ≈ 51 KB, comfortably inside a single system prompt.

The prompt instructs the classifier to answer `repo_knowledge` questions only from the
supplied text, and to say plainly when the supplied text does not cover something, rather than
inventing an answer.

### 4.2 `docs/CUJ2-simple.md` — new file

`docs/CUJ2.md` is a 731-line locked design document: span contracts, phase-by-phase acceptance
criteria, worked examples, extended goals. It documents the *target* design, which is not
identical to what `analysis_flow.py` currently implements — for example, it specifies vector
retrieval over a `table_semantics` table for domain resolution, while the current code
(`infer_domain_from_question`) uses a keyword ladder. Embedding the full document risks the
Analyst claiming capabilities the running code does not have.

`docs/CUJ2-simple.md` is a condensed, ~100-150 line document written to describe what the
system *actually does*, for direct consumption by the classifier prompt:

- What CUJ 2 is and who asks it questions (a PM, in natural language)
- The Analyst's role and its boundaries (analyzes telemetry; does not design schemas or run
  ingestion — that's CUJ 1)
- The pipeline in plain terms, matching the real phases in `analysis_flow.py`: pull relevant
  business context → run the question against the five mandatory cuts (`device_type`,
  `geoip_country_code`, `destination`, plus two more) → check whether the pattern matches a
  known issue → score confidence → write the answer
- What kinds of questions it answers well (funnel drop-offs, conversion rates, segment
  comparisons, anomaly diagnosis) and what it explicitly does not do (ingestion, schema
  design, raw SQL access)
- A short paragraph on traceability (every answer links a Langfuse trace)

This file is *source content* for the prompt, not developer documentation — it is written to
be quoted back to a user, not to specify implementation.

### 4.3 The ingestion redirect message

A new constant in `prompts.py`, `INGESTION_REDIRECT_RESPONSE_MD`, textually close to the
existing `ANALYST_SCOPE_NOTICE_MD` in `conversational_ingestion.py` but not imported from it —
`conversational_ingestion.py` is not touched by this design, and `prompts.py` must not import
from it (`conversational_ingestion.py` already imports `prompts`; the reverse would cycle).
Content: acknowledge the request is about ingestion, state plainly that the Analyst doesn't
do that, name the `atlys-instrumentation` model as the right one, in one short friendly
paragraph.

### 4.4 Offline / heuristic path

`_heuristic_classify_intent` (`analysis_flow.py:132`), the deterministic fallback used with no
API key or under `PYTEST_CURRENT_TEST`, gains two matching pattern blocks, checked after the
existing `greeting`/`out_of_scope` blocks and before the `analytical` default:

- **`repo_knowledge` patterns** — recognize questions about the system itself: `cuj`,
  `readme`, `architecture`, `repo(sitory)`, `how do you diagnose`, `what can you do`-adjacent
  system questions, `how do I run`. Returns a short canned `direct_response` (no doc grounding
  available offline — same degradation convention already used for `greeting` and
  `out_of_scope`).
- **`ingestion_redirect` patterns** — recognize ingestion vocabulary: `ingest`, `schema`,
  `ddl`, `propose (a )?(table|schema)`, `create table`, `instrument`. Returns
  `INGESTION_REDIRECT_RESPONSE_MD`.

Neither pattern block is gated by the existing `has_analytical` guard, for the same reason
established in the superseded design: "how do I run the backend" contains no analytical
keyword, and a pattern like `schema` could coexist with an analytical word in a real sentence
without changing which intent should win.

### 4.5 `analysis_flow.run`

Two new branches beside the existing guardrail branches (`analysis_flow.py:~671`), each
returning the standard response dict built inline from the classifier's `direct_response` (or
the offline canned text) — no new module, no new import beyond what's already there:

```python
elif intent == "repo_knowledge":
    return _direct_response_dict(direct_response, spec_id="repo_knowledge")
elif intent == "ingestion_redirect":
    return _direct_response_dict(
        direct_response or prompts.INGESTION_REDIRECT_RESPONSE_MD,
        spec_id="ingestion_redirect",
    )
```

A small `_direct_response_dict(text, spec_id)` helper (module-level function in
`analysis_flow.py`) builds the eleven-key contract, mirroring the existing `greeting` /
`abusive` / `out_of_scope` return blocks so there is exactly one place that shape is
constructed for these five canned-answer intents.

## 5. What Gets Removed From The Branch

The prior implementation (`docs/superpowers/plans/2026-08-03-analyst-repo-knowledge.md`,
commits `6ada3e8..d4999ad` on `feat/analyst-repo-knowledge`) is removed:

- `src/atlys_agentic/repo_index.py` — the keyword index
- `src/atlys_agentic/tools_repo.py` — `search_repo` / `read_repo_file`, including the path
  jail. Removing this removes the attack surface it defended, since there is no longer an
  LLM-driven file-read tool to defend against.
- `src/atlys_agentic/repo_qa.py` — the CrewAI agent + Crew/Task invocation
- The `build_repo_agent`, `_search_repo_tool`, `_read_repo_file_tool` additions in `agents.py`
- The `build_repo_qa_task_description` addition in `prompts.py`
- The `repo_knowledge` classifier-prompt text and `repo_patterns` heuristic block added in the
  superseded Task 4 (replaced by this design's own, differently-scoped versions of both)
- `tests/test_repo_qa.py` in its entirety (replaced by a new test file for this design)

**Kept:** `tools_cuj1.py`'s Python 3.11 f-string fix (commit `9c93684`) — an independent,
unrelated bug that must stay fixed regardless of this pivot.

## 6. A Second Independent Bug, Still In Scope

Unrelated to this redesign but discovered during the superseded design's planning and still
real: `analysis_flow.py:546` calls `prompts.build_product_analyst_synthesis_prompt(question=,
spec_id=, table_name=, known_issue=, cuts=, confidence=)`, an alias (`prompts.py:277`) for
`build_analytics_agent_synthesis_prompt`, which accepts none of those keyword arguments. The
resulting `TypeError` is swallowed by the bare `except Exception: pass` at
`analysis_flow.py:580`, so the Product Analyst synthesis LLM call has never executed on the
chat path — `executive_summary` is always the template string, and
`product_analyst::gemini_synthesis` never reaches Langfuse.

This design does not require touching that prompt (there is no repo-context blend anymore),
but the bug is real, independent, and cheap to fix, so it is folded into the implementation
plan as its own task: a `build_chat_synthesis_prompt` taking exactly the arguments
`_score_and_write` has on hand.

## 7. Error Handling

- If the classifier LLM call fails entirely (network error, bad API key), the existing
  fallback in `classify_question_intent_with_llm` already drops to
  `_heuristic_classify_intent` — this design adds no new failure mode there.
- If the classifier returns `repo_knowledge` or `ingestion_redirect` with an empty
  `direct_response` (LLM produced nothing), `analysis_flow.run` falls back to a fixed default
  message rather than returning blank content to the chat UI.

## 8. Testing

New file `tests/test_analyst_scope_layer.py`, hermetic and offline:

- `docs/CUJ2-simple.md` exists and is non-empty, and is short enough to embed
  (sanity ceiling, e.g. under 10 KB).
- `prompts.build_intent_classifier_system_prompt()` contains the text of `CUJ2-simple.md`,
  `README.md`, `ARCHITECTURE.md`, `RUN.md`, and does **not** contain `atlys_tech_design.md`
  content.
- `_heuristic_classify_intent` routes system-about-itself questions to `repo_knowledge`.
- `_heuristic_classify_intent` routes ingestion vocabulary to `ingestion_redirect`.
- `_heuristic_classify_intent` still routes telemetry questions to `analytical`, greetings to
  `greeting`, abuse to `abusive` — no regression on the existing four intents.
- `analysis_flow.run` for both new intents returns the full eleven-key response contract.
- `prompts.build_chat_synthesis_prompt` (the bug fix from §6) accepts the arguments
  `_score_and_write` actually passes, and builds without raising.

Existing suites must stay green: `tests/test_cuj2_analytics_flow.py`,
`tests/test_chat_backend.py`.

## 9. Files Touched

**Removed:** `src/atlys_agentic/repo_index.py`, `tools_repo.py`, `repo_qa.py`,
`tests/test_repo_qa.py`; the `build_repo_agent`/tool-wrapper additions in `agents.py`; the
`build_repo_qa_task_description` addition in `prompts.py`.

**New:** `docs/CUJ2-simple.md`, `tests/test_analyst_scope_layer.py`.

**Modified:** `src/atlys_agentic/prompts.py` (system prompt embeds four docs; two new
constants: `INGESTION_REDIRECT_RESPONSE_MD`, and `build_chat_synthesis_prompt` for §6's fix);
`src/atlys_agentic/flows/analysis_flow.py` (two new intents in `_heuristic_classify_intent`,
two new branches plus `_direct_response_dict` helper in `run`, the `_score_and_write` call-site
fix from §6).

**Unchanged:** `run_chat.py`, `conversational_ingestion.py`, `flows/ingestion_flow.py`,
`agents.py` (net zero — additions from the superseded design are removed, nothing new added
here in this design), every CUJ 1 code path.

## 10. Decisions Recorded

- One LLM call, extending the existing classifier's `direct_response` pattern. Not a second
  module, not a retrieval layer, not an agent.
- Grounding is direct text embedding of four documents (README, ARCHITECTURE, RUN,
  CUJ2-simple), not a keyword index and not chunked retrieval.
- `atlys_tech_design.md` is excluded — redundant with `ARCHITECTURE.md`.
- Ingestion questions are recognized specifically and redirected amicably to
  `atlys-instrumentation`; the Analyst never answers them itself.
- `docs/CUJ2-simple.md` describes actual current behavior, not the aspirational locked design
  in `docs/CUJ2.md`, to avoid the Analyst claiming capabilities the code doesn't have.
- The keyword-index/CrewAI-agent/path-jail stack from the superseded design is removed, not
  left in place unused.
- The independent synthesis-prompt signature bug (§6) is fixed here since it's cheap and real,
  even though it's unrelated to this pivot.
