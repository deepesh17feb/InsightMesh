import os
import socket

import pytest
import requests

pytestmark = pytest.mark.skipif(
    os.getenv("LIBRECHAT_SMOKE") != "1",
    reason="manual smoke test: set LIBRECHAT_SMOKE=1 after `docker compose -f src/atlys_agentic/librechat/docker-compose.librechat.yml up -d` and `uvicorn src.atlys_agentic.run_chat:app --port 8008`",
)


def _port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0


def test_backend_reachable_directly():
    assert _port_open("localhost", 8008)
    r = requests.post(
        "http://localhost:8008/v1/chat/completions",
        json={"model": "atlys-analyst", "messages": [{"role": "user", "content": "Does Express lift conversion?"}]},
        timeout=30,
    )
    assert r.status_code == 200
    assert "content" in r.json()["choices"][0]["message"]


def test_librechat_ui_reachable():
    assert _port_open("localhost", 3080)
