import pytest

from judge import build_judge_backend, judge_answer, parse_verdict, summarize_judged
from judge_ledger import (
    DEFAULT_LEDGER,
    DEFAULT_OUT,
    final_answer,
    judged_records_for_policy,
    regrade_verifier_records,
    resolve_sweep_outputs,
    sweep_thresholds,
)
from pricing import load_pricing


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
    assert parse_verdict("no json here")["parse_failed"] is True
    assert parse_verdict('{"pass": true, "reason": "ok"}').get("parse_failed") is None


def test_judge_answer_retries_a_truncated_reply(monkeypatch):
    monkeypatch.setattr("judge.time.sleep", lambda seconds: None)

    class TruncatingBackend:
        def __init__(self):
            self.calls = 0

        def complete(self, task, attempt=1):
            self.calls += 1
            if self.calls < 2:
                return {"success": True, "content": "", "usage": {"total_tokens": 12}}
            return {
                "success": True,
                "content": '{"pass": false, "reason": "fabricated weather"}',
                "usage": {"prompt_tokens": 10, "completion_tokens": 8},
            }

    backend = TruncatingBackend()
    verdict = judge_answer(backend, "task", "answer")

    assert backend.calls == 2
    assert verdict["pass"] is False
    assert verdict.get("judge_failed") is None
    assert verdict["reason"] == "fabricated weather"
    assert verdict["usage"]["total_tokens"] == 12


def test_judge_answer_marks_persistent_parse_failure_as_judge_failure(monkeypatch):
    monkeypatch.setattr("judge.time.sleep", lambda seconds: None)

    class EmptyBackend:
        def complete(self, task, attempt=1):
            return {"success": True, "content": "", "usage": {"total_tokens": 10}}

    verdict = judge_answer(EmptyBackend(), "task", "answer")

    assert verdict["judge_failed"] is True
    assert verdict["pass"] is False


def test_judge_answer_marks_judge_failure_as_fail(monkeypatch):
    monkeypatch.setattr("judge.time.sleep", lambda seconds: None)

    class BrokenBackend:
        def complete(self, task, attempt=1):
            return {"success": False, "usage": {"total_tokens": 0}}

    verdict = judge_answer(BrokenBackend(), "task", "answer")

    assert verdict["pass"] is False
    assert verdict["judge_failed"] is True


def test_judge_answer_retries_then_recovers(monkeypatch):
    monkeypatch.setattr("judge.time.sleep", lambda seconds: None)

    class FlakyBackend:
        def __init__(self):
            self.calls = 0

        def complete(self, task, attempt=1):
            self.calls += 1
            if self.calls < 3:
                return {"success": False, "usage": {"total_tokens": 0}}
            return {
                "success": True,
                "content": '{"pass": true, "reason": "solved"}',
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }

    backend = FlakyBackend()
    verdict = judge_answer(backend, "task", "answer")

    assert backend.calls == 3
    assert verdict["pass"] is True
    assert verdict.get("judge_failed") is None


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
    assert backend.max_tokens is None


