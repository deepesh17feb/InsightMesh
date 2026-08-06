"""Accuracy & evaluation benchmark across all complexity levels and acceptance criteria."""
from pathlib import Path

from atlys_agentic import tools
from atlys_agentic.flows.analysis_flow import AnalysisFlow, AnalysisState


class AccuracyBenchmark:
    """Benchmark harness evaluating system accuracy across complexity tiers."""

    @classmethod
    def evaluate_select_only_safety(cls) -> float:
        """Level 1: SELECT-only enforcement accuracy."""
        tests_passed = 0
        total_tests = 2

        # Test 1: Rejection of destructive statements
        try:
            tools._assert_select_only("DROP TABLE insights")
        except ValueError:
            tests_passed += 1

        # Test 2: Acceptance of safe analytic CTE queries
        try:
            tools._assert_select_only("WITH cte AS (SELECT 1 as x) SELECT * FROM cte")
            tests_passed += 1
        except ValueError:
            pass

        return tests_passed / total_tests


# ==============================================================================
# PYTEST TEST CASES
# ==============================================================================

def test_eval_level1_select_only_safety():
    score = AccuracyBenchmark.evaluate_select_only_safety()
    assert score == 1.0, f"Expected 100% accuracy on SELECT-only safety; got {score * 100:.1f}%"
