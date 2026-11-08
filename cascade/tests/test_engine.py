import copy

import pytest

from engine import CascadeEngine, aggregate, export_trace
from pricing import call_cost, load_pricing
from router import load_policy
from schema import validate_route_decision

SMALL_USAGE = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
FAILED_USAGE = {"prompt_tokens": 100, "completion_tokens": 0, "total_tokens": 100}


class ScriptedBackend:
    """In-process backend that returns pre-scripted success flags."""

    def __init__(self, role, outcomes, confidences=None):
        self.role = role
        self.outcomes = list(outcomes)
        self.confidences = list(confidences) if confidences else []
        self.calls = []

    def complete(self, task, attempt=1):
        self.calls.append(attempt)
        index = min(attempt - 1, len(self.outcomes) - 1)
        success = self.outcomes[index]
        usage = dict(SMALL_USAGE if success else FAILED_USAGE)
        response = {
            "task_id": task["task_id"],
            "model": self.role,
            "content": "fake answer" if success else "",
            "success": success,
            "latency_ms": 100.0,
            "usage": usage,
        }
        if self.confidences:
            response["confidence"] = self.confidences[
                min(index, len(self.confidences) - 1)
            ]
        return response


TASK = {
    "task_id": "task_0001",
    "kind": "simple",
    "prompt": "今天东莞天气怎么样？需要带伞吗？",
    "expected_difficulty": "low",
    "tags": ["weather"],
    "created_at": "2026-11-04T09:00:00+08:00",
}


@pytest.fixture(scope="module")
def pricing():
    return load_pricing()


@pytest.fixture(scope="module")
def policy():
    return load_policy()


def make_engine(role_outcomes, pricing, policy, policy_name="cascade"):
    backends = {
        role: ScriptedBackend(role, outcomes)
        for role, outcomes in role_outcomes.items()
    }
    return CascadeEngine(backends, pricing, policy, policy_name), backends


def test_cascade_confident_success_stays_on_the_small_model(pricing, policy):
    engine, backends = make_engine(
        {"small": [True], "frontier": [True]}, pricing, policy
    )
    trace = engine.run_task(TASK)

    assert len(trace["responses"]) == 1
    assert trace["responses"][0]["model"] == "small"
    assert trace["route_decisions"] == [trace["route_decisions"][0]]
    assert trace["route_decisions"][0]["escalated"] is False
    assert backends["frontier"].calls == []
    assert trace["cost_record"]["attempts"] == 1
    assert trace["cost_record"]["success"] is True
    assert trace["cost_record"]["cost_usd"] == call_cost(SMALL_USAGE, "small", pricing)


def test_cascade_escalates_when_the_small_model_fails(pricing, policy):
    engine, backends = make_engine(
        {"small": [False], "frontier": [True]}, pricing, policy
    )
    trace = engine.run_task(TASK)

    assert len(trace["responses"]) == 2
    assert trace["route_decisions"][1]["selected_model"] == "frontier"
    assert trace["route_decisions"][1]["escalated"] is True
    assert "fallback" in trace["route_decisions"][1]["reason"]
    assert backends["small"].calls == [1]
    assert backends["frontier"].calls == [1]
    assert trace["cost_record"]["attempts"] == 2
    assert trace["cost_record"]["success"] is True
    expected = (
        call_cost(FAILED_USAGE, "small", pricing)
        + call_cost(SMALL_USAGE, "frontier", pricing)
    )
    assert trace["cost_record"]["cost_usd"] == pytest.approx(expected)


def test_cascade_escalates_on_low_confidence_even_when_small_succeeds(pricing, policy):
    engine, _ = make_engine(
        {"small": [True], "frontier": [True]}, pricing, policy
    )
    hard_task = dict(TASK, expected_difficulty="high")
    trace = engine.run_task(hard_task)

    assert len(trace["responses"]) == 2
    assert trace["responses"][0]["success"] is True
    assert trace["route_decisions"][1]["escalated"] is True
    assert "quality check" in trace["route_decisions"][1]["reason"]
    assert trace["cost_record"]["attempts"] == 2


def test_cascade_uses_model_reported_confidence_over_the_prior(pricing, policy):
    backends = {
        "small": ScriptedBackend("small", [True], confidences=[0.95]),
        "frontier": ScriptedBackend("frontier", [True]),
    }
    engine = CascadeEngine(backends, pricing, policy, "cascade")
    # The rule prior for "high" is ~0.52 and would escalate; 0.95 must not.
    trace = engine.run_task(dict(TASK, expected_difficulty="high"))

    assert len(trace["responses"]) == 1
    assert trace["route_decisions"][0]["confidence"] == 0.95
    assert "reported confidence 0.95" in trace["route_decisions"][0]["reason"]


