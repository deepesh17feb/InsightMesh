from unittest.mock import patch

from atlys_agentic import run_ingestion


def test_main_parses_spec_id_from_spec_dir_and_invokes_flow():
    with patch("atlys_agentic.run_ingestion.chdb_client.init_schema"), \
         patch("atlys_agentic.run_ingestion.chdb_client.init_base_context"), \
         patch("atlys_agentic.run_ingestion.ingestion_flow.run", return_value={"approved": True}) as mock_run:
        code = run_ingestion.main(["--spec_dir", "specs/01_express_checkout", "--table", "express_checkout"])
    assert code == 0
    mock_run.assert_called_once()
    _, kwargs = mock_run.call_args
    assert kwargs["spec_id"] == "01_express_checkout"
    assert kwargs["table_name"] == "express_checkout"


def test_main_returns_nonzero_when_rejected():
    with patch("atlys_agentic.run_ingestion.chdb_client.init_schema"), \
         patch("atlys_agentic.run_ingestion.chdb_client.init_base_context"), \
         patch("atlys_agentic.run_ingestion.ingestion_flow.run", return_value={"approved": False}):
        code = run_ingestion.main(["--spec_dir", "specs/01_express_checkout", "--table", "express_checkout"])
    assert code == 1
