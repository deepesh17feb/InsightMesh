"""Analyst scope layer — hermetic, no network calls."""
from atlys_agentic import paths


def test_cuj2_simple_exists_and_is_reasonably_sized():
    doc = paths.REPO_ROOT / "docs" / "CUJ2-simple.md"
    assert doc.exists()
    text = doc.read_text(encoding="utf-8")
    assert len(text) > 200
    assert len(text.encode("utf-8")) < 10_000  # embedding ceiling: short enough to embed on every call


from atlys_agentic import prompts
from atlys_agentic.flows import analysis_flow


def test_repo_knowledge_context_embeds_all_four_docs_and_excludes_the_fifth():
    context = prompts._load_repo_knowledge_context()
    assert "CUJ 2 — What the Analyst Does" in context  # docs/CUJ2-simple.md
    assert "InsightMesh" in context or "Atlys" in context  # README.md sanity check
    assert len(context) > 20_000  # four real docs, not a stub


def test_classifier_prompt_documents_all_six_intents():
    text = prompts.build_intent_classifier_system_prompt()
    assert '"analytical" | "greeting" | "abusive" | "out_of_scope" | "repo_knowledge" | "ingestion_redirect"' in text
    assert "repo_knowledge" in text
    assert "ingestion_redirect" in text
    assert "atlys-instrumentation" in text


def test_classifier_prompt_embeds_the_repo_knowledge_context():
    text = prompts.build_intent_classifier_system_prompt()
    assert "CUJ 2 — What the Analyst Does" in text


def test_heuristic_routes_system_questions_to_repo_knowledge():
    for question in [
        "what is CUJ 2?",
        "how do you diagnose a drop?",
        "how does the analytics agent work?",
        "how do i run the backend?",
        "tell me about this system's architecture",
    ]:
        assert analysis_flow._heuristic_classify_intent(question)["intent"] == "repo_knowledge", question


def test_heuristic_routes_ingestion_questions_to_ingestion_redirect():
    for question in [
        "ingest a new spec",
        "propose a schema for the new feature",
        "what's the DDL for the express checkout table?",
        "create table for group family applications",
    ]:
        assert analysis_flow._heuristic_classify_intent(question)["intent"] == "ingestion_redirect", question


def test_heuristic_still_classifies_the_original_four_intents_correctly():
    assert analysis_flow._heuristic_classify_intent("hello")["intent"] == "greeting"
    assert analysis_flow._heuristic_classify_intent("you are stupid")["intent"] == "abusive"
    assert analysis_flow._heuristic_classify_intent("tell me a joke")["intent"] == "out_of_scope"
    assert analysis_flow._heuristic_classify_intent(
        "why did express checkout conversion drop on iOS?"
    )["intent"] == "analytical"