def test_cascade_escalates_on_low_reported_confidence(pricing, policy):
    backends = {
        "small": ScriptedBackend("small", [True], confidences=[0.30]),
        "frontier": ScriptedBackend("frontier", [True]),
    }
    engine = CascadeEngine(backends, pricing, policy, "cascade")
    # The rule prior for "low" is ~0.93 and would stay; 0.30 must escalate.
    trace = engine.run_task(TASK)

    assert len(trace["responses"]) == 2
    assert trace["route_decisions"][1]["escalated"] is True
    assert "quality check" in trace["route_decisions"][1]["reason"]
    assert "0.30" in trace["route_decisions"][1]["reason"]


def test_cascade_threshold_is_configurable(pricing, policy):
    strict = copy.deepcopy(policy)
    strict["confidence_threshold"] = 0.99
    engine, _ = make_engine({"small": [True], "frontier": [True]}, pricing, strict)
    trace = engine.run_task(TASK)

    assert len(trace["responses"]) == 2
    assert trace["route_decisions"][1]["escalated"] is True


def test_cascade_fails_when_both_models_fail_and_counts_both_costs(pricing, policy):
    engine, _ = make_engine(
        {"small": [False], "frontier": [False]}, pricing, policy
    )
    trace = engine.run_task(TASK)

    assert trace["cost_record"]["success"] is False
    assert trace["cost_record"]["attempts"] == 2
    assert trace["cost_record"]["cost_per_successful_task_usd"] == 0
    expected = (
        call_cost(FAILED_USAGE, "small", pricing)
        + call_cost(FAILED_USAGE, "frontier", pricing)
    )
    assert trace["cost_record"]["cost_usd"] == pytest.approx(expected)


def test_all_small_retries_then_succeeds(pricing, policy):
    engine, backends = make_engine({"small": [False, True]}, pricing, policy, "all_small")
    trace = engine.run_task(TASK)

    assert backends["small"].calls == [1, 2]
    assert trace["cost_record"]["attempts"] == 2
    assert trace["cost_record"]["success"] is True
    assert trace["cost_record"]["cost_usd"] == pytest.approx(
        call_cost(FAILED_USAGE, "small", pricing)
        + call_cost(SMALL_USAGE, "small", pricing)
    )


def test_all_small_exhausts_retries_and_reports_failed_cost(pricing, policy):
    engine, _ = make_engine({"small": [False]}, pricing, policy, "all_small")
    trace = engine.run_task(TASK)

    assert trace["cost_record"]["attempts"] == 2
    assert trace["cost_record"]["success"] is False
    assert trace["cost_record"]["cost_per_successful_task_usd"] == 0


def test_all_frontier_uses_one_attempt(pricing, policy):
    engine, _ = make_engine({"frontier": [True]}, pricing, policy, "all_frontier")
    trace = engine.run_task(TASK)

    assert len(trace["responses"]) == 1
    assert trace["responses"][0]["model"] == "frontier"
    assert trace["cost_record"]["attempts"] == 1


def test_every_route_decision_is_schema_valid(pricing, policy):
    for policy_name in ("all_frontier", "cascade", "all_small"):
        engine, _ = make_engine(
            {"small": [False, True], "frontier": [True]},
            pricing,
            policy,
            policy_name,
        )
        for decision in engine.run_task(dict(TASK, expected_difficulty="high"))[
            "route_decisions"
        ]:
            assert validate_route_decision(decision).valid


def test_export_trace_is_a_readable_decision_chain(pricing, policy):
    engine, _ = make_engine({"small": [False], "frontier": [True]}, pricing, policy)
    trace = engine.run_task(TASK)
    rendered = export_trace(trace)

    assert "task_0001 (cascade)" in rendered
    assert "-> small" in rendered
    assert "-> frontier" in rendered
    assert "success=True" in rendered


def test_aggregate_reports_escalation_and_latency(pricing, policy):
    engine, _ = make_engine({"small": [False], "frontier": [True]}, pricing, policy)
    traces = [engine.run_task(TASK)]
    summary = aggregate(traces)

    assert summary["escalation_rate"] == 1.0
    assert summary["avg_latency_ms"] == 200.0
    assert summary["tasks"] == 1
