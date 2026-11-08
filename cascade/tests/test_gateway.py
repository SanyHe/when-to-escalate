import pytest
from fastapi.testclient import TestClient

from engine import CascadeEngine
from gateway import build_task, classify_prompt, create_app
from pricing import load_pricing
from router import load_policy

USAGE_OK = {"prompt_tokens": 40, "completion_tokens": 20, "total_tokens": 60}
USAGE_FAIL = {"prompt_tokens": 40, "completion_tokens": 0, "total_tokens": 40}


class ScriptedBackend:
    def __init__(self, role, outcomes):
        self.role = role
        self.outcomes = list(outcomes)

    def complete(self, task, attempt=1):
        success = self.outcomes[min(attempt - 1, len(self.outcomes) - 1)]
        return {
            "task_id": task["task_id"],
            "model": self.role,
            "content": f"{self.role} answer" if success else "",
            "success": success,
            "latency_ms": 120.0,
            "usage": dict(USAGE_OK if success else USAGE_FAIL),
        }


class ExplodingEngine:
    policy_name = "cascade"
    backends = {"small": object(), "frontier": object()}

    def run_task(self, task):
        raise RuntimeError("sk-secret-CASCADE_FRONTIER_API_KEY Traceback /tmp/file.py")


def make_engine(small_outcomes, frontier_outcomes):
    return CascadeEngine(
        {
            "small": ScriptedBackend("small", small_outcomes),
            "frontier": ScriptedBackend("frontier", frontier_outcomes),
        },
        load_pricing(),
        load_policy(),
        "cascade",
    )


@pytest.fixture
def client():
    return TestClient(create_app(make_engine([True], [True])))


def test_classify_prompt_by_length():
    assert classify_prompt("short") == ("simple", "low")
    assert classify_prompt("x" * 121) == ("medium", "medium")
    assert classify_prompt("x" * 400) == ("complex", "high")


def test_build_task_is_schema_valid_and_classified():
    task = build_task("今天天气怎么样？需要带伞吗？")
    assert task["kind"] == "simple"
    assert task["expected_difficulty"] == "low"
    assert task["task_id"].startswith("req_")
    assert task["created_at"].endswith("+00:00")


def test_healthz_reports_policy_and_backends(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["policy"] == "cascade"
    assert body["backends"] == ["frontier", "small"]


def test_models_endpoint_lists_cascade(client):
    body = client.get("/v1/models").json()
    assert body["object"] == "list"
    assert body["data"][0]["id"] == "cascade"


def test_chat_completion_matches_openai_shape(client):
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "cascade",
            "messages": [{"role": "user", "content": "今天东莞天气怎么样？"}],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "chat.completion"
    assert body["id"].startswith("chatcmpl-")
    assert body["model"] == "small"
    assert body["choices"][0]["message"]["role"] == "assistant"
    assert body["choices"][0]["message"]["content"] == "small answer"
    assert body["usage"] == USAGE_OK
    assert body["cascade"]["success"] is True
    assert body["cascade"]["escalated"] is False
    assert body["cascade"]["attempts"] == 1
    assert body["cascade"]["kind"] == "simple"
    assert body["cascade"]["decisions"][0]["selected_model"] == "small"


def test_long_prompt_escalates_and_metadata_reports_both_attempts():
    client = TestClient(create_app(make_engine([True], [True])))
    long_prompt = "请帮我做一个跨平台比价并给出推荐。" + ("补充细节。" * 90)
    body = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": long_prompt}]},
    ).json()

    assert body["cascade"]["kind"] == "complex"
    assert body["cascade"]["escalated"] is True
    assert body["cascade"]["attempts"] == 2
    assert body["model"] == "frontier"
    assert len(body["cascade"]["decisions"]) == 2
    assert body["usage"]["total_tokens"] == 60 + 60
    assert "quality check" in body["cascade"]["decisions"][1]["reason"]


def test_small_failure_escalates_to_frontier():
    client = TestClient(create_app(make_engine([False], [True])))
    body = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "嗨"}]},
    ).json()

    assert body["cascade"]["success"] is True
    assert body["cascade"]["escalated"] is True
    assert body["choices"][0]["message"]["content"] == "frontier answer"
    assert "fallback" in body["cascade"]["decisions"][1]["reason"]


def test_empty_messages_are_rejected(client):
    response = client.post("/v1/chat/completions", json={"messages": []})
    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request_error"


def test_streaming_is_rejected_with_openai_error(client):
    response = client.post(
        "/v1/chat/completions",
        json={
            "stream": True,
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request_error"


def test_internal_errors_do_not_leak_details():
    client = TestClient(create_app(ExplodingEngine()))
    response = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 500
    text = response.text
    assert "sk-secret" not in text
    assert "Traceback" not in text
    assert "CASCADE_FRONTIER_API_KEY" not in text
    assert response.json()["error"]["type"] == "server_error"


def test_unconfigured_gateway_returns_clear_503(monkeypatch):
    for name in (
        "CASCADE_SMALL_BASE_URL",
        "CASCADE_FRONTIER_BASE_URL",
        "DASHSCOPE_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    client = TestClient(create_app())
    health = client.get("/healthz")
    chat = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hi"}]},
    )

    assert health.status_code == 503
    assert health.json()["status"] == "unconfigured"
    assert chat.status_code == 503
    assert "CASCADE_SMALL_BASE_URL" in chat.json()["error"]["message"]


def test_dashscope_key_only_builds_bailian_backends(monkeypatch):
    for name in ("CASCADE_SMALL_BASE_URL", "CASCADE_FRONTIER_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-bailian")

    client = TestClient(create_app())
    health = client.get("/healthz")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["backends"] == ["frontier", "small"]
