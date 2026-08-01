from unittest.mock import MagicMock, patch

from atlys_agentic.flows.ingestion_flow import IngestionFlow, run


def test_approved_path_executes_ddl_and_runs_context_audit():
    with patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Infer_Schema", return_value="CREATE TABLE express_checkout (...)"), \
         patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Generate_MV", return_value=""), \
         patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Execute_DDL", return_value={"status": "ok", "table": "express_checkout", "version": None, "error": None}) as mock_exec, \
         patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Register_Schema_Version", return_value={"status": "ok", "table": "express_checkout", "version": 1, "error": None}) as mock_register, \
         patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Context_Diff", return_value={"additions": ["express_checkout.shown_amount"], "conflicts": [], "gaps": []}) as mock_diff, \
         patch("atlys_agentic.flows.ingestion_flow.tools._latest_context_definition", return_value=""), \
         patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Context_Upsert", return_value=1) as mock_upsert, \
         patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Append_Context_Changelog") as mock_changelog, \
         patch("atlys_agentic.flows.ingestion_flow.tracing.new_trace", return_value="trace-1"), \
         patch("atlys_agentic.flows.ingestion_flow.tracing.span"):
        result = run(
            spec_id="01_express_checkout",
            table_name="express_checkout",
            input_fn=lambda _prompt: "APPROVE",
        )
    mock_exec.assert_called_once()
    mock_register.assert_called_once()
    mock_diff.assert_called_once()
    mock_upsert.assert_called_once()
    mock_changelog.assert_called_once()
    assert result["approved"] is True
    assert result["ddl_result"]["status"] == "ok"
    assert result["ddl_result"]["version"] == 1
    assert result["trace_id"] == "trace-1"


def test_rejected_path_never_touches_clickhouse():
    with patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Infer_Schema", return_value="CREATE TABLE express_checkout (...)"), \
         patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Generate_MV", return_value=""), \
         patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Execute_DDL") as mock_exec, \
         patch("atlys_agentic.flows.ingestion_flow.tracing.new_trace", return_value="trace-2"), \
         patch("atlys_agentic.flows.ingestion_flow.tracing.span"):
        result = run(
            spec_id="01_express_checkout",
            table_name="express_checkout",
            input_fn=lambda _prompt: "nope",
        )
    mock_exec.assert_not_called()
    assert result["approved"] is False


def test_only_literal_approve_string_passes_the_gate():
    with patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Infer_Schema", return_value="CREATE TABLE express_checkout (...)"), \
         patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Generate_MV", return_value=""), \
         patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Execute_DDL") as mock_exec, \
         patch("atlys_agentic.flows.ingestion_flow.tracing.new_trace", return_value="trace-3"), \
         patch("atlys_agentic.flows.ingestion_flow.tracing.span"):
        result = run(
            spec_id="01_express_checkout",
            table_name="express_checkout",
            input_fn=lambda _prompt: "approve",  # lowercase must NOT pass
        )
    mock_exec.assert_not_called()
    assert result["approved"] is False


def test_approved_path_executes_materialized_view_when_generated():
    mv_ddl = "CREATE MATERIALIZED VIEW IF NOT EXISTS express_checkout_daily_mv (...)"
    with patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Infer_Schema", return_value="CREATE TABLE express_checkout (...)"), \
         patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Generate_MV", return_value=mv_ddl), \
         patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Execute_DDL", return_value={"status": "ok", "table": "express_checkout", "version": None, "error": None}) as mock_exec, \
         patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Register_Schema_Version", return_value={"status": "ok", "table": "express_checkout", "version": 1, "error": None}), \
         patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Context_Diff", return_value={"additions": [], "conflicts": [], "gaps": []}), \
         patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Context_Upsert"), \
         patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Append_Context_Changelog"), \
         patch("atlys_agentic.flows.ingestion_flow.tracing.new_trace", return_value="trace-4"), \
         patch("atlys_agentic.flows.ingestion_flow.tracing.span"):
        result = run(
            spec_id="01_express_checkout",
            table_name="express_checkout",
            input_fn=lambda _prompt: "APPROVE",
        )
    assert mock_exec.call_count == 2
    assert result["approved"] is True


def test_execute_and_audit_skips_registry_write_on_ddl_failure():
    """A rolled-back DDL must never produce a schema_registry version row —
    the two writes are now separate calls, so this has to be enforced by the
    flow, not implicitly by one function doing both."""
    with patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Infer_Schema", return_value="CREATE TABLE express_checkout (...)"), \
         patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Generate_MV", return_value=""), \
         patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Execute_DDL", return_value={"status": "rolled_back", "table": "express_checkout", "version": None, "error": "boom"}), \
         patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Register_Schema_Version") as mock_register, \
         patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Context_Diff", return_value={"additions": [], "conflicts": [], "gaps": []}), \
         patch("atlys_agentic.flows.ingestion_flow.tracing.new_trace", return_value="trace-5"), \
         patch("atlys_agentic.flows.ingestion_flow.tracing.span"):
        result = run(
            spec_id="01_express_checkout",
            table_name="express_checkout",
            input_fn=lambda _prompt: "APPROVE",
        )
    mock_register.assert_not_called()
    assert result["ddl_result"]["status"] == "rolled_back"
