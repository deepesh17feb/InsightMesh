"""Shared fixtures for the CUJ1->CUJ2 E2E suite.

Routes ch_client at a local chdb session (no live ClickHouse Cloud, no
network), mutes real Langfuse tracing (same pattern as tests/test_tracing.py),
and provisions/cleans up synthetic spec directories + their chDB rows.
See docs/superpowers/specs/2026-08-06-cuj1-cuj2-e2e-tests-design.md.
"""
from __future__ import annotations

import json
import shutil
from unittest.mock import MagicMock

import pytest

from atlys_agentic import ch_client, chdb_client, paths, tools_common, tracing
from atlys_agentic import tools_cuj1


@pytest.fixture
def chdb_only_ch_client(monkeypatch):
    """Route ch_client.command/select/insert_ndjson at the local chdb session
    so CUJ1 writes and CUJ2 reads share one real embedded ClickHouse engine
    instead of touching live Cloud."""
    monkeypatch.setattr(ch_client, "command", lambda ddl: chdb_client.run(ddl, fmt="CSV"))
    monkeypatch.setattr(ch_client, "select", lambda sql: chdb_client.run(sql))
    monkeypatch.setattr(ch_client, "insert_ndjson", lambda table, content: None, raising=False)
    chdb_client.init_schema()
    return ch_client


@pytest.fixture
def no_pytest_guard(monkeypatch):
    """Tool_Load_Events / Tool_Analytics_Compute both no-op under
    PYTEST_CURRENT_TEST as a belt against tests hitting live ClickHouse Cloud.
    This suite calls only tool-layer functions -- never the LLM-gated flow
    orchestration -- so lifting the guard for the test body triggers no
    network or LLM calls, only the real storage code paths."""
    # ponytail: can't delenv or setenv — pytest re-sets PYTEST_CURRENT_TEST during
    # test execution. Patch os.environ.get to hide it from tools.
    import os
    original_get = os.environ.get
    monkeypatch.setattr(os.environ, "get", lambda key, default=None: None if key == "PYTEST_CURRENT_TEST" else original_get(key, default))


@pytest.fixture(autouse=True)
def mock_tracing(monkeypatch):
    """Prevent real Langfuse network calls. Mirrors the mock shape used in
    tests/test_tracing.py's test_step_nests_under_active_trace_without_flushing."""
    mock_client = MagicMock()
    mock_client.start_as_current_observation.return_value.__enter__.return_value = MagicMock()
    mock_client.get_current_trace_id.return_value = "e2e-test-trace"
    mock_client.get_trace_url.return_value = None
    monkeypatch.setattr(tracing, "client", lambda: mock_client)


@pytest.fixture(autouse=True)
def stub_embed_text(monkeypatch):
    """Prevent real LLM API calls to Gemini/OpenAI/etc for text embeddings.
    embed_text() is called by Tool_Write_Table_Semantics during ingest().
    Stub it to return empty embedding (matches its own documented fallback
    behavior) so test suite incurs zero LLM network calls, independent of
    PYTEST_CURRENT_TEST env var. Patch in tools_cuj1 where it's imported,
    not just in tools_common where it's defined."""
    monkeypatch.setattr(tools_cuj1, "embed_text", lambda text: [])


@pytest.fixture
def synthetic_spec():
    """Factory fixture: _make(name, spec_md_text, events) writes spec.md +
    events.ndjson under src/atlys_agentic/specs/e2e_synth_<name>/ (never the
    graded problem statement directory) and returns (spec_id, table_name).
    Teardown removes the directory and any chDB tables/catalog rows it caused."""
    created_dirs: list = []
    created_tables: list[str] = []

    def _make(name: str, spec_md_text: str, events: list[dict]) -> tuple[str, str]:
        spec_id = f"e2e_synth_{name}"
        table_name = f"e2e_{name}"
        spec_dir = paths.ATLYS_AGENTIC_DIR / "specs" / spec_id
        spec_dir.mkdir(parents=True, exist_ok=True)
        (spec_dir / "spec.md").write_text(spec_md_text, encoding="utf-8")
        with (spec_dir / "events.ndjson").open("w", encoding="utf-8") as f:
            for ev in events:
                f.write(json.dumps(ev) + "\n")
        created_dirs.append(spec_dir)
        created_tables.append(table_name)
        return spec_id, table_name

    yield _make

    for spec_dir in created_dirs:
        shutil.rmtree(spec_dir, ignore_errors=True)
    for table_name in created_tables:
        for cleanup_sql in (
            f"DROP TABLE IF EXISTS {table_name}",
            f"ALTER TABLE schema_registry DELETE WHERE \"table\" = '{table_name}'",
            f"ALTER TABLE table_semantics DELETE WHERE table_name = '{table_name}'",
        ):
            try:
                chdb_client.run(cleanup_sql, fmt="CSV")
            except Exception:
                pass