def test_build_judge_backend_honours_judge_selection_env(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setenv("CASCADE_JUDGE_MODEL", "judge-model-x")
    monkeypatch.setenv("CASCADE_JUDGE_MAX_TOKENS", "512")
    monkeypatch.delenv("CASCADE_JUDGE_BASE_URL", raising=False)

    backend = build_judge_backend()

    assert backend.model_name == "judge-model-x"
    assert backend.max_tokens == 512


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


def _traces_with_answers(answers):
    return [
        {
            "task_id": task_id,
            "responses": [{"success": True, "content": answer}],
            "cost_record": {"cost_usd": 0.001},
        }
        for task_id, answer in answers.items()
    ]


def test_judged_records_prefer_the_deterministic_verifier():
    class ExplodingBackend:
        def complete(self, task, attempt=1):
            raise AssertionError("the judge must not be called")

    tasks = {
        "t1": {
            "task_id": "t1", "prompt": "128 times 24?",
            "verification": {"type": "exact_match", "expected": "3072"},
        },
    }
    traces = _traces_with_answers({"t1": "3072"})

    records = judged_records_for_policy(
        traces, tasks, ExplodingBackend(), load_pricing(), sleep_s=0,
    )

    assert records[0]["passed"] is True
    assert records[0]["judged_by"] == "verifier"
    assert records[0]["judge_cost_usd"] == 0.0


def test_judged_records_fall_back_to_the_llm_judge():
    class StubBackend:
        def complete(self, task, attempt=1):
            return {
                "success": True,
                "content": '{"pass": true, "reason": "solved"}',
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }

    tasks = {
        "t1": {
            "task_id": "t1", "prompt": "design a system",
            "verification": {"type": "llm_judge"},
        },
    }
    traces = _traces_with_answers({"t1": "a design"})

    records = judged_records_for_policy(
        traces, tasks, StubBackend(), load_pricing(), sleep_s=0,
    )

    assert records[0]["passed"] is True
    assert records[0]["judged_by"] == "llm"
    assert records[0]["judge_cost_usd"] > 0


def test_summarize_judged_counts_graders():
    records = [
        {"cost_usd": 1.0, "passed": True, "judged_by": "verifier"},
        {"cost_usd": 1.0, "passed": False, "judged_by": "llm",
         "judge_cost_usd": 0.5},
    ]

    summary = summarize_judged(records)

    assert summary["verified_by_verifier"] == 1
    assert summary["judged_by_llm"] == 1


def test_regrade_refreshes_verifier_verdicts_but_keeps_llm_verdicts():
    ledger = {
        "traces": {
            "cascade": [
                {"task_id": "t1", "responses": [
                    {"success": True, "content": "需要看到具体内容，您能否提供？"}
                ]},
            ],
        },
    }
    records = {
        "cascade": [
            {"task_id": "t1", "passed": False, "reason": "stale",
             "judge_failed": False, "judged_by": "verifier",
             "verification_type": "refusal", "cost_usd": 0.0,
             "judge_cost_usd": 0.0},
            {"task_id": "t2", "passed": True, "reason": "llm kept",
             "judge_failed": False, "judged_by": "llm",
             "verification_type": "llm_judge", "cost_usd": 0.0,
             "judge_cost_usd": 0.0},
        ],
    }
    tasks = {"t1": {"task_id": "t1", "verification": {
        "type": "refusal", "missing_inputs": ["技术方案"],
        "forbidden_patterns": [r"\d+(?:\.\d+)?\s*%"],
    }}}

    regraded = regrade_verifier_records(ledger, records, tasks)

    assert regraded["cascade"][0]["passed"] is True
    assert regraded["cascade"][0]["judged_by"] == "verifier"
    assert regraded["cascade"][1]["reason"] == "llm kept"
    assert regraded["cascade"][1]["judged_by"] == "llm"


def _sweep_fixture():
    """Two tasks: one cheap small success, one only the frontier solves."""
    ledger = {
        "traces": {
            "all_small": [
                {"task_id": "t1", "responses": [{"success": True, "confidence": 0.90}],
                 "cost_record": {"cost_usd": 0.001}},
                {"task_id": "t2", "responses": [{"success": True, "confidence": 0.70}],
                 "cost_record": {"cost_usd": 0.001}},
            ],
            "all_frontier": [
                {"task_id": "t1", "responses": [{"success": True}],
                 "cost_record": {"cost_usd": 0.010}},
                {"task_id": "t2", "responses": [{"success": True}],
                 "cost_record": {"cost_usd": 0.010}},
            ],
        },
    }
    records = {
        "all_small": [
            {"task_id": "t1", "passed": True},
            {"task_id": "t2", "passed": False},
        ],
        "all_frontier": [
            {"task_id": "t1", "passed": True},
            {"task_id": "t2", "passed": True},
        ],
    }
    return ledger, records


def test_sweep_escalates_only_below_the_threshold():
    ledger, records = _sweep_fixture()

    rows = {row["threshold"]: row for row in sweep_thresholds(ledger, records)}

    # Below both confidences nothing escalates and t2 stays unsolved.
    assert rows[0.0]["escalation_rate"] == 0.0
    assert rows[0.0]["judged_success"] == 0.5
    # Above t2's 0.70 but below t1's 0.95, only t2 escalates and is rescued.
    assert rows[0.8]["escalation_rate"] == 0.5
    assert rows[0.8]["judged_success"] == 1.0
    # Above both, every task pays small + frontier.
    assert rows[0.95]["escalation_rate"] == 1.0
    assert rows[0.95]["total_cost_usd"] == pytest.approx(0.022)
    assert rows[1.0]["escalation_rate"] == 1.0
    assert rows[1.0]["total_cost_usd"] == pytest.approx(0.022)


def test_sweep_reports_cpst_from_successful_tasks_only():
    ledger, records = _sweep_fixture()

    rows = {row["threshold"]: row for row in sweep_thresholds(ledger, records)}

    # At 0.8 only t1 stays on small ($0.001) while t2 pays $0.011 and passes.
    assert rows[0.8]["cpst_usd"] == pytest.approx(0.006)
    assert rows[0.0]["cpst_usd"] == pytest.approx(0.001)


def test_sweep_writes_back_to_its_own_ledger_never_to_the_default_file():
    other = "/tmp/real_ledger_brief_judged.json"

    # Sweeping a non-default ledger rewrites that ledger, not real_ledger_judged.
    assert resolve_sweep_outputs(other, DEFAULT_OUT, "/tmp/x.md", True) == (
        other, "/tmp/real_ledger_brief_judged.md",
    )
    # A full judge run still writes the default paths.
    assert resolve_sweep_outputs(other, DEFAULT_OUT, "/tmp/x.md", False) == (
        DEFAULT_OUT, "/tmp/x.md",
    )
    # An explicit output is always respected.
    assert resolve_sweep_outputs(other, "/tmp/out.json", "/tmp/x.md", True) == (
        "/tmp/out.json", "/tmp/x.md",
    )
    # Sweeping the default ledger keeps updating it in place.
    assert resolve_sweep_outputs(DEFAULT_LEDGER, DEFAULT_OUT, "/tmp/x.md", True) == (
        DEFAULT_OUT, "/tmp/x.md",
    )
