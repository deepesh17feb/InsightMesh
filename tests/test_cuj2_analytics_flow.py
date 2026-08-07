"""Comprehensive CUJ 2 multi-agent pipeline tests across all phases and complexity levels."""
from pathlib import Path

import pytest

from atlys_agentic import tools
from atlys_agentic.flows.analysis_flow import AnalysisFlow, AnalysisState
from atlys_agentic.tools_common import cosine_distance


# ==============================================================================
# LEVEL 1: INVARIANTS, VECTOR MATH & VALIDATION SAFETY
# ==============================================================================

def test_l1_cosine_distance_properties():
    """Verify vector distance properties: identical vectors=0.0, orthogonal=1.0, opposite=2.0."""
    v1 = [1.0, 0.0, 0.0]
    v2 = [1.0, 0.0, 0.0]
    v3 = [0.0, 1.0, 0.0]
    v4 = [-1.0, 0.0, 0.0]

    assert cosine_distance(v1, v2) == pytest.approx(0.0, abs=1e-5)
    assert cosine_distance(v1, v3) == pytest.approx(1.0, abs=1e-5)
    assert cosine_distance(v1, v4) == pytest.approx(2.0, abs=1e-5)
    # Empty vectors return 1.0 safely
    assert cosine_distance([], [1.0]) == 1.0


def test_l1_strict_select_only_validation():
    """Assert query validator permits SELECT/WITH queries and rejects any mutation or DDL."""
    valid_queries = [
        "SELECT count() FROM express_checkout",
        "WITH daily AS (SELECT toDate(timestamp) as d FROM express_checkout) SELECT d, count() FROM daily GROUP BY d",
        "  select * from express_checkout limit 10",
    ]
    for q in valid_queries:
        tools._assert_select_only(q)  # Must not raise

    invalid_queries = [
        "DROP TABLE express_checkout",
        "ALTER TABLE express_checkout DELETE WHERE user_id = 'u1'",
        "INSERT INTO express_checkout VALUES ('2026-04-01', 'u1')",
        "TRUNCATE TABLE express_checkout",
        "SELECT * FROM express_checkout; DROP TABLE users;",
    ]
    for q in invalid_queries:
        with pytest.raises(ValueError):
            tools._assert_select_only(q)


def test_l1_confidence_score_calibration_boundaries():
    """Verify confidence formula bounds, sample size log-scale, and component additivity."""
    # Large sample (5000+), large effect (>=10%), known issue match, consistent cuts
    high_score = tools.Tool_Score_Confidence(
        sample_size=5507,
        effect_size_pct=15.2,
        known_issue_match=True,
        cut_consistency=1.0,
    )
    assert high_score["score"] >= 0.85
    assert high_score["sample_size_component"] == 0.40
    assert high_score["effect_size_component"] == 0.25
    assert high_score["known_issue_component"] == 0.20
    assert high_score["cut_consistency_component"] == 0.15

    # Small sample (100 rows), small effect (1%), no known issue
    low_score = tools.Tool_Score_Confidence(
        sample_size=100,
        effect_size_pct=1.0,
        known_issue_match=False,
        cut_consistency=0.5,
    )
    assert low_score["score"] < 0.40
    assert low_score["known_issue_component"] == 0.0


# ==============================================================================
# LEVEL 2: COMPONENT INTEGRATION, RETRIEVAL GUARDS & ANSWERABILITY TRAPS
# ==============================================================================


# ==============================================================================
# LEVEL 3: END-TO-END WORKFLOW & PERSISTENCE
# ==============================================================================


def test_run_includes_trace_url_captured_during_the_trace():
    """analysis_flow.run()'s return dict must carry trace_url (not just
    trace_id) so callers like /api/analyze/query can surface a clickable
    Langfuse link without reconstructing the URL themselves."""
    from unittest.mock import MagicMock, patch

    from atlys_agentic import chdb_client, tracing
    from atlys_agentic.flows import analysis_flow

    chdb_client.init_schema()
    chdb_client.init_base_context()

    mock_client = MagicMock()
    mock_client.start_as_current_observation.return_value.__enter__.return_value = MagicMock()
    mock_client.get_current_trace_id.return_value = "trace-insight-1"
    mock_client.get_trace_url.return_value = "https://us.cloud.langfuse.com/trace/trace-insight-1"

    tracing._current_trace_id = None
    tracing._current_trace_url = None

    with patch("atlys_agentic.tracing.client", return_value=mock_client):
        result = analysis_flow.run(
            question="What is the conversion rate?",
            spec_id="01_express_checkout",
            enable_guardrails=False,
        )

    assert result["trace_id"] == "trace-insight-1"
    assert result["trace_url"] == "https://us.cloud.langfuse.com/trace/trace-insight-1"


# ==============================================================================
# LEVEL 4: UNSEEN SPEC GENERALIZATION & CONTEXT PERSISTENCE
# ==============================================================================

