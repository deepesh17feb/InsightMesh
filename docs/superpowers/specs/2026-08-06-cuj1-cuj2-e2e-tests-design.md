# CUJ 1 → CUJ 2 end-to-end integration tests — design

**Status:** approved. **Branch:** `enable-e2e`.

## 1. Problem

CUJ 1 (ingestion: `tools_cuj1.py`, `flows/ingestion_flow.py`) and CUJ 2 (analytics:
`tools_cuj2.py`, `flows/analysis_flow.py`) each have unit tests, but nothing chains them:
generate data → ingest via CUJ 1 → query the *persisted* result via CUJ 2 → assert parity.
`tests/test_cuj2_analytics_flow.py` even has empty "LEVEL 3: END-TO-END WORKFLOW" /
"LEVEL 4: UNSEEN SPEC GENERALIZATION" section headers with no tests under them — this gap
is already flagged in the repo, just unfilled.

Two production code paths make a naive E2E attempt silently pass without checking anything:

1. `Tool_Load_Events` and `Tool_Analytics_Compute` (`tools_cuj1.py`, `tools_cuj2.py`) both
   check `os.environ.get("PYTEST_CURRENT_TEST")` and short-circuit — a deliberate belt
   stopping tests from writing to live ClickHouse Cloud. Any test run under plain `pytest`
   silently no-ops instead of touching storage.
