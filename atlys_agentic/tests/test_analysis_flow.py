from unittest.mock import patch

from atlys_agentic.flows.analysis_flow import run

_CUT_ROWS = {"rows": [{"device_type": "ios", "converted": 100, "total": 500}]}


def test_multi_cut_is_always_run_for_device_geo_destination():
    with patch("atlys_agentic.flows.analysis_flow.chdb_client.run", return_value=[]), \
         patch("atlys_agentic.flows.analysis_flow.tools.Tool_Analytics_Compute", return_value=_CUT_ROWS) as mock_compute, \
         patch("atlys_agentic.flows.analysis_flow.tools.Tool_Score_Confidence", return_value={"score": 0.8, "rationale": "r"}), \
         patch("atlys_agentic.flows.analysis_flow.tools.Tool_Context_Upsert", return_value=1), \
         patch("atlys_agentic.flows.analysis_flow.tracing.new_trace", return_value="trace-9"), \
         patch("atlys_agentic.flows.analysis_flow.tracing.span"):
        result = run(
            question="Does Express Checkout lift conversion on iOS?",
            spec_id="01_express_checkout",
            base_sql="SELECT * FROM express_checkout",
        )
    called_cut_dims = {
        c.kwargs.get("select_sql", c.args[0] if c.args else "") for c in mock_compute.call_args_list
    }
    joined = " ".join(called_cut_dims)
    assert "device_type" in joined
    assert "geoip_country_code" in joined
    assert "destination" in joined
    assert result["confidence"]["score"] == 0.8
    assert result["trace_id"] == "trace-9"


def test_known_issue_branch_cites_k1_for_ios_otp_question():
    with patch("atlys_agentic.flows.analysis_flow.chdb_client.run", return_value=[
        {"key": "K1", "definition": "iOS WebKit OTP autofill regression"}
    ]), \
         patch("atlys_agentic.flows.analysis_flow.tools.Tool_Analytics_Compute", return_value=_CUT_ROWS), \
         patch("atlys_agentic.flows.analysis_flow.tools.Tool_Score_Confidence", return_value={"score": 0.9, "rationale": "r"}), \
         patch("atlys_agentic.flows.analysis_flow.tools.Tool_Context_Upsert", return_value=1), \
         patch("atlys_agentic.flows.analysis_flow.tracing.new_trace", return_value="trace-10"), \
         patch("atlys_agentic.flows.analysis_flow.tracing.span"):
        result = run(
            question="Is there an iOS OTP drop on Express Checkout?",
            spec_id="01_express_checkout",
            base_sql="SELECT * FROM express_checkout",
        )
    assert result["known_issue_match"] is True
    assert "K1" in result["answer_md"]


def test_no_known_issue_branch_when_unrelated():
    with patch("atlys_agentic.flows.analysis_flow.chdb_client.run", return_value=[
        {"key": "K1", "definition": "iOS WebKit OTP autofill regression"}
    ]), \
         patch("atlys_agentic.flows.analysis_flow.tools.Tool_Analytics_Compute", return_value=_CUT_ROWS), \
         patch("atlys_agentic.flows.analysis_flow.tools.Tool_Score_Confidence", return_value={"score": 0.6, "rationale": "r"}), \
         patch("atlys_agentic.flows.analysis_flow.tools.Tool_Context_Upsert", return_value=1), \
         patch("atlys_agentic.flows.analysis_flow.tracing.new_trace", return_value="trace-11"), \
         patch("atlys_agentic.flows.analysis_flow.tracing.span"):
        result = run(
            question="What is total revenue in UAE?",
            spec_id="general",
            base_sql="SELECT * FROM purchase_completed",
        )
    assert result["known_issue_match"] is False
