from atlys_agentic import agents


def test_llm_reads_model_from_env(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "gemini/gemini-flash-latest")
    monkeypatch.setenv("LLM_TEMPERATURE", "0")
    llm = agents.llm()
    assert llm.model == "gemini/gemini-flash-latest"


def test_instrumentation_engineer_is_memory_free():
    agent = agents.build_instrumentation_engineer()
    # In CrewAI 1.15+, memory=False in the constructor resolves to None on the
    # object instance (since it delegates to the Crew's memory setting by default)
    assert agent.memory in (False, None)


def test_instrumentation_engineer_has_infer_schema_tool():
    agent = agents.build_instrumentation_engineer()
    tool_names = {t.name for t in agent.tools}
    assert "infer_schema" in tool_names
