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
| 1 | Happy path | `test_happy_path_ingest_and_query` | 50 funnels (shown → selected → otp_entered → confirmed, ~20% OTP failure) with unique `user_id`/`application_id` | Exact `COUNT`/`SUM` against precomputed ground truth; point lookup by `application_id`; `DESCRIBE TABLE` schema integrity; the `table_semantics` CUJ1→CUJ2 handoff; query latency under budget |
| 2 | Schema/type boundaries | `test_boundary_cases_survive_round_trip` | Missing optional field, unicode + SQL-lookalike string, max-length string, unrounded float, timestamps on a `toYYYYMM()` partition boundary | Nulls stay `NULL`, unicode/long strings round-trip exactly, float precision survives, partition-boundary rows land in the correct month |
| 3 | Out-of-order / late-arriving | `test_out_of_order_events_query_correctly` | 5 events inserted in scrambled order relative to their timestamps | A time-ordered query returns correct chronological order regardless of insertion order |
| 4 | Duplicate / idempotency | `test_duplicate_events_are_not_silently_deduped` | 3 distinct events, 2 loaded twice with identical `id` | `MergeTree` does not dedupe on insert — `count()` shows duplication, `uniqExact(id)` shows the true distinct count |

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
- **LLM-driven schema reasoning and semantic retrieval ranking.** Both are
  gated behind `PYTEST_CURRENT_TEST`, which this suite leaves set except
  around the two storage calls that need it lifted — no real Gemini calls
  happen anywhere in this suite.
