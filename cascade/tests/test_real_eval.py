from real_eval import build_backends, build_ledger, sample_tasks
from backends import mock_backends
from pricing import load_pricing
from replay import load_tasks
from router import load_policy

import pytest


def test_sample_tasks_spreads_across_the_full_flow():
    tasks = [{"task_id": f"t{index}"} for index in range(100)]

    picked = sample_tasks(tasks, 10)

    assert len(picked) == 10
    assert picked[0]["task_id"] == "t0"
    assert picked[-1]["task_id"] == "t90"
    assert [task["task_id"] for task in picked] == [
        "t0", "t10", "t20", "t30", "t40", "t50", "t60", "t70", "t80", "t90",
    ]


def test_sample_tasks_returns_the_whole_flow_when_limit_is_larger():
    tasks = [{"task_id": f"t{index}"} for index in range(3)]

    assert sample_tasks(tasks, 10) == tasks


def test_sample_tasks_rejects_non_positive_limit():
    with pytest.raises(ValueError, match="positive"):
        sample_tasks([{"task_id": "t0"}], 0)


def test_build_backends_requires_credentials(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("CASCADE_SMALL_BASE_URL", raising=False)
    monkeypatch.delenv("CASCADE_FRONTIER_BASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="DASHSCOPE_API_KEY"):
        build_backends(30)


def test_build_backends_uses_bailian_defaults_and_timeout(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.delenv("CASCADE_SMALL_BASE_URL", raising=False)
    monkeypatch.delenv("CASCADE_SMALL_MODEL", raising=False)
    monkeypatch.delenv("CASCADE_FRONTIER_MODEL", raising=False)

    backends = build_backends(45)

    assert set(backends) == {"small", "frontier"}
    assert backends["small"].timeout_s == 45
    assert backends["frontier"].timeout_s == 45
    assert backends["small"].model_name == "qwen-turbo"
    assert backends["frontier"].model_name == "qwen-max"


def test_build_ledger_records_the_shared_max_tokens():
    tasks = load_tasks()[:1]

    ledger = build_ledger(
        tasks, load_pricing(), load_policy(), mock_backends(),
        limit=1, sleep_s=0, max_tokens=1024,
    )

    assert ledger["_meta"]["mode"] == "real"
    assert ledger["_meta"]["max_tokens"] == 1024
    assert ledger["_meta"]["task_count"] == 1
