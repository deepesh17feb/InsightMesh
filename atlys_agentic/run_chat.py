import time
import uuid

from fastapi import FastAPI
from pydantic import BaseModel, Field

from atlys_agentic.flows import analysis_flow

app = FastAPI(title="Atlys Product Analyst — OpenAI-compatible backend for LibreChat")


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage] = Field(min_length=1)


_DEFAULT_BASE_SQL = "SELECT * FROM purchase_completed"


@app.post("/v1/chat/completions")
def chat_completions(req: ChatCompletionRequest):
    question = req.messages[-1].content
    result = analysis_flow.run(question=question, spec_id="chat", base_sql=_DEFAULT_BASE_SQL)

    content = (
        f"{result['answer_md']}\n\n"
        f"_confidence: {result['confidence'].get('score')} · trace: {result['trace_id']}_"
    )
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": req.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }
