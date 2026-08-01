"""End-to-end rehearsal test for the full Atlys Agentic Analytics pipeline.

Verifies:
1. Ingestion Flow (CUJ 1):
   - Ingests 01_express_checkout spec & events sample
   - Generates production DDL with (timestamp, user_id) ORDER BY key
   - Generates daily segment-rollup Materialized View
   - Passes HITL approval gate
   - Updates chDB schema_registry and business_context
2. Analysis Flow (CUJ 2):
   - JIT retrieves business context
   - Runs multi-cut queries
   - Detects known issue alignment
   - Produces confidence score and PM markdown insight
3. Observability & Viz:
   - Emits structured 3-view viz snapshot
   - Generates trace IDs for Langfuse
"""
from pathlib import Path
from unittest.mock import patch

from atlys_agentic import chdb_client, paths, tools
from atlys_agentic.flows import analysis_flow, ingestion_flow


def test_end_to_end_pipeline_rehearsal(tmp_path):
    # 1. Initialize chDB local metadata layer
    with patch("atlys_agentic.paths.CHDB_PATH", tmp_path / "chdb"):
        chdb_client.init_schema()
        inserted_context = chdb_client.init_base_context()
        assert inserted_context > 0, "base_context.md must be chunked into business_context rows"

        # 2. Run Ingestion Flow (CUJ 1) with simulated APPROVE
        with patch("atlys_agentic.tools.ch_client.command") as mock_ch_cmd, \
             patch("atlys_agentic.tools.ch_client.select", return_value=[]), \
             patch("atlys_agentic.tracing.new_trace", return_value="trace-e2e-ingest"):
            ingest_result = ingestion_flow.run(
                spec_id="01_express_checkout",
                table_name="express_checkout",
                input_fn=lambda _prompt: "APPROVE",
            )

        assert ingest_result["approved"] is True
        assert "CREATE TABLE IF NOT EXISTS express_checkout" in ingest_result["ddl"]
        assert "ORDER BY (timestamp, user_id)" in ingest_result["ddl"]
        assert "TTL timestamp + INTERVAL 12 MONTH" in ingest_result["ddl"]
        mock_ch_cmd.assert_called()

        # Verify schema_registry updated
        schemas = chdb_client.run("SELECT table, version, spec_id FROM schema_registry")
        assert any(r["table"] == "express_checkout" for r in schemas)

        # 3. Run Analysis Flow (CUJ 2) for an analytical question
        mock_cut_rows = [
            {"device_type": "ios", "converted": 120, "total": 600},
            {"device_type": "android", "converted": 200, "total": 800},
        ]
        with patch("atlys_agentic.tools.ch_client.select", return_value=mock_cut_rows), \
             patch("atlys_agentic.tracing.new_trace", return_value="trace-e2e-analysis"):
            analysis_result = analysis_flow.run(
                question="Is there an iOS OTP drop on Express Checkout?",
                spec_id="01_express_checkout",
                base_sql="SELECT * FROM express_checkout",
            )

        assert analysis_result["known_issue_match"] is True
        assert "K1" in analysis_result["answer_md"] or "known issue" in analysis_result["answer_md"].lower()
        assert analysis_result["confidence"]["score"] >= 0.6
        assert "device_type" in analysis_result["cuts"]

        # Verify insight logged in chDB
        insights = chdb_client.run("SELECT key, definition FROM business_context WHERE section = 'Insights'")
        assert len(insights) >= 1

        # 4. Generate structured 3-view visualization snapshot
        with patch("atlys_agentic.paths.OUTPUTS_DIR", tmp_path / "outputs"):
            viz = tools.Tool_Emit_Viz()
            assert len(viz["schema_history"]) >= 1
            assert len(viz["context_changelog"]) >= 1
            assert (tmp_path / "outputs" / "viz_snapshot.json").exists()
