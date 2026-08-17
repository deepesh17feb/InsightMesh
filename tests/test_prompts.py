"""Contract tests: call each prompt builder with the kwargs its real call site
uses. Exists because build_product_analyst_synthesis_prompt's signature drifted
from its only caller (analysis_flow.py) and the TypeError was silently
swallowed by a bare `except Exception: pass` — these tests fail loudly instead."""
from atlys_agentic import prompts


def test_build_intent_classifier_system_prompt():
    out = prompts.build_intent_classifier_system_prompt(["01_express_checkout"])
    assert isinstance(out, str) and out


def test_build_product_analyst_synthesis_prompt():
    out = prompts.build_product_analyst_synthesis_prompt(
        question="Why did iOS conversion drop?",
        spec_id="01_express_checkout",
        table_name="express_checkout",
        known_issue="",
        cuts={"device_type": [{"device_type": "iOS", "events": 10}]},
        confidence={"score": 0.7, "rationale": "r"},
    )
    assert isinstance(out, str) and out


def test_build_instrumentation_engineer_prompt():
    out = prompts.build_instrumentation_engineer_prompt(
        spec_id="01_express_checkout",
        table_name="express_checkout",
        ddl="CREATE TABLE express_checkout (...)",
        strategy="CREATE_NEW",
        recommendation="",
    )
    assert isinstance(out, str) and out


def test_build_context_librarian_prompt():
    out = prompts.build_context_librarian_prompt(
        spec_id="01_express_checkout",
        table_name="express_checkout",
        additions=["otp_success"],
        conflicts=[],
        gaps=[],
    )
    assert isinstance(out, str) and out


def test_build_instrumentation_followup_prompt():
    out = prompts.build_instrumentation_followup_prompt(
        question="Why partition by month?",
        table_name="express_checkout",
        current_ddl="CREATE TABLE express_checkout (...)",
    )
    assert isinstance(out, str) and out
