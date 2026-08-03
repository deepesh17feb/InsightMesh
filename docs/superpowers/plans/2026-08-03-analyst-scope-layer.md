# Analyst Simple Scope Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the `atlys-analyst` chat surface answer questions about its own responsibilities and this system's architecture, and recognize ingestion questions specifically to redirect them — using one LLM call, not a retrieval layer or an agent.

**Architecture:** Two new intents (`repo_knowledge`, `ingestion_redirect`) extend the classifier that `analysis_flow.run` already calls, which today returns a canned `direct_response` for `greeting`/`abusive`/`out_of_scope` in the same call it classifies with. `repo_knowledge` is grounded by embedding four documents' full text directly in the classifier's system prompt — no index, no chunking, no agent, no file-read tool. `ingestion_redirect` returns a fixed message. The offline heuristic fallback gets matching pattern blocks for both.

**Tech Stack:** Python 3.11, litellm, pydantic, pytest 8.

**Spec:** `docs/superpowers/specs/2026-08-03-analyst-scope-layer-design.md`

**Supersedes:** `docs/superpowers/plans/2026-08-03-analyst-repo-knowledge.md`. Task 0 below removes that plan's Tasks 1-4 (the keyword index, the read-only file tools with their path jail, and the CrewAI repo agent), which are committed on this same branch at `6ada3e8..d4999ad`. That plan's own Task 0 (a Python 3.11 f-string fix, commit `9c93684`) is independent and stays.

## Global Constraints

- **Python 3.11.** Run everything through the venv: `.venv/bin/python3 -m pytest`. A bare `python` is not on PATH; a bare `python3` is `/usr/bin/python3` and has no dependencies installed.
- **One LLM call.** No retrieval, no chunking, no keyword index, no CrewAI agent, no file-read tool. `repo_knowledge` grounding is four documents' full text, embedded directly in the classifier's system prompt string, read fresh (with a simple in-process cache) from disk.
- **`docs/CUJ2-simple.md` describes actual current behavior**, not the aspirational locked design in `docs/CUJ2.md` — e.g. the real cut dimensions are `device_type`, `geoip_country_code`, `destination` (`analysis_flow.py:41`, `_MANDATORY_CUT_DIMENSIONS`), not the five cuts the locked doc describes as a target. Do not embed claims the running code doesn't back.
- **The `has_analytical` guard must NOT gate the new `repo_patterns`/`ingestion_patterns` blocks** in `_heuristic_classify_intent`. A telemetry-sounding word can coexist with a system or ingestion question without changing which intent should win.
- **The response dict returned by `analysis_flow.run` is a contract.** `run_chat.py` and `POST /api/analyze/query` both consume it. Every return path must produce all eleven keys: `answer_md`, `executive_summary`, `confidence`, `known_issue_match`, `matched_known_issue`, `cuts`, `views`, `sql_queries`, `spec_id`, `table_name`, `trace_id`.
- **Offline degradation is mandatory** wherever an LLM call already happens (`classify_question_intent_with_llm`, `_score_and_write`) — these call sites already guard on the API key and `PYTEST_CURRENT_TEST`; do not weaken that guard.
- **Do not modify** `run_chat.py`, `conversational_ingestion.py`, `flows/ingestion_flow.py`, or any CUJ 1 code path. `prompts.py` must not import `conversational_ingestion` (that module already imports `prompts`; the reverse would cycle).
- **`agents.py` ends this plan in exactly its pre-Task-0-of-the-old-plan state** (i.e. matching commit `9c93684`) — nothing in this plan adds to it.

## File Structure

**Removed by Task 0:** `src/atlys_agentic/repo_index.py`, `tools_repo.py`, `repo_qa.py`, `tests/test_repo_qa.py`; the `build_repo_agent`/tool-wrapper additions in `agents.py`; the `build_repo_qa_task_description` addition and the `repo_knowledge`-intent text in `prompts.py`; the `repo_patterns`/`repo_knowledge` block in `analysis_flow.py`'s heuristic.

**New:**

| File | Responsibility |
| :--- | :--- |
| `docs/CUJ2-simple.md` | Plain-language description of the Analyst, quoted directly to users. Source content for the classifier prompt, not developer documentation. |
| `tests/test_analyst_scope_layer.py` | Covers the new prompt content, the two heuristic intents, the two `run()` branches, and the synthesis-prompt bug fix. |

**Modified:**

| File | Change |
| :--- | :--- |
| `src/atlys_agentic/prompts.py` | `_load_repo_knowledge_context()` doc-embedding helper; two new classifier intents; `INGESTION_REDIRECT_RESPONSE_MD`; `REPO_KNOWLEDGE_FALLBACK_MD`; `build_chat_synthesis_prompt` (bug fix). |
| `src/atlys_agentic/flows/analysis_flow.py` | Two new pattern blocks in `_heuristic_classify_intent`; `_direct_response_dict` helper; two new branches (plus the existing three refactored onto the same helper) in `run`; corrected call site in `_score_and_write`. |

---

### Task 0: Remove the superseded repo-knowledge implementation

The prior design (keyword index + CrewAI agent + path-jailed file tools) is being replaced before it ever merged. Three files it touched need reverting to their pre-that-work state, and four files it added need deleting.

**Files:**
- Revert (checkout from `9c93684`): `src/atlys_agentic/agents.py`, `src/atlys_agentic/prompts.py`, `src/atlys_agentic/flows/analysis_flow.py`
- Delete: `src/atlys_agentic/repo_index.py`, `src/atlys_agentic/tools_repo.py`, `src/atlys_agentic/repo_qa.py`, `tests/test_repo_qa.py`

