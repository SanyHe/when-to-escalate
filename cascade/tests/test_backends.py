import json
import math

import httpx
import pytest

from backends import (
    BAILIAN_BASE_URL,
    MockBackend,
    OpenAICompatibleBackend,
    backends_from_env,
    bailian_backends,
    confidence_from_logprobs,
    mock_backends,
)


TASK = {
    "task_id": "task_0001",
    "kind": "simple",
    "prompt": "今天东莞天气怎么样？需要带伞吗？",
    "expected_difficulty": "low",
    "tags": ["weather"],
    "created_at": "2026-11-04T09:00:00+08:00",
}


def make_backend(handler, **kwargs):
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    return OpenAICompatibleBackend(
        "https://api.example.com",
        "vendor-model",
        role=kwargs.pop("role", "frontier"),
        client=client,
        **kwargs,
    )


def test_mock_backend_is_deterministic_and_schema_shaped():
    backend = MockBackend("small")
    first = backend.complete(TASK, attempt=1)
    second = backend.complete(TASK, attempt=1)
    assert first == second
    assert first["model"] == "small"
    assert first["usage"]["total_tokens"] == (
        first["usage"]["prompt_tokens"] + first["usage"]["completion_tokens"]
    )
    assert isinstance(first["success"], bool)
    assert "task_0001" in first["content"] or first["success"] is False


def test_mock_backends_return_both_roles():
    backends = mock_backends()
    assert backends["small"].complete(TASK)["model"] == "small"
    assert backends["frontier"].complete(TASK)["model"] == "frontier"


def test_openai_backend_success_returns_standard_usage():
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "a short answer"}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 5},
            },
        )

    backend = make_backend(handler)
    response = backend.complete(TASK, attempt=1)

    assert response["success"] is True
    assert response["model"] == "frontier"
    assert response["content"] == "a short answer"
    assert response["usage"] == {
        "prompt_tokens": 12,
        "completion_tokens": 5,
        "total_tokens": 17,
    }
    assert captured["url"] == "https://api.example.com/v1/chat/completions"
    assert captured["payload"]["model"] == "vendor-model"
    assert captured["payload"]["messages"] == [{"role": "user", "content": TASK["prompt"]}]
    assert "authorization" not in {key.lower() for key in captured["headers"]}


def test_openai_backend_sends_api_key_from_configuration_only():
    captured = {}

    def handler(request):
        captured["authorization"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}}]},
        )

    backend = make_backend(handler, api_key="sk-from-env")
    response = backend.complete(TASK)

    assert captured["authorization"] == "Bearer sk-from-env"
    assert response["usage"]["total_tokens"] == 0
    assert response["success"] is True


def test_openai_backend_http_error_is_a_failed_response_not_an_exception():
    def handler(request):
        return httpx.Response(500, json={"error": {"message": "boom"}})

    response = make_backend(handler).complete(TASK)

    assert response["success"] is False
    assert response["content"] == ""
    assert response["usage"] == {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }


def test_openai_backend_timeout_is_a_failed_response_not_an_exception():
    def handler(request):
        raise httpx.TimeoutException("timed out")

    response = make_backend(handler).complete(TASK)

    assert response["success"] is False
    assert response["usage"]["total_tokens"] == 0


def test_openai_backend_requests_logprobs_and_reports_confidence():
    captured = {}

    def handler(request):
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [{
                    "message": {"content": "ok"},
                    "logprobs": {
                        "content": [
                            {"token": "o", "logprob": -0.1},
                            {"token": "k", "logprob": -0.2},
                        ]
                    },
                }],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2},
            },
        )

    response = make_backend(handler).complete(TASK)

    assert captured["payload"]["logprobs"] is True
    assert captured["payload"]["top_logprobs"] == 3
    assert response["confidence"] == pytest.approx(round(math.exp(-0.15), 4))


def test_openai_backend_without_logprobs_omits_confidence():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    response = make_backend(handler).complete(TASK)

    assert response["success"] is True
    assert "confidence" not in response


def test_openai_backend_retries_without_logprobs_on_400():
    calls = []

    def handler(request):
        payload = json.loads(request.content)
        calls.append(payload)
        if payload.get("logprobs"):
            return httpx.Response(400, json={"error": {"message": "unsupported"}})
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    response = make_backend(handler).complete(TASK)

    assert len(calls) == 2
    assert calls[0]["logprobs"] is True
    assert "logprobs" not in calls[1]
    assert response["success"] is True
    assert "confidence" not in response


def test_request_logprobs_can_be_disabled():
    captured = {}

    def handler(request):
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "ok"}}]}
        )

    make_backend(handler, request_logprobs=False).complete(TASK)

    assert "logprobs" not in captured["payload"]
    assert "top_logprobs" not in captured["payload"]


def test_openai_backend_applies_shared_max_tokens():
    captured = {}

    def handler(request):
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "ok"}}]}
        )

    make_backend(handler, max_tokens=1024).complete(TASK)
    assert captured["payload"]["max_tokens"] == 1024

    make_backend(handler).complete(TASK)
    assert "max_tokens" not in captured["payload"]


