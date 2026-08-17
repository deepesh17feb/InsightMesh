# InsightMesh — Critical Review & Improvement Plan

Scope: `src/atlys_agentic` (agents/flows/tools) + `frontend/` (Next.js UI). Generated from direct code reading, not speculation — file:line refs included.

## P0 — Broken / wrong right now

1. **Product Analyst LLM synthesis never runs — silent signature mismatch.**
   `analysis_flow.py:498-505` calls
   `prompts.build_product_analyst_synthesis_prompt(question=, spec_id=, table_name=, known_issue=, cuts=, confidence=)`
   but `prompts.py:60` defines the function as
   `(question, interpretation, headline, cuts_summary, correlation, timing_k_match, context_applied, trend_info, confidence)`.
   Every call raises `TypeError`, caught by the bare `except Exception: pass` at `analysis_flow.py:532`, so the flow silently falls back to the templated `executive_summary` string built at line 481. **The core "AI insight" is template text, not an LLM answer, in every live run.** No test exercises this call with real kwargs (`tests/test_cuj2_analytics_flow.py` mocks the Langfuse client only, never reaches this call).
   Fix: rewrite `build_product_analyst_synthesis_prompt` to accept the args the flow actually has, or fix the call site. Add one test that calls it with real args and asserts no `TypeError`.

2. **Fabricated fallback data presented as real insight.**
   `analysis_flow.py:426-444` — when live chDB/ClickHouse queries fail or the table lacks the queried columns, `conversion_trend` and `segment_waterfall` fall back to **hardcoded fake numbers** (`iOS 2302 / 3.0%`, dates `2026-07-28`...). Same pattern in `run_multi_cut_analysis` (`analysis_flow.py:329-335`): a failed cut silently becomes `[{"dim": dim, "events": 100}]`. Nothing in the API response or UI marks these as synthetic. A user reading the InsightCard cannot tell a real ClickHouse result from a canned placeholder.
   Fix: tag `views`/`cuts` with a `"source": "live" | "fallback"` field per series; render a visible "estimated / no live data" badge in `InsightCard.tsx` instead of hiding it.

3. **Mandatory cut dimensions assume columns that don't exist on every table.**
   `_MANDATORY_CUT_DIMENSIONS = ("device_type", "geoip_country_code", "destination")` (`analysis_flow.py:9`) is applied to every table regardless of schema (e.g. `purchase_completed` may not have `geoip_country_code`). Missing-column queries throw, get swallowed, and produce finding #2's fake row. Fix: derive cut dimensions from the table's actual columns (already available via `tools_cuj2.Tool_Load_Table_Semantics`) instead of a fixed tuple.

## P0 — Security

4. **Unauthenticated production write endpoint.**
   `run_chat.py:110` `POST /api/ingest/approve` executes DDL directly against ClickHouse Cloud (`ingestion_flow.deploy_approved_proposal` → `Tool_Execute_DDL`) with zero auth, no API key, no rate limit, no CORS restriction. The service is deployed publicly on Render (`render.yaml`). Anyone with the URL can run schema changes against the production database. Same exposure for `/api/analyze/query` (arbitrary Gemini spend) and `/v1/chat/completions`.
   Fix: add a shared-secret header (or proper auth) checked via FastAPI `Depends`, at minimum on `/api/ingest/approve`; add basic rate limiting.

5. **SQL built via f-string interpolation of identifiers/values throughout.**
   E.g. `tools_orchestrator.py:151`, `tools_cuj2.py:196`, `tools_cuj2.py:256`, `mcp_server.py:71/93` — table names and other values are spliced directly into SQL strings. Current inputs happen to come from filenames/internal enums, not raw user text, so it's not exploitable today, but the pattern is one refactor away from a real injection (e.g. if `table_hint` from chat ever reaches these paths unchecked — `conversational_ingestion.py` passes `table_hint` from parsed chat text into flows that eventually hit these functions). Fix: parameterize where the client supports it, or at minimum whitelist identifiers against `schema_registry`/`available_spec_ids()` before interpolating.

## P1 — Reliability / observability

6. **58 bare `except Exception: pass` blocks in `src/atlys_agentic`** (grep count). This is the direct cause of #1 being invisible for as long as it has been. No logging call anywhere in the flows/tools code — failures vanish with zero trace. Fix: at minimum `logging.exception(...)` inside every swallowed except in the two flow files and `tools_common.py`; reserve silent fallback for genuinely optional paths (e.g. Langfuse flush).

