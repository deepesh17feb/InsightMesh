from unittest.mock import patch

from fastapi.testclient import TestClient

from atlys_agentic.run_chat import app

client = TestClient(app)


def test_chat_completions_returns_openai_shaped_response():
    fake_result = {
        "answer_md": "Express lifts conversion 8% overall.",
        "confidence": {"score": 0.75, "rationale": "r"},
        "known_issue_match": False,
        "cuts": {"device_type": []},
        "trace_id": "trace-42",
    }
    with patch("atlys_agentic.run_chat.analysis_flow.run", return_value=fake_result) as mock_run:
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "atlys-analyst",
                "messages": [{"role": "user", "content": "Does Express lift conversion?"}],
            },
        )
    assert response.status_code == 200
    body = response.json()
    content = body["choices"][0]["message"]["content"]
    assert fake_result["answer_md"] in content
    assert "0.75" in content and "trace-42" in content
    assert body["object"] == "chat.completion"
    mock_run.assert_called_once()
    _, kwargs = mock_run.call_args
    assert kwargs["question"] == "Does Express lift conversion?"


def test_chat_completions_rejects_empty_messages():
    response = client.post("/v1/chat/completions", json={"model": "atlys-analyst", "messages": []})
    assert response.status_code == 422