**Interfaces:**
- Consumes: nothing
- Produces: a codebase at exactly commit `9c93684`'s state for these three files, with the four new files gone. Every later task in this plan builds from that baseline.

- [ ] **Step 1: Confirm the exact commits involved**

Run: `git log --oneline 9c93684..HEAD -- src/atlys_agentic/repo_index.py src/atlys_agentic/tools_repo.py src/atlys_agentic/repo_qa.py tests/test_repo_qa.py src/atlys_agentic/agents.py src/atlys_agentic/prompts.py src/atlys_agentic/flows/analysis_flow.py`

Expected output includes exactly these six commits (newest first): `d4999ad`, `adf2d05`, `5749d4f`, `5a38a41`, `9468c2e`, `913e934`, `a892bdb`, `6ada3e8` — the full stack built after `9c93684`. If any commit is missing or an extra one appears, stop and report `BLOCKED` rather than guessing.

- [ ] **Step 2: Revert the three touched files to their pre-existing state**

```bash
git checkout 9c93684 -- src/atlys_agentic/agents.py src/atlys_agentic/prompts.py src/atlys_agentic/flows/analysis_flow.py
```

- [ ] **Step 3: Delete the four new files**

```bash
git rm src/atlys_agentic/repo_index.py src/atlys_agentic/tools_repo.py src/atlys_agentic/repo_qa.py tests/test_repo_qa.py
```

- [ ] **Step 4: Verify the diff is exactly a revert**

Run: `git diff --stat 9c93684 -- src/atlys_agentic/agents.py src/atlys_agentic/prompts.py src/atlys_agentic/flows/analysis_flow.py`

Expected: empty output — no difference between the working tree and commit `9c93684` for these three files.

- [ ] **Step 5: Run the full suite and confirm the Task-0-of-the-old-plan baseline**

Run: `.venv/bin/python3 -m pytest -q 2>&1 | tail -5`

Expected: `63 passed, 12 failed` — exactly what the old plan's Task 0 review recorded right after the f-string fix, before any repo-knowledge code existed. The 12 are pre-existing and unrelated; do not investigate or fix them here.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "revert: remove superseded repo-knowledge implementation

The keyword-index + CrewAI-agent + path-jailed-file-tools design (commits
6ada3e8..d4999ad) is replaced by a simpler single-LLM-call design before
merging. See docs/superpowers/specs/2026-08-03-analyst-scope-layer-design.md
for what replaces it. The Python 3.11 f-string fix from the same branch
(9c93684) is unrelated and stays."
```

---

### Task 1: `docs/CUJ2-simple.md`

**Files:**
- Create: `docs/CUJ2-simple.md`
- Test: `tests/test_analyst_scope_layer.py`

**Interfaces:**
- Consumes: nothing
- Produces: a file that Task 2's `_load_repo_knowledge_context()` reads by exact relative path `docs/CUJ2-simple.md`

- [ ] **Step 1: Write the failing test**

Create `tests/test_analyst_scope_layer.py`:

```python
"""Analyst scope layer — hermetic, no network calls."""
from atlys_agentic import paths


def test_cuj2_simple_exists_and_is_reasonably_sized():
    doc = paths.REPO_ROOT / "docs" / "CUJ2-simple.md"
    assert doc.exists()
    text = doc.read_text(encoding="utf-8")
    assert len(text) > 200
    assert len(text.encode("utf-8")) < 10_000  # embedding ceiling: short enough to embed on every call
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python3 -m pytest tests/test_analyst_scope_layer.py -q`

Expected: FAIL — `assert doc.exists()` is false.

- [ ] **Step 3: Create the file**

Create `docs/CUJ2-simple.md` with exactly this content:

```markdown
# CUJ 2 — What the Analyst Does (Plain-Language Summary)

This is a short, plain-language description of the Atlys Product Analyst, written to be
quoted directly to a user who asks what this system does or how it works. It describes the
system's *actual current behavior*, not aspirational or planned capabilities. For the full
locked design specification, engineers should read `docs/CUJ2.md`.

## What it is

The Atlys Product Analyst is a chat-based analytics assistant. A product manager asks a
natural-language question about product telemetry — a conversion funnel, a drop-off, a
segment comparison — and the Analyst investigates it directly against the live ClickHouse
event data and returns a plain-English diagnosis with a confidence score and a trace link.

## What it does not do

The Analyst does not design database schemas, generate DDL, or run data ingestion. Adding a
new feature's telemetry to the system is a separate job, owned by a different model in this
same chat interface: the **Instrumentation Engineer** (`atlys-instrumentation`). If a question
is about ingesting a spec, proposing a table, or ClickHouse schema design, the right place to
ask it is that model, not this one.

The Analyst also does not run arbitrary SQL on request, and does not fabricate a number when
the data cannot answer the question — it says so plainly instead.

## How it investigates a question

1. **Pull relevant context.** Before looking at any numbers, the Analyst checks its business
   context layer for known issues and metric definitions relevant to the question — so a
   drop that matches a previously logged regression is recognized as such, not treated as new.
2. **Resolve the feature domain.** It works out which feature and which ClickHouse table the
   question is actually about (express checkout, group/family applications, abandoned
   checkout recovery, multi-currency pricing, and so on).
3. **Run the segment cuts.** It aggregates the relevant event data inside ClickHouse — never
   pulling raw rows into the conversation — cut by segment dimensions that matter for
   diagnosis, at minimum device type, country, and destination.
