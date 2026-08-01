import json

from atlys_agentic import assemble_submission, paths


def test_assemble_writes_all_three_required_files(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "SUBMISSION_DIR", tmp_path)
    written = assemble_submission.assemble(
        spec_id="06_unseen",
        ddl="CREATE TABLE unseen (...)",
        insight_md="# Insight\nPM-audience summary here.",
        trace_json={"trace_id": "t1", "spans": []},
    )
    out_dir = tmp_path / "06_unseen"
    assert (out_dir / "schema.sql").read_text() == "CREATE TABLE unseen (...)"
    assert "PM-audience" in (out_dir / "insight.md").read_text()
    assert json.loads((out_dir / "trace.json").read_text())["trace_id"] == "t1"
    assert written == {
        "schema": out_dir / "schema.sql",
        "insight": out_dir / "insight.md",
        "trace": out_dir / "trace.json",
    }
