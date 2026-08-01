from unittest.mock import patch

from atlys_agentic.flows.ingestion_flow import run


def test_approved_path_executes_ddl_and_runs_context_audit():
    with patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Infer_Schema", return_value="CREATE TABLE t (...)"), \
         patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Generate_MV", return_value=""), \
         patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Execute_DDL", return_value={"status": "ok", "table": "t", "version": 1, "error": None}) as mock_exec, \
         patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Context_Diff", return_value={"additions": ["t.x"], "conflicts": [], "gaps": []}), \
         patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Context_Upsert", return_value=1), \
         patch("atlys_agentic.flows.ingestion_flow.tracing.trace"), \
         patch("atlys_agentic.flows.ingestion_flow.tracing.step"):
        result = run(
            spec_id="01_express_checkout",
            table_name="express_checkout",
            input_fn=lambda _prompt: "APPROVE",
        )
    mock_exec.assert_called_once()
    assert result["approved"] is True
    assert result["ddl_result"]["status"] == "ok"


def test_rejected_path_never_touches_clickhouse():
    with patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Infer_Schema", return_value="CREATE TABLE t (...)"), \
         patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Generate_MV", return_value=""), \
         patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Execute_DDL") as mock_exec, \
         patch("atlys_agentic.flows.ingestion_flow.tracing.trace"), \
         patch("atlys_agentic.flows.ingestion_flow.tracing.step"):
        result = run(
            spec_id="01_express_checkout",
            table_name="express_checkout",
            input_fn=lambda _prompt: "nope",
        )
    mock_exec.assert_not_called()
    assert result["approved"] is False


def test_only_literal_approve_string_passes_the_gate():
    with patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Infer_Schema", return_value="CREATE TABLE t (...)"), \
         patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Generate_MV", return_value=""), \
         patch("atlys_agentic.flows.ingestion_flow.tools.Tool_Execute_DDL") as mock_exec, \
         patch("atlys_agentic.flows.ingestion_flow.tracing.trace"), \
         patch("atlys_agentic.flows.ingestion_flow.tracing.step"):
        result = run(
            spec_id="01_express_checkout",
            table_name="express_checkout",
            input_fn=lambda _prompt: "approve",  # lowercase must NOT pass
        )
    mock_exec.assert_not_called()
    assert result["approved"] is False
