import os

import pytest

from atlys_agentic import assemble_submission, chdb_client, paths
from atlys_agentic.flows import analysis_flow, ingestion_flow

pytestmark = pytest.mark.skipif(
    not os.getenv("CLICKHOUSE_HOST") or not os.getenv("GEMINI_API_KEY"),
    reason="E2E rehearsal requires live ClickHouse Cloud + Gemini credentials",
)


def test_full_cuj4_dry_run_on_express_checkout_produces_valid_submission():
    chdb_client.init_schema()
    chdb_client.init_base_context()

    ingestion_result = ingestion_flow.run(
        spec_id="01_express_checkout",
        table_name="express_checkout_rehearsal",
        input_fn=lambda _prompt: "APPROVE",
    )
    assert ingestion_result["approved"] is True
    assert ingestion_result["ddl_result"]["status"] == "ok"

    analysis_result = analysis_flow.run(
        question="Does Express Checkout lift conversion, and is there an iOS OTP issue?",
        spec_id="01_express_checkout",
        base_sql="SELECT count() AS c FROM express_checkout_rehearsal",
    )
    assert analysis_result["answer_md"]
    assert 0.0 <= analysis_result["confidence"]["score"] <= 1.0

    written = assemble_submission.assemble(
        spec_id="01_express_checkout_rehearsal",
        ddl=ingestion_result["ddl"],
        insight_md=analysis_result["answer_md"],
        trace_json={
            "ingestion_trace_id": ingestion_result["trace_id"],
            "analysis_trace_id": analysis_result["trace_id"],
        },
    )
    assert written["schema"].exists()
    assert written["insight"].exists()
    assert written["trace"].exists()