def test_openai_backend_rejects_non_positive_max_tokens():
    with pytest.raises(ValueError):
        OpenAICompatibleBackend(
            "https://api.example.com", "vendor-model", role="small", max_tokens=0
        )


def test_confidence_from_logprobs_handles_missing_and_legacy_shapes():
    assert confidence_from_logprobs(None) is None
    assert confidence_from_logprobs({"content": []}) is None
    assert confidence_from_logprobs({}) is None
    assert confidence_from_logprobs(
        {"token_logprobs": [-0.1, -0.3]}
    ) == pytest.approx(round(math.exp(-0.2), 4))


def test_openai_backend_rejects_unknown_role():
    with pytest.raises(ValueError):
        OpenAICompatibleBackend(
            "https://api.example.com", "vendor-model", role="medium"
        )


def test_backends_from_env_requires_endpoints(monkeypatch):
    for name in (
        "CASCADE_SMALL_BASE_URL",
        "CASCADE_FRONTIER_BASE_URL",
        "CASCADE_SMALL_MODEL",
        "CASCADE_FRONTIER_MODEL",
        "CASCADE_FRONTIER_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(RuntimeError):
        backends_from_env()


def test_backends_from_env_builds_roles_and_keys_from_env(monkeypatch):
    monkeypatch.setenv("CASCADE_SMALL_BASE_URL", "http://127.0.0.1:6006/v1")
    monkeypatch.setenv("CASCADE_SMALL_MODEL", "wte-small")
    monkeypatch.setenv("CASCADE_FRONTIER_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("CASCADE_FRONTIER_MODEL", "frontier-model")
    monkeypatch.setenv("CASCADE_FRONTIER_API_KEY", "sk-env-only")
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("CASCADE_SMALL_API_KEY", raising=False)

    backends = backends_from_env()

    assert backends["small"].role == "small"
    assert backends["frontier"].role == "frontier"
    assert backends["small"].endpoint == "http://127.0.0.1:6006/v1/chat/completions"
    assert backends["frontier"].endpoint == "https://api.example.com/v1/chat/completions"
    assert backends["frontier"]._headers()["Authorization"] == "Bearer sk-env-only"
    assert "Authorization" not in backends["small"]._headers()


def test_backends_from_env_falls_back_to_dashscope_key(monkeypatch):
    monkeypatch.setenv("CASCADE_SMALL_BASE_URL", BAILIAN_BASE_URL)
    monkeypatch.setenv("CASCADE_FRONTIER_BASE_URL", BAILIAN_BASE_URL)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-dashscope")
    monkeypatch.delenv("CASCADE_SMALL_API_KEY", raising=False)
    monkeypatch.delenv("CASCADE_FRONTIER_API_KEY", raising=False)

    backends = backends_from_env()

    for role in ("small", "frontier"):
        headers = backends[role]._headers()
        assert headers["Authorization"] == "Bearer sk-dashscope"


def test_backends_from_env_prefers_role_specific_key(monkeypatch):
    monkeypatch.setenv("CASCADE_SMALL_BASE_URL", BAILIAN_BASE_URL)
    monkeypatch.setenv("CASCADE_FRONTIER_BASE_URL", BAILIAN_BASE_URL)
    monkeypatch.setenv("CASCADE_SMALL_API_KEY", "sk-small-only")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-dashscope")
    monkeypatch.delenv("CASCADE_FRONTIER_API_KEY", raising=False)

    backends = backends_from_env()

    assert backends["small"]._headers()["Authorization"] == "Bearer sk-small-only"
    assert backends["frontier"]._headers()["Authorization"] == "Bearer sk-dashscope"


def test_bailian_backends_defaults(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-bailian")
    monkeypatch.delenv("CASCADE_SMALL_MODEL", raising=False)
    monkeypatch.delenv("CASCADE_FRONTIER_MODEL", raising=False)

    backends = bailian_backends()

    assert backends["small"].role == "small"
    assert backends["frontier"].role == "frontier"
    assert backends["small"].model_name == "qwen-turbo"
    assert backends["frontier"].model_name == "qwen-max"
    expected = f"{BAILIAN_BASE_URL}/chat/completions"
    assert backends["small"].endpoint == expected
    assert backends["frontier"].endpoint == expected
    for role in ("small", "frontier"):
        assert backends[role]._headers()["Authorization"] == "Bearer sk-bailian"


def test_bailian_backends_custom_models(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-bailian")

    backends = bailian_backends(small_model="qwen-plus", frontier_model="qwen3.8-max")

    assert backends["small"].model_name == "qwen-plus"
    assert backends["frontier"].model_name == "qwen3.8-max"


def test_bailian_backends_models_from_env(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-bailian")
    monkeypatch.setenv("CASCADE_SMALL_MODEL", "qwen-plus")
    monkeypatch.setenv("CASCADE_FRONTIER_MODEL", "qwen3.8-max")

    backends = bailian_backends()

    assert backends["small"].model_name == "qwen-plus"
    assert backends["frontier"].model_name == "qwen3.8-max"


def test_bailian_backends_requires_key(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="DASHSCOPE_API_KEY"):
        bailian_backends()
