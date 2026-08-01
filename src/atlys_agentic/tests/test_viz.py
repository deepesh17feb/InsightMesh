from atlys_agentic.viz import cli_report

_SNAPSHOT = {
    "schema_history": [{"table": "express_checkout", "version": 1, "spec_id": "01_express_checkout", "created_at": "2026-08-01"}],
    "insights": [{"spec_id": "01_express_checkout", "question": "lift?", "confidence": 0.82, "created_at": "2026-08-01"}],
    "context_changelog": [{"ts": "2026-08-01", "change_type": "context_upsert", "agent": "context_librarian", "trace_id": "t1"}],
}


def test_render_includes_all_three_view_headers():
    text = cli_report.render(_SNAPSHOT)
    assert "SCHEMA CHANGES OVER TIME" in text
    assert "INSIGHTS (WITH CONFIDENCE)" in text
    assert "CONTEXT CHANGELOG" in text


def test_render_includes_row_values():
    text = cli_report.render(_SNAPSHOT)
    assert "express_checkout" in text
    assert "0.82" in text
    assert "context_librarian" in text


def test_render_handles_empty_snapshot_without_crashing():
    text = cli_report.render({"schema_history": [], "insights": [], "context_changelog": []})
    assert "SCHEMA CHANGES OVER TIME" in text
