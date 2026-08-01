from unittest.mock import patch

from atlys_agentic import run_ingestion


def test_main_parses_spec_id_and_returns_zero_on_approval():
    with patch("atlys_agentic.run_ingestion.chdb_client.init_schema") as mock_init_schema, \
         patch("atlys_agentic.run_ingestion.chdb_client.init_base_context") as mock_init_ctx, \
         patch("atlys_agentic.run_ingestion.ingestion_flow.run", return_value={"approved": True}) as mock_run:
        exit_code = run_ingestion.main(["--spec_dir", "specs/01_express_checkout", "--table", "express_checkout"])

    mock_init_schema.assert_called_once()
    mock_init_ctx.assert_called_once()
    mock_run.assert_called_once_with(spec_id="01_express_checkout", table_name="express_checkout")
    assert exit_code == 0


def test_main_returns_nonzero_when_rejected():
    with patch("atlys_agentic.run_ingestion.chdb_client.init_schema"), \
         patch("atlys_agentic.run_ingestion.chdb_client.init_base_context"), \
         patch("atlys_agentic.run_ingestion.ingestion_flow.run", return_value={"approved": False}):
        exit_code = run_ingestion.main(["--spec_dir", "specs/01_express_checkout", "--table", "express_checkout"])

    assert exit_code == 1


def test_main_handles_trailing_slashes_and_paths():
    with patch("atlys_agentic.run_ingestion.chdb_client.init_schema"), \
         patch("atlys_agentic.run_ingestion.chdb_client.init_base_context"), \
         patch("atlys_agentic.run_ingestion.ingestion_flow.run", return_value={"approved": True}) as mock_run:
        exit_code = run_ingestion.main(["--spec_dir", "problem statment/specs/01_express_checkout/", "--table", "express_checkout"])

    mock_run.assert_called_once_with(spec_id="01_express_checkout", table_name="express_checkout")
    assert exit_code == 0
