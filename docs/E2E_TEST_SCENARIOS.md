# CUJ 1 → CUJ 2 E2E Test Scenario Matrix

Suite: `tests/e2e/`. Run with `.venv/bin/python -m pytest tests/e2e/ -v`.

Every scenario generates deterministic synthetic events, ingests them through
the real CUJ 1 tool pipeline (`Tool_Infer_Schema` → `Tool_Validate_Invariants`
→ `Tool_Execute_DDL` → `Tool_Load_Events` → `Tool_Write_Table_Semantics`),
then queries the persisted table through the real CUJ 2 execution primitive
(`Tool_Analytics_Compute`) — backed by a local embedded `chdb` session instead
of live ClickHouse Cloud (see `docs/superpowers/specs/2026-08-06-cuj1-cuj2-e2e-tests-design.md`
for why).

| # | Scenario | Test | Generates | Proves |
| :-- | :--- | :--- | :--- | :--- |
| 1 | Harness smoke test | `test_harness_persists_and_queries_via_chdb` | 2 minimal events | Minimal round trip proving the harness itself works: events ingested via the real CUJ1 tool pipeline are queryable back out via the real CUJ2 tool pipeline |
| 2 | Happy path | `test_happy_path_ingest_and_query` | 50 funnels (shown → selected → otp_entered → confirmed, ~20% OTP failure) with unique `user_id`/`application_id` | Exact `COUNT`/`SUM` against precomputed ground truth; point lookup by `application_id`; schema integrity via `system.columns`; the `table_semantics` CUJ1→CUJ2 handoff; query latency under budget |
| 3 | Schema/type boundaries | `test_boundary_cases_survive_round_trip` | Missing optional field, unicode + SQL-lookalike string, max-length string, unrounded float, timestamps on a `toYYYYMM()` partition boundary | Nulls stay `NULL`, unicode/long strings round-trip exactly, float precision survives, partition-boundary rows land in the correct month |
| 4 | Out-of-order / late-arriving | `test_out_of_order_events_query_correctly` | 5 events inserted in scrambled order relative to their timestamps | A time-ordered query returns correct chronological order regardless of insertion order |
| 5 | Duplicate / idempotency | `test_duplicate_events_are_not_silently_deduped` | 3 distinct events, 2 loaded twice with identical `id` | `MergeTree` does not dedupe on insert — `count()` shows duplication, `uniqExact(id)` shows the true distinct count |

`pytest tests/e2e -v` reports "5 passed" — the table above lists all 5.

## Known gaps this suite intentionally does not cover

- **Real ClickHouse Cloud.** By design decision, this suite never opens a
  network connection — it validates the tool-layer pipeline logic against a
  real embedded ClickHouse engine (`chdb`), not production latency/infra
  characteristics of the actual Cloud service.
- **`analysis_flow.run()`'s CUJ2 orchestration.** That entry point currently
  re-reads `events.ndjson` directly on several fallback paths rather than
  querying the ingested table (see design doc §1). This suite exercises
  `Tool_Analytics_Compute` directly instead, since that is the primitive that
  actually proves data landed correctly in storage.
- **LLM-driven schema reasoning and semantic retrieval ranking.** The suite's
  autouse `chdb_only_ch_client` fixture patches `os.environ.get` so
  `PYTEST_CURRENT_TEST` reads as unset for the whole test body — not just around
  the storage calls — which is what lets `Tool_Load_Events`/`Tool_Analytics_Compute`
  take their real code paths. What actually prevents a real Gemini/OpenAI
  embedding call is the separate autouse `stub_embed_text` fixture, which
  unconditionally stubs `tools_cuj1.embed_text` to return `[]` regardless of that
  env var's state. No real Gemini calls happen anywhere in this suite.
