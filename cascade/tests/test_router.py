import copy

import pytest

from router import (
    needs_escalation,
    route_escalation,
    route_first,
    task_confidence,
)
from schema import validate_route_decision

TASK = {
    "task_id": "task_0001",
    "kind": "simple",
    "prompt": "今天东莞天气怎么样？",
    "expected_difficulty": "low",
    "tags": ["weather"],
    "created_at": "2026-11-04T09:00:00+08:00",
}


@pytest.fixture
def policy():
    return {
        "confidence_threshold": 0.66,
        "confidence_by_difficulty": {"low": 0.93, "medium": 0.78, "high": 0.52},
        "max_attempts": {"all_frontier": 1, "all_small": 2, "cascade": 1},
        "task_mix": {"simple": 50, "medium": 30, "complex": 20},
    }


def test_confidence_is_deterministic_and_near_base(policy):
    first = task_confidence(TASK, policy)
    second = task_confidence(copy.deepcopy(TASK), policy)
    assert first == second
    assert 0.90 <= first <= 0.96


def test_confidence_reflects_difficulty(policy):
    complex_task = copy.deepcopy(TASK)
    complex_task["task_id"] = "task_0099"
    complex_task["expected_difficulty"] = "high"
    assert task_confidence(complex_task, policy) < task_confidence(TASK, policy)


def test_policy_specific_first_decisions(policy):
    frontier = route_first(TASK, "all_frontier", policy)
    assert frontier["selected_model"] == "frontier"
    assert frontier["escalated"] is False

    small = route_first(TASK, "all_small", policy)
    assert small["selected_model"] == "small"
    assert small["escalated"] is False

    cascade = route_first(TASK, "cascade", policy)
    assert cascade["selected_model"] == "small"
    assert cascade["escalated"] is False
    for decision in (frontier, small, cascade):
        assert validate_route_decision(decision)


def test_escalation_decision_is_valid(policy):
    decision = route_escalation(TASK, policy, "fallback: small failed")
    assert decision["selected_model"] == "frontier"
    assert decision["escalated"] is True
    assert validate_route_decision(decision)


def test_threshold_is_configurable(policy):
    assert needs_escalation(0.60, policy) is True
    assert needs_escalation(0.70, policy) is False
    stricter = {**policy, "confidence_threshold": 0.95}
    assert needs_escalation(0.93, stricter) is True


def test_unknown_policy_raises(policy):
    with pytest.raises(Exception):
        route_first(TASK, "cheapest", policy)
