import pytest

from judge import build_judge_backend, judge_answer, parse_verdict, summarize_judged
from judge_ledger import final_answer


def test_parse_verdict_accepts_plain_and_fenced_json():
    assert parse_verdict('{"pass": true, "reason": "ok"}') == {
        "pass": True, "reason": "ok",
    }
    assert parse_verdict('```json\n{"pass": false, "reason": "wrong"}\n```') == {
        "pass": False, "reason": "wrong",
    }


def test_parse_verdict_fails_closed_on_bad_output():
    assert parse_verdict("no json here")["pass"] is False
    assert parse_verdict('{"pass": "yes"}')["pass"] is False
    assert parse_verdict('{"pass": true, "reason": }')["pass"] is False


def test_judge_answer_marks_judge_failure_as_fail(monkeypatch):
    class BrokenBackend:
        def complete(self, task, attempt=1):
            return {"success": False, "usage": {"total_tokens": 0}}

    verdict = judge_answer(BrokenBackend(), "task", "answer")

    assert verdict["pass"] is False
    assert verdict["judge_failed"] is True


def test_judge_answer_parses_verdict_and_keeps_usage():
    class StubBackend:
        def complete(self, task, attempt=1):
            return {
                "success": True,
                "content": '{"pass": true, "reason": "solved"}',
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }

    verdict = judge_answer(StubBackend(), "task", "answer")

    assert verdict["pass"] is True
    assert verdict["reason"] == "solved"
    assert verdict["usage"]["completion_tokens"] == 5


def test_build_judge_backend_requires_credentials(monkeypatch):
    monkeypatch.delenv("CASCADE_JUDGE_BASE_URL", raising=False)
    monkeypatch.delenv("CASCADE_JUDGE_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="DASHSCOPE_API_KEY"):
        build_judge_backend()


def test_build_judge_backend_defaults_to_qwen_max(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.delenv("CASCADE_JUDGE_BASE_URL", raising=False)
    monkeypatch.delenv("CASCADE_JUDGE_API_KEY", raising=False)
    monkeypatch.delenv("CASCADE_JUDGE_MODEL", raising=False)

    backend = build_judge_backend()

    assert backend.model_name == "qwen-max"
    assert backend.role == "frontier"
    assert backend.request_logprobs is False


def test_summarize_judged_excludes_failed_spend_from_cpst():
    records = [
        {"cost_usd": 10.0, "passed": True, "judge_cost_usd": 1.0},
        {"cost_usd": 2.0, "passed": False, "judge_cost_usd": 1.0},
    ]

    summary = summarize_judged(records)

    assert summary["tasks"] == 2
    assert summary["passed"] == 1
    assert summary["success_rate"] == 0.5
    assert summary["cpst_usd"] == 10.0
    assert summary["failed_cost_usd"] == 2.0
    assert summary["judge_cost_usd"] == 2.0
    assert summary["all_in_cpst_usd"] == 12.0


def test_summarize_judged_excludes_judge_failures_from_the_denominator():
    records = [
        {"cost_usd": 10.0, "passed": True, "judge_cost_usd": 1.0},
        {"cost_usd": 2.0, "passed": False, "judge_cost_usd": 1.0},
        {"cost_usd": 5.0, "passed": False, "judge_failed": True,
         "judge_cost_usd": 0.0},
    ]

    summary = summarize_judged(records)

    assert summary["tasks"] == 3
    assert summary["judged"] == 2
    assert summary["judge_failures"] == 1
    assert summary["success_rate"] == 0.5
    assert summary["failed_cost_usd"] == 2.0
    assert summary["cpst_usd"] == 10.0


def test_final_answer_prefers_the_last_successful_attempt():
    trace = {"responses": [
        {"success": False, "content": ""},
        {"success": True, "content": "good"},
    ]}

    assert final_answer(trace) == "good"


def test_final_answer_falls_back_to_last_attempt():
    trace = {"responses": [{"success": False, "content": "last"}]}

    assert final_answer(trace) == "last"
    assert final_answer({"responses": []}) == ""