4. **Check for a known-issue match.** If the pattern in the data lines up with something
   already logged in the business context layer, the answer says so explicitly instead of
   re-diagnosing from scratch.
5. **Score confidence.** Every answer carries a confidence score, based on sample size,
   effect size, and whether a known issue was matched — not a flat, unexplained number.
6. **Write the answer.** The final response states the headline finding, where in the data it
   concentrates, the likely mechanism, and a concrete next step.

## What it's good at answering

- Conversion and funnel drop-off diagnosis ("is there an iOS OTP drop on Express Checkout
  during verification?")
- Segment comparisons (by device, by country, by destination)
- Whether a pattern matches a previously known issue, or looks new
- Confidence-scored, PM-actionable summaries rather than raw charts

## Traceability

Every answer the Analyst gives links to a Langfuse trace, so the reasoning chain behind a
diagnosis — which context was pulled, which cuts were run, which known issue (if any) was
matched — can be inspected, not just trusted.
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python3 -m pytest tests/test_analyst_scope_layer.py -q`

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add docs/CUJ2-simple.md tests/test_analyst_scope_layer.py
git commit -m "docs(cuj2): add plain-language Analyst summary for LLM grounding

Describes actual current behavior (analysis_flow.py's real cut dimensions
and phase order), not the aspirational locked design in docs/CUJ2.md, so the
classifier prompt that embeds this file cannot claim capabilities the code
doesn't have."
```

---

### Task 2: Two new classifier intents — prompt embedding and offline heuristic

**Files:**
- Modify: `src/atlys_agentic/prompts.py`
- Modify: `src/atlys_agentic/flows/analysis_flow.py:132-194` (`_heuristic_classify_intent`)
- Test: `tests/test_analyst_scope_layer.py` (append)

**Interfaces:**
- Consumes: `docs/CUJ2-simple.md` (Task 1), `paths.REPO_ROOT`
- Produces:
  - `prompts._load_repo_knowledge_context() -> str`
  - `prompts.INGESTION_REDIRECT_RESPONSE_MD: str`
  - `prompts.REPO_KNOWLEDGE_FALLBACK_MD: str`
  - `prompts.build_intent_classifier_system_prompt(...)` documenting six intents: `analytical | greeting | abusive | out_of_scope | repo_knowledge | ingestion_redirect`
  - `_heuristic_classify_intent` returning `{"intent": "repo_knowledge", ...}` and `{"intent": "ingestion_redirect", ...}` for matching questions

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_analyst_scope_layer.py`:

```python
from atlys_agentic import prompts
from atlys_agentic.flows import analysis_flow


def test_repo_knowledge_context_embeds_all_four_docs_and_excludes_the_fifth():
    context = prompts._load_repo_knowledge_context()
    assert "CUJ 2 — What the Analyst Does" in context  # docs/CUJ2-simple.md
    assert "InsightMesh" in context or "Atlys" in context  # README.md sanity check
    assert len(context) > 20_000  # four real docs, not a stub


def test_classifier_prompt_documents_all_six_intents():
    text = prompts.build_intent_classifier_system_prompt()
    assert '"analytical" | "greeting" | "abusive" | "out_of_scope" | "repo_knowledge" | "ingestion_redirect"' in text
    assert "repo_knowledge" in text
    assert "ingestion_redirect" in text
    assert "atlys-instrumentation" in text


def test_classifier_prompt_embeds_the_repo_knowledge_context():
    text = prompts.build_intent_classifier_system_prompt()
    assert "CUJ 2 — What the Analyst Does" in text


def test_heuristic_routes_system_questions_to_repo_knowledge():
    for question in [
        "what is CUJ 2?",
        "how do you diagnose a drop?",
        "how does the analytics agent work?",
        "how do i run the backend?",
        "tell me about this system's architecture",
    ]:
        assert analysis_flow._heuristic_classify_intent(question)["intent"] == "repo_knowledge", question


def test_heuristic_routes_ingestion_questions_to_ingestion_redirect():
    for question in [
        "ingest a new spec",
        "propose a schema for the new feature",
        "what's the DDL for the express checkout table?",
        "create table for group family applications",
    ]:
        assert analysis_flow._heuristic_classify_intent(question)["intent"] == "ingestion_redirect", question


def test_heuristic_still_classifies_the_original_four_intents_correctly():
    assert analysis_flow._heuristic_classify_intent("hello")["intent"] == "greeting"
    assert analysis_flow._heuristic_classify_intent("you are stupid")["intent"] == "abusive"
    assert analysis_flow._heuristic_classify_intent("tell me a joke")["intent"] == "out_of_scope"
    assert analysis_flow._heuristic_classify_intent(
        "why did express checkout conversion drop on iOS?"
    )["intent"] == "analytical"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python3 -m pytest tests/test_analyst_scope_layer.py -q -k "repo_knowledge or classifier or heuristic"`

Expected: FAIL — `AttributeError: module 'atlys_agentic.prompts' has no attribute '_load_repo_knowledge_context'`.

- [ ] **Step 3: Add the doc-embedding helper and two new response constants to `prompts.py`**

`prompts.py` currently has no imports. Add one at the top, right after the module docstring:

```python
"""Centralized prompt templates for Atlys Agentic LLM evaluations and guardrails.

Keeps system prompts and prompt templates separated from flow execution logic.
"""
from atlys_agentic import paths
```

`paths.py` has no dependency on `prompts.py`, so this does not create an import cycle.

Then append, anywhere after the imports (a natural spot is right before `build_intent_classifier_system_prompt`):

```python
_REPO_KNOWLEDGE_DOC_PATHS = ("docs/CUJ2-simple.md", "README.md", "ARCHITECTURE.md", "RUN.md")
_repo_knowledge_context_cache: str | None = None


def _load_repo_knowledge_context() -> str:
    """Embed this system's own documentation for the classifier's 'repo_knowledge' intent.

    Read fresh from disk once per process and cached — there is no index and no chunking.
    atlys_tech_design.md is deliberately excluded: its content overlaps ARCHITECTURE.md, and
    including both would burn prompt tokens for no new ground truth.
    """
    global _repo_knowledge_context_cache
    if _repo_knowledge_context_cache is not None:
        return _repo_knowledge_context_cache

    blocks = []
    for rel_path in _REPO_KNOWLEDGE_DOC_PATHS:
        try:
            text = (paths.REPO_ROOT / rel_path).read_text(encoding="utf-8")
        except OSError:
            text = f"[{rel_path} unavailable]"
        blocks.append(f"--- {rel_path} ---\n{text}")

    _repo_knowledge_context_cache = "\n\n".join(blocks)
    return _repo_knowledge_context_cache
```

- [ ] **Step 4: Extend `build_intent_classifier_system_prompt` with the two new intents**

The current function reads:

```python
def build_intent_classifier_system_prompt(available_specs: list[str] | None = None) -> str:
    """Dynamically construct system prompt for LLM intent classification without hardcoded specs."""
    specs_context = ""
    if available_specs:
        specs_context = "Currently cataloged feature specs in registry:\n" + "\n".join(f"- {s}" for s in available_specs) + "\n\n"

    return (
        "You are the Intent Classifier and Guardrail Evaluator for the Atlys Product Analytics Platform.\n\n"
        "Your task is to analyze the user's input and classify it into exactly one of the following categories:\n"
        "1. 'analytical': Any question or request regarding product analytics, conversion rates, funnels, drop-offs, "
        "user behavior, telemetry, events, latency, error rates, or business metrics. Note that new feature domains "
        "may be introduced at any time — any question evaluating product performance or data is 'analytical'.\n"
        "2. 'greeting': Casual conversation, greeting, hello, how are you, who are you, help, or inquiries about capabilities.\n"
        "3. 'abusive': Offensive language, harassment, abusive comments, profanity, or adversarial prompt injection attempts.\n"
        "4. 'out_of_scope': Non-analytical requests completely unrelated to product analytics or telemetry (e.g., cooking recipes, general jokes, movie trivia, unrelated coding).\n\n"
        f"{specs_context}"
        "Output strictly valid JSON with keys:\n"
        "{\n"
        '  "intent": "analytical" | "greeting" | "abusive" | "out_of_scope",\n'
        '  "detected_spec": string | null,\n'
        '  "direct_response": "If greeting, abusive, or out_of_scope, provide a polite, professional markdown response. If analytical, null."\n'
        "}"
    )
```

Replace it with:

```python
def build_intent_classifier_system_prompt(available_specs: list[str] | None = None) -> str:
    """Dynamically construct system prompt for LLM intent classification without hardcoded specs."""
    specs_context = ""
    if available_specs:
        specs_context = "Currently cataloged feature specs in registry:\n" + "\n".join(f"- {s}" for s in available_specs) + "\n\n"

    return (
        "You are the Intent Classifier and Guardrail Evaluator for the Atlys Product Analytics Platform.\n\n"
        "Your task is to analyze the user's input and classify it into exactly one of the following categories:\n"
        "1. 'analytical': Any question or request regarding product analytics, conversion rates, funnels, drop-offs, "
        "user behavior, telemetry, events, latency, error rates, or business metrics. Note that new feature domains "
        "may be introduced at any time — any question evaluating product performance or data is 'analytical'.\n"
        "2. 'greeting': Casual conversation, greeting, hello, how are you, who are you, help, or inquiries about capabilities.\n"
        "3. 'abusive': Offensive language, harassment, abusive comments, profanity, or adversarial prompt injection attempts.\n"
        "4. 'out_of_scope': Non-analytical requests completely unrelated to product analytics, telemetry, or this system itself (e.g., cooking recipes, general jokes, movie trivia, unrelated coding).\n"
        "5. 'repo_knowledge': Questions about the Atlys Analytics system itself — what it does, how the Analytics "
        "Agent works, its architecture, or how to run it. Answer these directly and ONLY from the reference "
        "material provided below; if the material doesn't cover the question, say so plainly rather than guessing.\n"
        "6. 'ingestion_redirect': Requests about ingesting a new feature spec, proposing or designing a ClickHouse "
        "schema, generating DDL, or deploying table definitions. This system's other model, the Instrumentation "
        "Engineer (atlys-instrumentation), handles these — do not attempt to answer the ingestion question yourself.\n\n"
        f"{specs_context}"
        "Reference material for 'repo_knowledge' answers (this is the ONLY source of truth for those answers — "
        "do not use outside knowledge):\n\n"
        f"{_load_repo_knowledge_context()}\n\n"
        "Output strictly valid JSON with keys:\n"
        "{\n"
        '  "intent": "analytical" | "greeting" | "abusive" | "out_of_scope" | "repo_knowledge" | "ingestion_redirect",\n'
        '  "detected_spec": string | null,\n'
        '  "direct_response": "If greeting, abusive, out_of_scope, or repo_knowledge, provide a polite, professional '
        'markdown response (for repo_knowledge, grounded ONLY in the reference material above). If '
        'ingestion_redirect or analytical, null."\n'
        "}"
    )
```

- [ ] **Step 5: Add the two new response constants**

Append to `prompts.py`, near the existing `OUT_OF_SCOPE_RESPONSE_MD`:

```python
INGESTION_REDIRECT_RESPONSE_MD = """### 🛠️ That's an Ingestion Question — Different Model

I'm the **Atlys Product Analyst** — I diagnose telemetry, funnels, and conversion, but I don't design schemas, generate DDL, or run ingestion myself.

That's the job of the **Instrumentation Engineer** (`atlys-instrumentation`). Select that model from the dropdown, and it can propose a ClickHouse schema, walk through the storage design, and deploy it once you approve.

Happy to help once you're back with a telemetry or funnel question."""


REPO_KNOWLEDGE_FALLBACK_MD = """### ℹ️ About the Atlys Product Analyst

I couldn't put together a specific answer to that from my own documentation, but here's what I do: I diagnose product telemetry — conversion funnels, drop-offs, segment comparisons — for Atlys features, using live ClickHouse data and a confidence-scored answer.

Try asking about a specific funnel or metric, or ask "what is CUJ 2?" for an overview of how I work."""
```

- [ ] **Step 6: Add the two new pattern blocks to `_heuristic_classify_intent`**

The current function ends with:

```python
    out_of_scope_patterns = [
        r"\bweather\b",
        r"\brecipe\b",
        r"\bpoem\b",
        r"\bjoke\b",
        r"\bstory\b",
        r"\bcapital of\b",
        r"\btranslate\b",
    ]
    if not has_analytical and any(re.search(p, q_lower) for p in out_of_scope_patterns):
        return {
            "intent": "out_of_scope",
            "detected_spec": None,
            "response": prompts.OUT_OF_SCOPE_RESPONSE_MD,
        }

    inferred_spec, _ = infer_domain_from_question(question)
    return {"intent": "analytical", "detected_spec": inferred_spec, "response": None}
```

Insert two new blocks between the `out_of_scope_patterns` block and the final `inferred_spec` line:

```python
    out_of_scope_patterns = [
        r"\bweather\b",
        r"\brecipe\b",
        r"\bpoem\b",
        r"\bjoke\b",
        r"\bstory\b",
        r"\bcapital of\b",
        r"\btranslate\b",
    ]
    if not has_analytical and any(re.search(p, q_lower) for p in out_of_scope_patterns):
        return {
            "intent": "out_of_scope",
            "detected_spec": None,
            "response": prompts.OUT_OF_SCOPE_RESPONSE_MD,
        }

    # Questions about this system itself, as opposed to what the telemetry shows. Checked
    # after greeting/abuse/out-of-scope, before the ingestion and analytical checks. Not
    # gated by has_analytical: "how do you diagnose a drop?" is a meta-question about the
    # Analyst's process, not a request to actually run that diagnosis.
    repo_patterns = [
        r"\bcuj\s*2\b",
        r"\b(readme|architecture)\b",
        r"\bthis (system|repo|repository|codebase)\b",
        r"\bhow do you (diagnose|analyze|investigate|work)\b",
        r"\bhow does (this|the) (analyst|analytics agent|system) work\b",
        r"\bhow do i run (this|the backend|the stack)\b",
        r"\bwhat is (this|the) (analytics agent|product analyst)\b",
    ]
    if any(re.search(p, q_lower) for p in repo_patterns):
        return {"intent": "repo_knowledge", "detected_spec": None, "response": None}

    # Ingestion / schema-design vocabulary — recognized specifically so the redirect is
    # friendly and accurate, not a generic out-of-scope refusal. Also not gated by
    # has_analytical: a question can mention an analytical word and still be fundamentally
    # about schema design ("propose a schema so we can measure the conversion drop").
    ingestion_patterns = [
        r"\bingest\b",
        r"\bschema\b",
        r"\bddl\b",
        r"\bpropose (a )?(table|schema)\b",
        r"\bcreate table\b",
        r"\binstrument(ation)?\b",
    ]
    if any(re.search(p, q_lower) for p in ingestion_patterns):
        return {"intent": "ingestion_redirect", "detected_spec": None, "response": None}

    inferred_spec, _ = infer_domain_from_question(question)
    return {"intent": "analytical", "detected_spec": inferred_spec, "response": None}
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `.venv/bin/python3 -m pytest tests/test_analyst_scope_layer.py -q`

Expected: 7 passed (1 from Task 1, 6 new).

- [ ] **Step 8: Regression-check the existing classifier behavior**

Run: `.venv/bin/python3 -m pytest tests/test_cuj2_analytics_flow.py tests/test_chat_backend.py -q`

Expected: identical to the Task 0 baseline (`63 passed, 12 failed` was the pre-existing full-suite count; these two files' own pass/fail counts should be unchanged from before this task). If a previously-passing test now fails, a new pattern is stealing a question it shouldn't — narrow that pattern rather than weakening the test.

- [ ] **Step 9: Commit**

```bash
git add src/atlys_agentic/prompts.py src/atlys_agentic/flows/analysis_flow.py tests/test_analyst_scope_layer.py
git commit -m "feat(classifier): add repo_knowledge and ingestion_redirect intents

Both ride the classifier's existing direct_response mechanism — one LLM
call, no retrieval. repo_knowledge is grounded by embedding four documents'
full text in the system prompt (CUJ2-simple.md, README, ARCHITECTURE, RUN).
ingestion_redirect recognizes ingestion vocabulary specifically instead of
lumping it into a generic out_of_scope refusal."
```

---

### Task 3: Route the two new intents in `analysis_flow.run`

**Files:**
- Modify: `src/atlys_agentic/flows/analysis_flow.py` (the `run` function, and its guardrail block)
- Test: `tests/test_analyst_scope_layer.py` (append)

**Interfaces:**
- Consumes: `prompts.INGESTION_REDIRECT_RESPONSE_MD`, `prompts.REPO_KNOWLEDGE_FALLBACK_MD` (Task 2)
- Produces: `_direct_response_dict(answer_md, summary, score, rationale, spec_id) -> dict`; `analysis_flow.run` returning the standard contract for `repo_knowledge` and `ingestion_redirect`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_analyst_scope_layer.py`:

```python
_RESPONSE_KEYS = {
    "answer_md", "executive_summary", "confidence", "known_issue_match",
    "matched_known_issue", "cuts", "views", "sql_queries", "spec_id",
    "table_name", "trace_id",
}


def test_run_routes_a_system_question_to_repo_knowledge():
    result = analysis_flow.run(question="what is CUJ 2?", spec_id="chat")
    assert result["spec_id"] == "repo_knowledge"
    assert set(result) == _RESPONSE_KEYS


def test_run_routes_an_ingestion_question_to_the_redirect():
    result = analysis_flow.run(question="ingest a new spec", spec_id="chat")
    assert result["spec_id"] == "ingestion_redirect"
    assert "atlys-instrumentation" in result["answer_md"]
    assert set(result) == _RESPONSE_KEYS


def test_run_still_answers_telemetry_questions_analytically():
    result = analysis_flow.run(question="why did express checkout conversion drop on iOS?", spec_id="chat")
    assert result["spec_id"] not in ("repo_knowledge", "ingestion_redirect")


def test_disabling_guardrails_disables_both_new_routes():
    for question in ("what is CUJ 2?", "ingest a new spec"):
        result = analysis_flow.run(question=question, spec_id="chat", enable_guardrails=False)
        assert result["spec_id"] not in ("repo_knowledge", "ingestion_redirect")


def test_greeting_abusive_and_out_of_scope_are_unaffected_by_the_refactor():
    assert analysis_flow.run(question="hello", spec_id="chat")["spec_id"] == "conversational"
    assert analysis_flow.run(question="you are stupid", spec_id="chat")["spec_id"] == "abusive_deescalation"
    assert analysis_flow.run(question="tell me a joke", spec_id="chat")["spec_id"] == "out_of_scope"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python3 -m pytest tests/test_analyst_scope_layer.py -q -k "run_routes or disabling or unaffected"`

Expected: FAIL — `repo_knowledge`/`ingestion_redirect` currently fall through to the `analytical` path, so `result["spec_id"]` is not what the test expects.

- [ ] **Step 3: Add the `_direct_response_dict` helper and refactor the guardrail block**

The current `run` function's guardrail block reads:

```python
    # Conversational & Scope Guardrails (configurable)
    if is_guardrails_enabled(enable_guardrails):
        decision = classify_question_intent_with_llm(question)
        intent = decision.get("intent", "analytical")
        if intent == "greeting":
            greeting_md = decision.get("response") or prompts.GREETING_RESPONSE_MD
            return {
                "answer_md": greeting_md,
                "executive_summary": "Atlys Product Analyst ready. Ask a question regarding feature funnels, conversion rates, or telemetry anomalies.",
                "confidence": {"score": 1.0, "rationale": "Conversational greeting acknowledged."},
                "known_issue_match": False,
                "matched_known_issue": "",
                "cuts": {},
                "views": {"conversion_trend": [], "segment_waterfall": [], "metric_deltas": []},
                "sql_queries": [],
                "spec_id": "conversational",
                "table_name": "none",
                "trace_id": "",
            }
        elif intent == "abusive":
            abusive_md = decision.get("response") or prompts.ABUSIVE_RESPONSE_MD
            return {
                "answer_md": abusive_md,
                "executive_summary": "Inappropriate or abusive query de-escalated respectfully.",
                "confidence": {"score": 0.0, "rationale": "Community conduct standard applied."},
                "known_issue_match": False,
                "matched_known_issue": "",
                "cuts": {},
                "views": {"conversion_trend": [], "segment_waterfall": [], "metric_deltas": []},
                "sql_queries": [],
                "spec_id": "abusive_deescalation",
                "table_name": "none",
                "trace_id": "",
            }
        elif intent == "out_of_scope":
            out_of_scope_md = decision.get("response") or prompts.OUT_OF_SCOPE_RESPONSE_MD
            return {
                "answer_md": out_of_scope_md,
                "executive_summary": "Query out of scope for Atlys product analytics.",
                "confidence": {"score": 0.0, "rationale": "Query is outside the scope of product analytics."},
                "known_issue_match": False,
                "matched_known_issue": "",
                "cuts": {},
                "views": {"conversion_trend": [], "segment_waterfall": [], "metric_deltas": []},
                "sql_queries": [],
                "spec_id": "out_of_scope",
                "table_name": "none",
                "trace_id": "",
            }
```

Replace it with (this both adds the two new branches and refactors the existing three onto one helper, so there is exactly one place the eleven-key shape is built for all five canned-answer intents):

```python
    # Conversational & Scope Guardrails (configurable)
    if is_guardrails_enabled(enable_guardrails):
        decision = classify_question_intent_with_llm(question)
        intent = decision.get("intent", "analytical")
        if intent == "greeting":
            greeting_md = decision.get("response") or prompts.GREETING_RESPONSE_MD
            return _direct_response_dict(
                greeting_md,
                "Atlys Product Analyst ready. Ask a question regarding feature funnels, conversion rates, or telemetry anomalies.",
                1.0,
                "Conversational greeting acknowledged.",
                "conversational",
            )
        elif intent == "abusive":
            abusive_md = decision.get("response") or prompts.ABUSIVE_RESPONSE_MD
            return _direct_response_dict(
                abusive_md,
                "Inappropriate or abusive query de-escalated respectfully.",
                0.0,
                "Community conduct standard applied.",
                "abusive_deescalation",
            )
        elif intent == "out_of_scope":
            out_of_scope_md = decision.get("response") or prompts.OUT_OF_SCOPE_RESPONSE_MD
            return _direct_response_dict(
                out_of_scope_md,
                "Query out of scope for Atlys product analytics.",
                0.0,
                "Query is outside the scope of product analytics.",
                "out_of_scope",
            )
        elif intent == "repo_knowledge":
            repo_md = decision.get("response") or prompts.REPO_KNOWLEDGE_FALLBACK_MD
            return _direct_response_dict(
                repo_md,
                f"Answered '{question}' from Atlys Analytics system documentation.",
                0.8,
                "Answered from embedded system documentation, grounded in the repository's own docs.",
                "repo_knowledge",
            )
        elif intent == "ingestion_redirect":
            redirect_md = decision.get("response") or prompts.INGESTION_REDIRECT_RESPONSE_MD
            return _direct_response_dict(
                redirect_md,
                "Ingestion request redirected to the Instrumentation Engineer.",
                0.0,
                "Ingestion and schema design are handled by a different model (atlys-instrumentation).",
                "ingestion_redirect",
            )
```

Note the `0.8` confidence for `repo_knowledge`: unlike the other four canned intents, which have an unambiguous fixed score, this one is answering a real question from grounded but LLM-synthesized text, so `0.8` reflects "grounded but not independently verified" rather than the certainty of a template greeting or a rule-based refusal.

- [ ] **Step 4: Add the `_direct_response_dict` helper function**

Add this as a module-level function in `flows/analysis_flow.py`, above `def run(`:

```python
def _direct_response_dict(answer_md: str, summary: str, score: float, rationale: str, spec_id: str) -> dict:
    """Build the standard analysis response dict for a canned, non-analytical answer.

    Used by every guardrail branch in `run` (greeting, abusive, out_of_scope, repo_knowledge,
    ingestion_redirect) so there is exactly one place this eleven-key shape is constructed.
    """
    return {
        "answer_md": answer_md,
        "executive_summary": summary,
        "confidence": {"score": score, "rationale": rationale},
        "known_issue_match": False,
        "matched_known_issue": "",
        "cuts": {},
        "views": {"conversion_trend": [], "segment_waterfall": [], "metric_deltas": []},
        "sql_queries": [],
        "spec_id": spec_id,
        "table_name": "none",
        "trace_id": "",
    }
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python3 -m pytest tests/test_analyst_scope_layer.py -q`

Expected: 12 passed (7 from Tasks 1-2, 5 new).

- [ ] **Step 6: Regression-check**

Run: `.venv/bin/python3 -m pytest tests/test_cuj2_analytics_flow.py tests/test_chat_backend.py -q && .venv/bin/python3 -m pytest -q 2>&1 | tail -5`

Expected: no change from the counts recorded after Task 2's Step 8.

- [ ] **Step 7: Commit**

```bash
git add src/atlys_agentic/flows/analysis_flow.py tests/test_analyst_scope_layer.py
git commit -m "feat(analysis_flow): route repo_knowledge and ingestion_redirect

Both return the standard eleven-key response contract via a new
_direct_response_dict helper, which also now backs the three existing
canned-answer branches (greeting/abusive/out_of_scope) so there is one place
that shape is built. run_chat.py and /api/analyze/query need no change."
```

---

### Task 4: Fix the Product Analyst synthesis prompt signature

Independent of this redesign, but real and cheap to fix: `_score_and_write` calls a prompt builder with keyword arguments the function doesn't accept, and the resulting `TypeError` is swallowed silently.

**Files:**
- Modify: `src/atlys_agentic/prompts.py` (append `build_chat_synthesis_prompt`)
- Modify: `src/atlys_agentic/flows/analysis_flow.py:543-581` (`_score_and_write`)
- Test: `tests/test_analyst_scope_layer.py` (append)

**Interfaces:**
- Consumes: nothing new
- Produces: `prompts.build_chat_synthesis_prompt(question, spec_id, table_name, known_issue, cuts, confidence) -> str`

- [ ] **Step 1: Confirm the defect**

Run:

```bash
.venv/bin/python3 -c "
from src.atlys_agentic import prompts
prompts.build_product_analyst_synthesis_prompt(
    question='q', spec_id='s', table_name='t', known_issue='', cuts={}, confidence={})
"
```

Expected: `TypeError: build_analytics_agent_synthesis_prompt() got an unexpected keyword argument 'spec_id'` — confirming `build_product_analyst_synthesis_prompt` (an alias, `prompts.py:277`, for `build_analytics_agent_synthesis_prompt`, `prompts.py:152`) does not accept the arguments `_score_and_write` passes it at `analysis_flow.py:546`. The bare `except Exception: pass` at `analysis_flow.py:580` swallows this every time, so the Product Analyst synthesis LLM call has never executed on the chat path — `executive_summary` is always the template string built at `analysis_flow.py:529-533`.

- [ ] **Step 2: Write the failing test**

Append to `tests/test_analyst_scope_layer.py`:

```python
import inspect


def test_chat_synthesis_prompt_accepts_what_score_and_write_actually_passes():
    params = inspect.signature(prompts.build_chat_synthesis_prompt).parameters
    for required in ("question", "spec_id", "table_name", "known_issue", "cuts", "confidence"):
        assert required in params, required


def test_chat_synthesis_prompt_builds_without_raising():
    text = prompts.build_chat_synthesis_prompt(
        question="why did express checkout drop?",
        spec_id="01_express_checkout",
        table_name="express_checkout",
        known_issue="K1: OTP autofill regression",
        cuts={"device_type": []},
        confidence={"score": 0.8, "rationale": "n=100"},
    )
    assert "express_checkout" in text
    assert "K1" in text
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `.venv/bin/python3 -m pytest tests/test_analyst_scope_layer.py -q -k synthesis`

Expected: FAIL — `AttributeError: module 'atlys_agentic.prompts' has no attribute 'build_chat_synthesis_prompt'`.

- [ ] **Step 4: Add the corrected prompt builder**

Append to `src/atlys_agentic/prompts.py`:

```python
def build_chat_synthesis_prompt(
    question: str,
    spec_id: str,
    table_name: str,
    known_issue: str,
    cuts: dict,
    confidence: dict,
) -> str:
    """Construct the Product Analyst synthesis prompt for the chat analytics path.

    Distinct from `build_analytics_agent_synthesis_prompt`, which serves the full 12-phase
    submission pipeline and requires phase outputs the chat path never computes. This builder
    takes exactly what `_score_and_write` has on hand.
    """
    known_issue_line = (
        f"Matched known issue: {known_issue}\n" if known_issue else "No known issue matched this cohort pattern.\n"
    )
    return (
        "You are the Product Analyst at Atlys. Write a concise, PM-actionable diagnosis.\n\n"
        f"Question: '{question}'\n"
        f"Feature domain: {spec_id} (table: {table_name})\n"
        f"{known_issue_line}"
        f"Live segment cuts analysed: {list(cuts.keys())}\n"
        f"Cut data: {cuts}\n"
        f"Confidence: {confidence}\n\n"
        "Write 3-5 sentences covering: the headline finding with its magnitude, where the "
        "effect concentrates across the cuts, the likely mechanism, and the recommended next "
        "step. Do not invent numbers that are not in the cut data."
    )
```

Leave `build_product_analyst_synthesis_prompt` and its alias exactly as they are — `scripts/run_all_submissions.py` and the 12-phase pipeline may still reference that name. Do not delete it.

- [ ] **Step 5: Fix the call site in `_score_and_write`**

The current call reads:

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

Replace it with:

```python
                prompt = prompts.build_chat_synthesis_prompt(
                    question=self.state.question,
                    spec_id=self.state.spec_id,
                    table_name=self.state.table_name,
                    known_issue=self.state.matched_known_issue if known_issue_match else "",
                    cuts=self.state.cuts,
                    confidence=self.state.confidence,
                )
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/python3 -m pytest tests/test_analyst_scope_layer.py -q`

Expected: 14 passed (12 from Tasks 1-3, 2 new).

- [ ] **Step 7: Confirm the synthesis call no longer raises**

Run:

```bash
.venv/bin/python3 -c "
from src.atlys_agentic import prompts
prompts.build_chat_synthesis_prompt(
    question='q', spec_id='s', table_name='t', known_issue='', cuts={}, confidence={})
print('synthesis prompt builds cleanly')
"
```

Expected: `synthesis prompt builds cleanly`, no `TypeError`.

- [ ] **Step 8: Run the full suite one final time**

Run: `.venv/bin/python3 -m pytest -q 2>&1 | tail -5`

Expected: the Task 0 baseline (`63 passed, 12 failed`) plus all 14 new tests passing — `77 passed, 12 failed`. The 12 are pre-existing and unrelated.

- [ ] **Step 9: Commit**

```bash
git add src/atlys_agentic/prompts.py src/atlys_agentic/flows/analysis_flow.py tests/test_analyst_scope_layer.py
git commit -m "fix(analysis_flow): correct the Product Analyst synthesis prompt call

The call at _score_and_write passed spec_id/table_name/known_issue/cuts to
build_product_analyst_synthesis_prompt, an alias for
build_analytics_agent_synthesis_prompt, which accepts none of them. The
resulting TypeError was swallowed by a bare except, so this LLM call has
never once executed on the chat path. build_chat_synthesis_prompt takes
exactly the arguments this call site has."
```

---

## Manual Verification

After Task 4, confirm end to end against a live LibreChat session, per `RUN.md`:

1. Start the backend: `.venv/bin/python3 -m uvicorn atlys_agentic.run_chat:app --port 8008`
2. Select the **Atlys Product Analyst** (`atlys-analyst`) model.
3. Ask *"what is CUJ 2?"* — expect an answer grounded in `docs/CUJ2-simple.md`, not the out-of-scope refusal.
4. Ask *"ingest a new spec for group family applications"* — expect the friendly redirect to `atlys-instrumentation`, not a generic out-of-scope message and not an attempt to actually answer.
5. Ask *"why did express checkout conversion drop on iOS?"* — expect the normal analytical diagnosis, and confirm in Langfuse that `product_analyst::gemini_synthesis` now appears (it never did before Task 4).