2. `analysis_flow.run()`'s cut queries re-read `events.ndjson` directly via `chdb.query(...
   FROM file(...))` on failure/pytest paths rather than querying the table CUJ 1 built. A
   flow-level E2E test would coincidentally "pass" on the shipped specs (their ndjson matches
   what got loaded) but would never actually validate genuinely new synthetic data injected
   only through the ingestion path.

## 2. Decision: local embedded ClickHouse via chdb, tool-layer calls

Verified locally: `chdb.session.Session` (already a project dependency, `chdb==4.2.1`)
executes real `MergeTree` DDL — `PARTITION BY`, `TTL`, `LowCardinality`, `Nullable`,
`GROUP BY`, `uniqExact`, `DESCRIBE TABLE` all behave like real ClickHouse, no network.

The E2E suite monkeypatches three `ch_client` functions so every "ClickHouse Cloud" call
in the real tool code lands on the local `chdb.session` instead:

| Patched | New behavior | Why safe |
| :--- | :--- | :--- |
| `ch_client.command` | no-op | `Tool_Execute_DDL` calls `chdb_client.run(ddl)` unconditionally right after — that does the real `CREATE TABLE` |
| `ch_client.select` | delegates to `chdb_client.run(sql)` | used for `Tool_Load_Events`'s row-count verification and `Tool_Analytics_Compute`'s primary query path |
| `ch_client.insert_ndjson` | no-op (function doesn't exist on `ch_client` today — calling it live would `AttributeError`) | `Tool_Load_Events`'s own `chdb_client.run(INSERT ... FORMAT JSONEachRow)` step is what actually loads rows |

Net effect: `chdb_client`'s embedded session becomes the single backing store for both
metadata (`schema_registry`, `business_context`, `table_semantics`) and "analytical" event
data for the duration of the test. No double-insert (only one of the two historical
Cloud/chDB write paths is live), no network, fully deterministic.

**`PYTEST_CURRENT_TEST` is unset narrowly.** The fixture does
`monkeypatch.delenv("PYTEST_CURRENT_TEST")` scoped only around the `Tool_Load_Events` and
`Tool_Analytics_Compute` calls — not around a full flow — so LLM-gated branches elsewhere
(schema-reasoning prose, embeddings) stay off. Zero real API calls, zero flakiness.

**Tool-layer, not flow-layer.** The suite calls
`Tool_Infer_Schema → Tool_Validate_Invariants → Tool_Execute_DDL → Tool_Load_Events →
Tool_Write_Table_Semantics` directly for CUJ 1, and hand-built aggregate `SELECT`s through
`Tool_Analytics_Compute` for CUJ 2 — not `ingestion_flow.run()` / `analysis_flow.run()`.
Those flows entangle LLM reasoning and LibreChat chat-state parsing, already covered by
`tests/test_ingestion_flow.py` and `tests/test_cuj1_ingestion.py`. `analysis_flow.run()`'s
ndjson-file bypass (§1.2 above) makes it unsuitable for validating genuinely new synthetic
rows — calling `Tool_Analytics_Compute` directly is what actually proves the persisted table
holds correct data.

## 3. Synthetic data

Deterministic (seeded), modeled on `01_express_checkout`'s event shape
(`express_checkout_shown` → `selected` → `otp_entered` → `express_payment_confirmed`, nested
`payment.amount/currency/latency_ms`). Each generator returns `(events, expected)` where
`expected` is precomputed ground truth (sums, counts, per-user records) asserted against
query output — never re-derived from the same code path being tested.

Written to `src/atlys_agentic/specs/e2e_synth_<scenario>/{spec.md,events.ndjson}` — one of
`paths.py`'s three recognized spec roots, distinct from the graded `problem statment/specs/`
directory. Created in a fixture, `shutil.rmtree`'d in teardown.

### Scenario matrix

| # | Scenario | What it generates | What CUJ 2 must prove |
| :-- | :--- | :--- | :--- |
| 1 | Happy path | 200 events, unique `user_id`/`application_id` per funnel, known `SUM(payment_amount)`, known `otp_success` count | Exact row count, `SUM`/`AVG`/`COUNT` match precomputed values; point lookup by `application_id` returns the exact expected row |
| 2 | Schema/type boundaries | `NULL` optional fields, unicode + quote/SQL-lookalike strings, max-length string, float precision edge values (`0.1+0.2` style), timestamps at exact `toYYYYMM` partition boundaries | Column types survive (`DESCRIBE TABLE`), no row silently dropped or corrupted, partition-boundary rows land in the correct month bucket |
| 3 | Late-arriving / out-of-order | Events generated with non-monotonic timestamps (older event inserted after newer ones) | A time-ordered query (`ORDER BY timestamp`) returns correct chronological order regardless of insertion order |
| 4 | Duplicate / idempotency | Exact-duplicate event rows (same `id`) inserted twice | `MergeTree` does **not** dedupe on insert — `count()` shows duplicates, `uniqExact(id)` shows the true distinct count. Test documents and asserts this real behavior rather than assuming silent dedup |

## 4. Assertions

- **Correctness:** `SUM`/`AVG`/`COUNT`/`uniqExact` from CUJ 2 queries vs precomputed expected values from the generator.
- **Schema integrity:** `DESCRIBE TABLE` column names/types match what `Tool_Infer_Schema` declared; `Tool_Validate_Invariants` returns zero violations.
- **Latency:** wall-clock (`time.perf_counter`) around each CUJ 2 query, asserted under a generous smoke threshold (not a strict SLA — local chdb, not production Cloud).
- **Correlation IDs:** every generated event carries a deterministic `user_id`/`application_id`; point queries assert the exact expected row comes back.

## 5. Deliverables

- `tests/e2e/synthetic_data.py` — scenario generators
- `tests/e2e/conftest.py` — `ch_client` patch fixture, synthetic-spec-dir fixture
- `tests/e2e/test_cuj1_to_cuj2_e2e.py` — the 4 scenarios end to end
- `docs/E2E_TEST_SCENARIOS.md` — scenario matrix (human-readable copy of §3)

## 6. Out of scope

- Real ClickHouse Cloud / network — explicitly rejected in favor of local chdb (user decision).
- LLM-driven schema reasoning / semantic retrieval ranking quality — `embed_text` returns `[]`
  under `PYTEST_CURRENT_TEST` (left set for that call), matching the documented "unranked
  candidate" fallback rather than exercising real embeddings.
- Fixing the `analysis_flow.run()` ndjson-file bypass or the missing `ch_client.insert_ndjson`
  — both noted as findings, not fixed here; out of this task's scope.