7. **Duplicated backend base URL default** (`"https://insightmesh-backend.onrender.com"`) hardcoded in both `frontend/app/api/analyze/query/route.ts:11` and `frontend/app/api/chat/route.ts:11`. One env var, two copies to keep in sync. Fix: single constant/module, or require the env var and fail fast if unset.

8. **`agents.py` builds a full CrewAI `Agent` (role/goal/backstory/LLM) for every call but the flows never invoke `agent.execute_task` or `kickoff()`** — they call `litellm.completion` directly and only use the `Agent` object for `.role`/`.backstory` string interpolation (`analysis_flow.py:488-509`, `ingestion_flow.py:118-141`). The `crewai` dependency (and its `Agent`/`Flow` machinery) is carrying almost no weight versus writing these as plain Python functions + prompt strings — the `@start/@listen/@router` graph is explicitly bypassed in favor of calling methods by hand (acknowledged in the `ponytail:` comment at `analysis_flow.py:659`). This is fine as a documented simplification, but it means the "multi-agent" framing (4 named agents/personas) is cosmetic: there are really just 2 LLM call sites (`context_librarian` JIT notes, `product_analyst`/`instrumentation_engineer` synthesis) wrapped in agent-shaped ceremony. Worth deciding deliberately: either lean into CrewAI's actual orchestration (delegation, tool-calling loop) or drop the `Agent`/`Flow` types and keep the deterministic function chain, removing a dependency and ~125 lines of indirection.

## P1 — UI

9. **No indication of stale/fallback data in `InsightCard.tsx`.** Ties to #2 — the component has no branch for "this is placeholder data," so a demo-fallback response is visually identical to a verified ClickHouse result. Same confidence-score styling either way.
10. **No request cancellation.** `page.tsx:97` `handleSend` has no `AbortController`; firing a second query while one is in flight leaves the first `fetch` racing the second against the same `assistantMsgId`-keyed state update — a slow first response can overwrite a faster second one. Fix: abort in-flight request (or disable input, which is already partially done via `isLoading`, but that only blocks new sends, not stale-response overwrite for the *same* session if `isLoading` toggles between).
11. **Copy-to-clipboard has no fallback/error handling** (`page.tsx:91-95`, `InsightCard.tsx:83-87`) — `navigator.clipboard.writeText` can reject (insecure context, permissions) and there's no `.catch`, so the button silently does nothing.
12. **No frontend tests at all.** `frontend/` has zero test files despite a component-heavy UI (`InsightCard`, `MarkdownBubble`) that already broke once in production (remark-gfm regression, per git history `416483c`). Even a couple of React Testing Library smoke tests on `InsightCard` would have caught that class of regression before deploy.
13. Minor: default selected model is `atlys-instrumentation` (`page.tsx:70`) while the product's headline use case (per the welcome message and suggestions) is arguably analytics — worth confirming intended default with product, not a code bug.

## P2 — Testing gaps

14. Per existing test suite: unit tests mock the LLM/Langfuse client boundary but never assert on the *shape* of arguments passed into prompt builders — this is exactly the class of bug in #1. Add one contract test per `prompts.build_*` function: call it with the kwargs the call site actually uses, assert it returns a non-empty string. Cheapest possible regression guard for this whole bug class.
15. No test currently drives `/api/ingest/approve` or `/api/analyze/query` end-to-end against a stubbed ClickHouse to catch the fallback-data behavior (#2/#3).

## Suggested order of work

1. Fix #1 (prompt signature) — one function, immediate correctness win, unblocks real LLM answers.
2. Fix #4 (auth on write endpoint) — production risk, small diff (one dependency check).
3. Fix #2/#3 (fallback-data labeling + column-aware cuts) — trust/correctness for every "no live data" case.
4. Add logging to the swallowed excepts touched while fixing 1-3 (don't boil the ocean — do it opportunistically per file).
5. Decide + act on #8 (keep CrewAI orchestration for real, or delete the ceremony) — architectural call, do after the above land since it touches every flow file.
6. UI: #9 (stale-data badge, depends on #2's data shape), #10/#11 (small, independent, do anytime).
7. Tests: one prompt-contract test per P0 fix as it lands; frontend smoke test for `InsightCard` once #9 changes its render branches.

Everything else (duplicated URL default, minor test coverage) is cleanup — bundle into whichever PR is already touching that file rather than a dedicated pass.
