from unittest.mock import MagicMock, patch

from atlys_agentic import tracing


def test_trace_captures_trace_id_and_flushes():
    mock_client = MagicMock()
    mock_client.get_current_trace_id.return_value = "trace-abc"
    mock_client.start_as_current_observation.return_value.__enter__.return_value = MagicMock()

    with patch("atlys_agentic.tracing.client", return_value=mock_client):
        with tracing.trace("root", input={"x": 1}):
            pass

    mock_client.flush.assert_called_once()
    assert tracing.trace_url() is not None or tracing._current_trace_id == "trace-abc"


def test_trace_url_returns_none_when_no_trace_captured():
    tracing._current_trace_id = None
    assert tracing.trace_url() is None


def test_step_nests_under_active_trace_without_flushing():
    mock_client = MagicMock()
    mock_client.start_as_current_observation.return_value.__enter__.return_value = MagicMock()

    with patch("atlys_agentic.tracing.client", return_value=mock_client):
        with tracing.step("tool_call", input={"sql": "SELECT 1"}):
            pass

    mock_client.flush.assert_not_called()


def test_client_does_not_register_a_litellm_langfuse_callback():
    """LiteLLM's own 'langfuse' callback is broken against the installed langfuse
    version (AttributeError: module 'langfuse' has no attribute 'version') and is
    redundant anyway -- every reachable LLM call site already logs explicitly via
    tracing.generation()/tracing.span(). Regression test for accidentally
    re-registering it."""
    import litellm

    tracing._client = None
    litellm.success_callback = []
    litellm.failure_callback = []

    with patch("atlys_agentic.tracing.Langfuse", return_value=MagicMock()):
        tracing.client()

    assert "langfuse" not in litellm.success_callback
    assert "langfuse" not in litellm.failure_callback


def test_init_litellm_callbacks_no_longer_exists():
    """Guards against reintroducing the broken callback under its old name."""
    assert not hasattr(tracing, "init_litellm_callbacks")
